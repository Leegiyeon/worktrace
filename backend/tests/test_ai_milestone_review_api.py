from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.security import require_report_access
import app.api.ai as ai_api
from app.main import app
from app.schemas.ai import MilestoneReviewResponse, StoredMilestoneReview


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


def test_latest_milestone_reviews_can_be_reloaded(monkeypatch) -> None:
    project_id = uuid4()
    milestone_id = uuid4()
    reviewed_at = datetime(2026, 9, 13, 11, 30, tzinfo=timezone.utc)

    def fake_list(settings, owner_id, requested_project_id):
        assert owner_id == "test-owner"
        assert requested_project_id == project_id
        return [
            StoredMilestoneReview(
                milestone_id=milestone_id,
                verdict="ready_candidate",
                confidence=0.9,
                reasoning_summary="성취 기준 근거가 확인됩니다.",
                missing_checks=[],
                supporting_evidence_ids=["commit-1"],
                reviewed_wbs_total=2,
                reviewed_wbs_completed=1,
                evidence_count=5,
                model="test-model",
                reviewed_at=reviewed_at,
            )
        ]

    monkeypatch.setattr(ai_api, "list_latest_milestone_reviews", fake_list)
    app.dependency_overrides[require_report_access] = lambda: "test-owner"
    try:
        client = TestClient(app)
        response = client.get(f"/ai/milestone-reviews/{project_id}")
    finally:
        app.dependency_overrides.pop(require_report_access, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["milestone_id"] == str(milestone_id)
    assert payload[0]["verdict"] == "ready_candidate"
    assert payload[0]["model"] == "test-model"
    assert payload[0]["reviewed_at"].startswith("2026-09-13T11:30:00")
