from uuid import UUID

from fastapi.testclient import TestClient

from app.api import projects
from app.main import app
from app.schemas.projects import ProjectMilestone
from app.services.projects import ProjectMilestoneNotFoundError, ProjectMilestoneWeightError

HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
MILESTONE_ID = "00000000-0000-0000-0000-000000000201"


def sample_milestone(**overrides) -> ProjectMilestone:
    data = {
        "id": MILESTONE_ID,
        "project_id": PROJECT_ID,
        "milestone_key": "project-wbs",
        "title": "프로젝트·WBS 관리",
        "description": "",
        "acceptance_criteria": "목표와 WBS가 연결된다.",
        "weight": 15,
        "sort_order": 10,
        "total_tasks": 2,
        "completed_tasks": 1,
        "progress_percent": 50,
        "updated_at": "2026-09-12 00:00:00+00",
    }
    data.update(overrides)
    return ProjectMilestone(**data)


def test_milestone_list_and_create_routes(monkeypatch):
    calls = []

    def fake_list(settings, owner_id, project_id):
        calls.append(("list", owner_id, project_id))
        return [sample_milestone()]

    def fake_create(settings, owner_id, project_id, payload):
        calls.append(("create", owner_id, project_id, payload.weight))
        return sample_milestone(title=payload.title, weight=payload.weight)

    monkeypatch.setattr(projects, "list_project_milestones", fake_list)
    monkeypatch.setattr(projects, "create_project_milestone", fake_create)
    client = TestClient(app)

    list_response = client.get(f"/projects/{PROJECT_ID}/milestones", headers=HEADERS)
    create_response = client.post(
        f"/projects/{PROJECT_ID}/milestones",
        headers=HEADERS,
        json={
            "milestone_key": "project-wbs",
            "title": "프로젝트·WBS 관리",
            "acceptance_criteria": "목표와 WBS가 연결된다.",
            "weight": 15,
            "sort_order": 10,
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["progress_percent"] == 50
    assert create_response.status_code == 201
    assert create_response.json()["weight"] == 15
    assert calls[0][2] == UUID(PROJECT_ID)


def test_milestone_weight_overflow_is_stable_conflict(monkeypatch):
    def fake_create(settings, owner_id, project_id, payload):
        raise ProjectMilestoneWeightError()

    monkeypatch.setattr(projects, "create_project_milestone", fake_create)
    response = TestClient(app).post(
        f"/projects/{PROJECT_ID}/milestones",
        headers=HEADERS,
        json={"milestone_key": "overflow", "title": "초과", "weight": 30},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROJECT_MILESTONE_WEIGHT_INVALID"


def test_unknown_milestone_uses_stable_error(monkeypatch):
    def fake_update(settings, owner_id, project_id, milestone_id, payload):
        raise ProjectMilestoneNotFoundError()

    monkeypatch.setattr(projects, "update_project_milestone", fake_update)
    response = TestClient(app).patch(
        f"/projects/{PROJECT_ID}/milestones/{MILESTONE_ID}",
        headers=HEADERS,
        json={"title": "수정"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_MILESTONE_NOT_FOUND"


def test_milestone_write_lock_missing_project_is_404(monkeypatch):
    def missing(*args):
        raise projects.ProjectNotFoundError()

    monkeypatch.setattr(projects, "update_project_milestone", missing)
    monkeypatch.setattr(projects, "delete_project_milestone", missing)
    client = TestClient(app)
    path = f"/projects/{PROJECT_ID}/milestones/{MILESTONE_ID}"
    for response in (client.patch(path, headers=HEADERS, json={"title": "Changed"}), client.delete(path, headers=HEADERS)):
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
