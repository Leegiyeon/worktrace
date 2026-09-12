from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.milestone_evidence import MilestoneEvidenceSummary
import app.api.milestone_evidence as milestone_evidence_api


def test_milestone_evidence_endpoint_returns_grounded_summary(monkeypatch) -> None:
    project_id = uuid4()
    milestone_id = uuid4()

    def fake_get_milestone_evidence(settings, owner_id, requested_project_id, requested_milestone_id):
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
    client = TestClient(app)
    response = client.get(
        f"/projects/{project_id}/milestones/{milestone_id}/evidence",
        headers={"X-Worktrace-Owner": "local-owner", "X-Report-Token": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["milestone_id"] == str(milestone_id)
    assert payload["completed_wbs"] == 1
    assert payload["evidence_count"] == 3
    assert payload["recent_evidence"][0]["kind"] == "commit"
