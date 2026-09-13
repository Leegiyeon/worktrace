from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import app.services.ai_milestone_review as review_service
from app.schemas.ai import MilestoneReviewResponse
from app.schemas.milestone_evidence import MilestoneEvidenceItem, MilestoneEvidenceSummary, MilestoneWorkItem


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = 0

    def execute(self, query, params):
        self.calls += 1
        if self.calls == 1:
            return FakeResult({"title": "Worktrace", "objective": "업무 근거를 경력 자산으로 연결", "success_criteria": "근거 기반 완료 판단"})
        if self.calls == 2:
            return FakeResult({"title": "운영 안정성", "description": "운영 검증", "acceptance_criteria": "배포 및 운영 검증 완료"})
        return FakeResult(None)


@contextmanager
def fake_connect(settings):
    yield FakeConnection()


class FakeResponses:
    def parse(self, **kwargs):
        return SimpleNamespace(
            output_parsed=MilestoneReviewResponse(
                verdict="ready_candidate",
                confidence=0.91,
                reasoning_summary="근거가 충분해 보입니다.",
                missing_checks=[],
                supporting_evidence_ids=["valid-evidence", "invented-evidence"],
            )
        )


class FakeOpenAI:
    def __init__(self, api_key):
        self.responses = FakeResponses()


def _run_review(monkeypatch, evidence: MilestoneEvidenceSummary):
    monkeypatch.setattr(review_service, "connect", fake_connect)
    monkeypatch.setattr(review_service, "get_milestone_evidence", lambda *args: evidence)
    monkeypatch.setattr(review_service, "build_milestone_review_context_fingerprint", lambda *args: "context-fingerprint")
    monkeypatch.setattr(review_service, "OpenAI", FakeOpenAI)
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="test-model")
    return review_service.review_milestone_completion(settings, "owner", uuid4(), uuid4())


def test_pending_substantive_wbs_prevents_ready_candidate_and_filters_unknown_evidence(monkeypatch) -> None:
    milestone_id = uuid4()
    evidence = MilestoneEvidenceSummary(
        milestone_id=str(milestone_id),
        acceptance_criteria="배포 및 운영 검증 완료",
        total_wbs=2,
        completed_wbs=1,
        pending_wbs=[MilestoneWorkItem(id="wbs-2", title="운영 검증", status="in_progress", priority="high")],
        evidence_count=4,
        recent_evidence=[
            MilestoneEvidenceItem(
                kind="commit",
                id="valid-evidence",
                title="fix: deploy verification",
                url="https://github.com/example/repo/commit/abc",
            )
        ],
    )

    result = _run_review(monkeypatch, evidence)

    assert result.verdict == "not_ready"
    assert result.supporting_evidence_ids == ["valid-evidence"]
    assert result.reviewed_wbs_total == 2
    assert result.reviewed_wbs_completed == 1
    assert any("남은 WBS 완료 확인" in item for item in result.missing_checks)


def test_validation_checkpoint_does_not_block_ready_candidate(monkeypatch) -> None:
    milestone_id = uuid4()
    evidence = MilestoneEvidenceSummary(
        milestone_id=str(milestone_id),
        acceptance_criteria="배포 및 운영 검증 완료",
        total_wbs=2,
        completed_wbs=1,
        pending_wbs=[
            MilestoneWorkItem(
                id="validation-wbs",
                title="[검증 필요] 운영 안정성 성취 기준 확인",
                status="planned",
                priority="medium",
                source_provider="derived-github",
                source_key=f"milestone-validation:{milestone_id}",
                is_validation_task=True,
            )
        ],
        evidence_count=4,
        recent_evidence=[
            MilestoneEvidenceItem(
                kind="commit",
                id="valid-evidence",
                title="fix: deploy verification",
                url="https://github.com/example/repo/commit/abc",
            )
        ],
    )

    result = _run_review(monkeypatch, evidence)

    assert result.verdict == "ready_candidate"
    assert not any("남은 WBS 완료 확인" in item for item in result.missing_checks)
