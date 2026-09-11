from uuid import UUID

from fastapi.testclient import TestClient

from app.api import projects
from app.main import app
from app.schemas.projects import GitHubDelivery, ProjectGitHubStatus, ProjectSummary, ProjectTask, RepositorySource
from app.services.github_webhooks import GitHubDeliveryNotFoundError, GitHubWebhookResult
from app.services.projects import ProjectNotFoundError, ProjectTaskNotFoundError

HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
TASK_ID = "00000000-0000-0000-0000-000000000101"


def sample_project(**overrides) -> ProjectSummary:
    data = {
        "id": PROJECT_ID,
        "title": "업무 플랫폼 MVP",
        "description": "프로젝트 진척도 관리",
        "status": "in_progress",
        "role": "PM",
        "total_tasks": 4,
        "completed_tasks": 1,
        "remaining_tasks": 3,
        "progress_percent": 25,
        "updated_at": "2026-06-01 12:00:00+00",
    }
    data.update(overrides)
    return ProjectSummary(**data)


def sample_task(**overrides) -> ProjectTask:
    data = {
        "id": TASK_ID,
        "project_id": PROJECT_ID,
        "title": "업무 상태 UI 구현",
        "description": "예정/진행/완료/보류 상태를 관리한다.",
        "status": "planned",
        "priority": "medium",
        "due_date": None,
        "created_at": "2026-06-01 12:00:00+00",
        "updated_at": "2026-06-01 12:00:00+00",
    }
    data.update(overrides)
    return ProjectTask(**data)


def test_project_list_exposes_progress_and_remaining_tasks(monkeypatch):
    def fake_list_projects(settings, owner_id):
        assert owner_id == "local-owner"
        return [sample_project()]

    monkeypatch.setattr(projects, "list_projects", fake_list_projects)
    client = TestClient(app)

    response = client.get("/projects", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["remaining_tasks"] == 3
    assert body[0]["progress_percent"] == 25


def test_project_tasks_crud_routes_use_owner_context(monkeypatch):
    calls = []

    def fake_create_project_task(settings, owner_id, project_id, payload):
        calls.append((owner_id, project_id, payload.title, payload.status, payload.priority, payload.due_date))
        return sample_task(title=payload.title, status=payload.status, priority=payload.priority, due_date=str(payload.due_date))

    def fake_update_project_task(settings, owner_id, project_id, task_id, payload):
        calls.append((owner_id, project_id, task_id, payload.status, payload.priority, payload.due_date))
        return sample_task(status=payload.status, priority=payload.priority or "medium", due_date=payload.due_date)

    def fake_delete_project_task(settings, owner_id, project_id, task_id):
        calls.append((owner_id, project_id, task_id, "deleted"))

    monkeypatch.setattr(projects, "create_project_task", fake_create_project_task)
    monkeypatch.setattr(projects, "update_project_task", fake_update_project_task)
    monkeypatch.setattr(projects, "delete_project_task", fake_delete_project_task)
    client = TestClient(app)

    create_response = client.post(
        f"/projects/{PROJECT_ID}/tasks",
        headers=HEADERS,
        json={"title": "업무 상태 UI 구현", "status": "in_progress", "priority": "high", "due_date": "2026-06-07"},
    )
    update_response = client.patch(
        f"/projects/{PROJECT_ID}/tasks/{TASK_ID}",
        headers=HEADERS,
        json={"status": "done", "priority": "low", "due_date": None},
    )
    delete_response = client.delete(f"/projects/{PROJECT_ID}/tasks/{TASK_ID}", headers=HEADERS)

    assert create_response.status_code == 201
    assert create_response.json()["status"] == "in_progress"
    assert create_response.json()["priority"] == "high"
    assert create_response.json()["due_date"] == "2026-06-07"
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "done"
    assert update_response.json()["priority"] == "low"
    assert update_response.json()["due_date"] is None
    assert delete_response.status_code == 204
    assert calls[0][0] == "local-owner"
    assert calls[0][1] == UUID(PROJECT_ID)
    assert calls[0][4] == "high"
    assert calls[2][2] == UUID(TASK_ID)


def test_project_and_task_not_found_use_stable_errors(monkeypatch):
    def fake_get_project(settings, owner_id, project_id):
        raise ProjectNotFoundError()

    def fake_update_project_task(settings, owner_id, project_id, task_id, payload):
        raise ProjectTaskNotFoundError()

    monkeypatch.setattr(projects, "get_project", fake_get_project)
    monkeypatch.setattr(projects, "update_project_task", fake_update_project_task)
    client = TestClient(app)

    project_response = client.get(f"/projects/{PROJECT_ID}", headers=HEADERS)
    task_response = client.patch(
        f"/projects/{PROJECT_ID}/tasks/{TASK_ID}",
        headers=HEADERS,
        json={"status": "done"},
    )

    assert project_response.status_code == 404
    assert project_response.json()["detail"] == {
        "code": "PROJECT_NOT_FOUND",
        "message": "Project was not found.",
    }
    assert task_response.status_code == 404
    assert task_response.json()["detail"] == {
        "code": "PROJECT_TASK_NOT_FOUND",
        "message": "Project task was not found.",
    }


def test_project_github_status_and_reprocess_routes(monkeypatch):
    delivery = GitHubDelivery(
        id="00000000-0000-0000-0000-000000000201",
        delivery_id="delivery-1",
        event_name="push",
        ref="refs/heads/main",
        status="failed",
        reason="temporary_failure",
        processing_attempts=1,
        received_at="2026-09-11 01:00:00+00",
        last_processed_at="2026-09-11 01:00:00+00",
    )
    github_status = ProjectGitHubStatus(
        repository=RepositorySource(
            id="00000000-0000-0000-0000-000000000301",
            project_id=PROJECT_ID,
            repository_id=123,
            full_name="Leegiyeon/worktrace",
            default_branch="main",
            updated_at="2026-09-11 01:00:00+00",
        ),
        stored_commit_count=51,
        last_success_at="2026-09-11 01:00:00+00",
        deliveries=[delivery],
    )

    monkeypatch.setattr(projects, "get_project", lambda settings, owner_id, project_id: sample_project())
    monkeypatch.setattr(projects, "get_project_github_status", lambda settings, owner_id, project_id: github_status)
    monkeypatch.setattr(
        projects,
        "reprocess_github_delivery",
        lambda settings, owner_id, project_id, delivery_id: GitHubWebhookResult("processed", "", 2),
    )
    client = TestClient(app)

    status_response = client.get(f"/projects/{PROJECT_ID}/github-status", headers=HEADERS)
    reprocess_response = client.post(
        f"/projects/{PROJECT_ID}/github-deliveries/delivery-1/reprocess",
        headers=HEADERS,
    )

    assert status_response.status_code == 200
    assert status_response.json()["stored_commit_count"] == 51
    assert status_response.json()["deliveries"][0]["status"] == "failed"
    assert reprocess_response.status_code == 200
    assert reprocess_response.json() == {"status": "processed", "reason": "", "commits_stored": 2}


def test_reprocess_unknown_delivery_uses_stable_error(monkeypatch):
    def fake_reprocess(settings, owner_id, project_id, delivery_id):
        raise GitHubDeliveryNotFoundError()

    monkeypatch.setattr(projects, "reprocess_github_delivery", fake_reprocess)
    response = TestClient(app).post(
        f"/projects/{PROJECT_ID}/github-deliveries/missing/reprocess",
        headers=HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "GITHUB_DELIVERY_NOT_FOUND"
