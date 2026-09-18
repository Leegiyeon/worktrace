from uuid import uuid4

from fastapi.testclient import TestClient

import app.api.milestone_evidence as milestone_evidence_api
from app.api.security import require_report_access
from app.main import app
from app.schemas.milestone_evidence import MilestoneEvidenceSummary
from app.services.milestone_completion import MilestoneConfirmationConflictError, MilestoneValidationBlockedError


def test_milestone_evidence_endpoint_returns_grounded_summary(monkeypatch) -> None:
    project_id = uuid4()
    milestone_id = uuid4()

    def fake_get_milestone_evidence(settings, owner_id, requested_project_id, requested_milestone_id):
        assert owner_id == "local-owner"
        assert requested_project_id == project_id
        assert requested_milestone_id == milestone_id
        return MilestoneEvidenceSummary(
            milestone_id=str(milestone_id),
            acceptance_criteria="회귀 검증을 통과한다.",
            total_wbs=2,
            completed_wbs=1,
            pending_wbs=[
                {
                    "id": str(uuid4()),
                    "title": "남은 회귀 테스트",
                    "status": "in_progress",
                    "priority": "high",
                }
            ],
            evidence_count=3,
            recent_evidence=[
                {
                    "kind": "commit",
                    "id": str(uuid4()),
                    "title": "fix: regression coverage",
                    "url": "https://github.com/example/repo/commit/abc",
                    "occurred_at": "2026-09-12T10:00:00+00:00",
                }
            ],
        )

    monkeypatch.setattr(milestone_evidence_api, "get_milestone_evidence", fake_get_milestone_evidence)
    app.dependency_overrides[require_report_access] = lambda: "local-owner"
    try:
        client = TestClient(app)
        response = client.get(f"/projects/{project_id}/milestones/{milestone_id}/evidence")
    finally:
        app.dependency_overrides.pop(require_report_access, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["milestone_id"] == str(milestone_id)
    assert payload["completed_wbs"] == 1
    assert payload["evidence_count"] == 3
    assert payload["recent_evidence"][0]["kind"] == "commit"


def confirmation_request():
    return {"status": "done", "expected_version": 0, "expected_context_fingerprint": "a" * 64,
            "request_id": str(uuid4()), "reason": "Reviewed acceptance", "evidence_note": "Acceptance steps passed"}


HEADERS = {"X-Worktrace-Owner-Id": "local-owner", "X-Worktrace-Report-Token": "dev-only-report-token"}


def test_manual_confirmation_route_requires_authenticated_context(monkeypatch):
    project_id, milestone_id = uuid4(), uuid4()
    path = f"/projects/{project_id}/milestones/{milestone_id}/validation"

    def save(settings, owner_id, requested_project, requested_milestone, payload):
        assert owner_id == "local-owner" and requested_project == project_id and requested_milestone == milestone_id
        assert payload.reason == "Reviewed acceptance" and payload.expected_version == 0
        return MilestoneEvidenceSummary(milestone_id=str(milestone_id))

    monkeypatch.setattr(milestone_evidence_api, "update_milestone_validation_status", save)
    client = TestClient(app)
    assert client.patch(path, json=confirmation_request()).status_code == 401
    assert client.patch(path, headers=HEADERS, json={"status": "done"}).status_code == 422
    assert client.patch(path, headers=HEADERS, json=confirmation_request()).status_code == 200


def test_confirmation_conflicts_and_gate_failures_have_stable_errors(monkeypatch):
    path = f"/projects/{uuid4()}/milestones/{uuid4()}/validation"
    for error, code in [(MilestoneConfirmationConflictError, "MILESTONE_CONFIRMATION_CONFLICT"),
                        (MilestoneValidationBlockedError, "MILESTONE_VALIDATION_BLOCKED")]:
        def fail(*args):
            raise error()

        monkeypatch.setattr(milestone_evidence_api, "update_milestone_validation_status", fail)
        response = TestClient(app).patch(path, headers=HEADERS, json=confirmation_request())
        assert response.status_code == 409 and response.json()["detail"]["code"] == code
        assert "AI" not in response.json()["detail"]["message"]
