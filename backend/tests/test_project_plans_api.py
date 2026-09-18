from uuid import UUID

from fastapi.testclient import TestClient

from app.api import project_plans
from app.main import app
from app.schemas.project_plans import ProjectPlan
from app.services.project_plans import ProjectPlanConflictError, ProjectPlanPolicyError, ProjectPlanRequestConflictError

HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def sample_plan(**overrides) -> ProjectPlan:
    data = {
        "version": 1,
        "status": "approved",
        "policy": "wbs",
        "context_fingerprint": "a" * 64,
        "total_tasks": 1,
        "derived_task_count": 0,
        "tasks": [{"id": "00000000-0000-0000-0000-000000000101", "title": "Task"}],
        "milestones": [{"id": "00000000-0000-0000-0000-000000000201", "title": "M1", "weight": 100}],
        "excluded_tasks": [],
        "policy_errors": {"wbs": [], "milestone": []},
        "history": [],
    }
    data.update(overrides)
    return ProjectPlan(**data)


def test_project_plan_routes_use_owner_context(monkeypatch):
    calls = []

    def fake_get(settings, owner_id, project_id):
        calls.append(("get", owner_id, project_id))
        return sample_plan()

    def fake_approve(settings, owner_id, project_id, payload):
        calls.append(("post", owner_id, project_id, payload.policy, payload.request_id))
        return sample_plan(version=2)

    monkeypatch.setattr(project_plans, "get_project_plan", fake_get)
    monkeypatch.setattr(project_plans, "approve_project_plan", fake_approve)
    client = TestClient(app)

    get_response = client.get(f"/projects/{PROJECT_ID}/plan", headers=HEADERS)
    post_response = client.post(
        f"/projects/{PROJECT_ID}/plan",
        headers=HEADERS,
        json={
            "policy": "wbs",
            "reason": "Approved current scope.",
            "expected_version": 1,
            "expected_context_fingerprint": "a" * 64,
            "request_id": "00000000-0000-0000-0000-000000000301",
        },
    )

    assert get_response.status_code == 200
    assert post_response.status_code == 200
    assert calls[0] == ("get", "local-owner", UUID(PROJECT_ID))
    assert calls[1][0:4] == ("post", "local-owner", UUID(PROJECT_ID), "wbs")


def test_plan_approval_errors_are_stable_409s(monkeypatch):
    client = TestClient(app)
    payload = {
        "policy": "wbs",
        "reason": "Approved current scope.",
        "expected_version": 1,
        "expected_context_fingerprint": "a" * 64,
        "request_id": "00000000-0000-0000-0000-000000000302",
    }

    for error, code in (
        (ProjectPlanConflictError(), "PROJECT_PLAN_VERSION_CONFLICT"),
        (ProjectPlanRequestConflictError(), "PROJECT_PLAN_REQUEST_CONFLICT"),
        (ProjectPlanPolicyError(), "PROJECT_PLAN_POLICY_BLOCKED"),
    ):
        def fail(*args, error=error):
            raise error

        monkeypatch.setattr(project_plans, "approve_project_plan", fail)
        response = client.post(f"/projects/{PROJECT_ID}/plan", headers=HEADERS, json=payload)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == code


def test_plan_approval_rejects_blank_reason_before_service():
    response = TestClient(app).post(
        f"/projects/{PROJECT_ID}/plan",
        headers=HEADERS,
        json={
            "policy": "wbs",
            "reason": " ",
            "expected_version": 0,
            "expected_context_fingerprint": "a" * 64,
            "request_id": "00000000-0000-0000-0000-000000000303",
        },
    )
    assert response.status_code == 422
