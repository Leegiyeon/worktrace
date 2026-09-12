from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.security import require_report_access
import app.api.ai as ai_api
from app.main import app
from app.schemas.ai import MilestoneReviewResponse


def test_ai_milestone_review_returns_structured_advisory(monkeypatch) -> None:
    project_id = uuid4()
    milestone_id = uuid4()

    def fake_review(settings, owner_id, requested_project_id, requested_milestone_id):
        assert owner_id == "test-owner"
        assert requested_project_id == project_id
        assert requested_milestone_id == milestone_id
        return MilestoneReviewResponse(
            verdict="needs_review",
            confidence=0.82,
            reasoning_summary="WBS는 완료됐지만 운영 검증 근거를 추가 확인해야 합니다.",
            missing_checks=["운영 검증 결과 확인"],
            supporting_evidence_ids=["evidence-1"],
            reviewed_wbs_total=3,
            reviewed_wbs_completed=3,
            evidence_count=7,
        )

    monkeypatch.setattr(ai_api, "review_milestone_completion", fake_review)
    app.dependency_overrides[require_report_access] = lambda: "test-owner"
    try:
        client = TestClient(app)
        response = client.post(
            "/ai/milestone-review",
            json={"project_id": str(project_id), "milestone_id": str(milestone_id)},
        )
    finally:
        app.dependency_overrides.pop(require_report_access, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "needs_review"
    assert payload["reviewed_wbs_completed"] == 3
    assert payload["evidence_count"] == 7
    assert payload["supporting_evidence_ids"] == ["evidence-1"]
