import pytest
from pydantic import ValidationError
from uuid import uuid4

from app.schemas.milestone_evidence import MilestoneValidationUpdate
from app.services.milestone_completion import _block_reasons


def test_gate_counts_manual_null_source_tasks_but_not_synthetic_checkpoints():
    context = {"milestone": {"acceptance_criteria": "Checked result"}, "tasks": [
        {"status": "planned", "counts_toward_progress": True, "source_provider": None, "source_key": None},
        {"status": "planned", "counts_toward_progress": True, "source_provider": "derived-github", "source_key": "milestone-validation:test"},
        {"status": "planned", "counts_toward_progress": False},
    ]}
    assert _block_reasons(context) == ["산정 대상 WBS 1개가 미완료입니다.", "산정 제외 업무의 사유를 프로젝트 계획에서 승인하세요."]
    context["plan"] = {"status": "approved"}
    assert _block_reasons(context) == ["산정 대상 WBS 1개가 미완료입니다."]


def test_gate_requires_criteria_but_not_ai_or_github():
    assert _block_reasons({"milestone": {"acceptance_criteria": " "}, "tasks": []}) == ["성취 기준을 먼저 등록하세요."]
    assert _block_reasons({"milestone": {"acceptance_criteria": "Manual acceptance"}, "tasks": []}) == []


@pytest.mark.parametrize("overrides", [{"reason": " "}, {"evidence_note": " "}, {"expected_context_fingerprint": "bad"}, {"expected_version": -1}])
def test_confirmation_rejects_missing_or_invalid_context(overrides):
    data = dict(status="done", expected_version=0, expected_context_fingerprint="a" * 64, request_id=uuid4(), reason="Accepted", evidence_note="Test passed")
    with pytest.raises(ValidationError):
        MilestoneValidationUpdate(**{**data, **overrides})


def test_reopen_needs_reason_but_no_new_completion_evidence():
    payload = MilestoneValidationUpdate(status="planned", expected_version=1, expected_context_fingerprint="a" * 64,
                                        request_id=uuid4(), reason=" Reopened ")
    assert payload.reason == "Reopened" and payload.evidence_note == ""
