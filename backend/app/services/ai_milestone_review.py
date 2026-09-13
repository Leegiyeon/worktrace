import json
from uuid import UUID

from openai import OpenAI, OpenAIError

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.ai import MilestoneReviewResponse, StoredMilestoneReview
from app.services.milestone_evidence import get_milestone_evidence
from app.services.milestone_review_state import build_milestone_review_context_fingerprint
from app.services.projects import ProjectMilestoneNotFoundError, ProjectNotFoundError


class AiMilestoneReviewConfigurationError(Exception):
    pass


class AiMilestoneReviewGenerationError(Exception):
    pass


SYSTEM_PROMPT = """당신은 프로젝트 마일스톤 완료 여부를 보조 판단하는 검토자다.
반드시 제공된 프로젝트 목표, 마일스톤 성취 기준, 계획 WBS, GitHub Evidence만 사용한다.
규칙:
- 완료 여부를 자동 확정하지 않는다. ready_candidate는 사람이 최종 확인할 수 있는 완료 후보라는 뜻이다.
- 제공되지 않은 사실, 수치, 테스트 결과, 운영 상태를 추정하거나 만들어내지 않는다.
- 실제 구현/업무 WBS가 남아 있거나 성취 기준 충족 근거가 부족하면 not_ready 또는 needs_review를 선택한다.
- '[검증 필요]' 합성 WBS는 지금 수행하는 검토 자체를 위한 체크포인트이므로, 그것만 남아 있다는 이유로 ready_candidate를 막지 않는다.
- 성취 기준이 모호하거나 비어 있으면 needs_review를 선택한다.
- supporting_evidence_ids에는 입력으로 제공된 Evidence id만 넣는다.
- Evidence 개수가 많다는 이유만으로 완료라고 판단하지 않는다.
- missing_checks에는 최종 완료 판단 전에 추가 확인할 구체적인 항목만 적는다.
- reasoning_summary는 짧고 실무적으로 작성한다.
"""


def review_milestone_completion(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID) -> MilestoneReviewResponse:
    if not settings.openai_api_key:
        raise AiMilestoneReviewConfigurationError()

    with connect(settings) as connection:
        project = connection.execute(
            "SELECT title, objective, success_criteria FROM projects WHERE owner_id=%s AND id=%s",
            (owner_id, project_id),
        ).fetchone()
        if project is None:
            raise ProjectNotFoundError()
        milestone = connection.execute(
            "SELECT title, description, acceptance_criteria FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id=%s",
            (owner_id, project_id, milestone_id),
        ).fetchone()
        if milestone is None:
            raise ProjectMilestoneNotFoundError()

    evidence = get_milestone_evidence(settings, owner_id, project_id, milestone_id)
    evidence_ids = {item.id for item in evidence.recent_evidence}
    substantive_pending = [item for item in evidence.pending_wbs if not item.is_validation_task]
    model = settings.openai_model or "gpt-4o-mini"

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(project, milestone, evidence, substantive_pending)},
            ],
            text_format=MilestoneReviewResponse,
        )
    except OpenAIError as exc:
        raise AiMilestoneReviewGenerationError() from exc
    except Exception as exc:
        raise AiMilestoneReviewGenerationError() from exc

    review = response.output_parsed
    if not isinstance(review, MilestoneReviewResponse):
        raise AiMilestoneReviewGenerationError()

    review.supporting_evidence_ids = [evidence_id for evidence_id in review.supporting_evidence_ids if evidence_id in evidence_ids]
    review.reviewed_wbs_total = evidence.total_wbs
    review.reviewed_wbs_completed = evidence.completed_wbs
    review.evidence_count = evidence.evidence_count

    if substantive_pending and review.verdict == "ready_candidate":
        review.verdict = "not_ready"
        pending_titles = ", ".join(item.title for item in substantive_pending[:3])
        review.missing_checks = _dedupe([*review.missing_checks, f"남은 WBS 완료 확인: {pending_titles}"])[:12]

    if not (evidence.acceptance_criteria or "").strip():
        review.verdict = "needs_review"
        review.missing_checks = _dedupe(["마일스톤 성취 기준을 먼저 정의해야 합니다.", *review.missing_checks])[:12]

    context_fingerprint = build_milestone_review_context_fingerprint(settings, owner_id, project_id, milestone_id)
    _save_review(settings, owner_id, project_id, milestone_id, review, model, context_fingerprint)
    return review


def list_latest_milestone_reviews(settings: Settings, owner_id: str, project_id: UUID) -> list[StoredMilestoneReview]:
    with connect(settings) as connection:
        project = connection.execute("SELECT 1 FROM projects WHERE owner_id=%s AND id=%s", (owner_id, project_id)).fetchone()
        if project is None:
            raise ProjectNotFoundError()
        rows = connection.execute(
            """
            SELECT DISTINCT ON (milestone_id)
                milestone_id, verdict, confidence, reasoning_summary,
                missing_checks, supporting_evidence_ids,
                reviewed_wbs_total, reviewed_wbs_completed, evidence_count,
                model, reviewed_at, context_fingerprint
            FROM project_milestone_reviews
            WHERE owner_id=%s AND project_id=%s
            ORDER BY milestone_id, reviewed_at DESC
            """,
            (owner_id, project_id),
        ).fetchall()

    results: list[StoredMilestoneReview] = []
    for row in rows:
        current_fingerprint = build_milestone_review_context_fingerprint(settings, owner_id, project_id, row["milestone_id"])
        stored_fingerprint = row.get("context_fingerprint") or ""
        is_stale = not stored_fingerprint or stored_fingerprint != current_fingerprint
        results.append(
            StoredMilestoneReview(
                milestone_id=row["milestone_id"],
                verdict=row["verdict"],
                confidence=row["confidence"],
                reasoning_summary=row["reasoning_summary"],
                missing_checks=row["missing_checks"] or [],
                supporting_evidence_ids=row["supporting_evidence_ids"] or [],
                reviewed_wbs_total=row["reviewed_wbs_total"],
                reviewed_wbs_completed=row["reviewed_wbs_completed"],
                evidence_count=row["evidence_count"],
                model=row.get("model") or "",
                reviewed_at=row["reviewed_at"],
                is_stale=is_stale,
                stale_reason="검토 이후 Evidence·WBS·성취 기준이 변경되어 재검토가 필요합니다." if is_stale else "",
            )
        )
    return results


def _save_review(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    milestone_id: UUID,
    review: MilestoneReviewResponse,
    model: str,
    context_fingerprint: str,
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO project_milestone_reviews (
                owner_id, project_id, milestone_id, verdict, confidence,
                reasoning_summary, missing_checks, supporting_evidence_ids,
                reviewed_wbs_total, reviewed_wbs_completed, evidence_count, model,
                context_fingerprint
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                owner_id, project_id, milestone_id, review.verdict, review.confidence,
                review.reasoning_summary,
                json.dumps(review.missing_checks, ensure_ascii=False),
                json.dumps(review.supporting_evidence_ids, ensure_ascii=False),
                review.reviewed_wbs_total, review.reviewed_wbs_completed, review.evidence_count, model,
                context_fingerprint,
            ),
        )


def _build_prompt(project, milestone, evidence, substantive_pending) -> str:
    pending_wbs = "\n".join(f"- [{item.status}/{item.priority}] {item.title}" for item in substantive_pending) or "- 없음"
    validation_wbs = "\n".join(f"- [{item.status}] {item.title}" for item in evidence.pending_wbs if item.is_validation_task) or "- 없음"
    recent_evidence = "\n".join(
        f"- id={item.id} | {item.kind} | {item.status} | {item.title} | {item.occurred_at or '날짜 없음'}"
        for item in evidence.recent_evidence
    ) or "- 없음"
    return f"""프로젝트: {project['title']}
프로젝트 목표: {project.get('objective') or '미정'}
프로젝트 성취 기준: {project.get('success_criteria') or '미정'}

마일스톤: {milestone['title']}
설명: {milestone.get('description') or '없음'}
마일스톤 성취 기준: {milestone.get('acceptance_criteria') or '미정'}

계획 WBS: {evidence.completed_wbs}/{evidence.total_wbs} 완료
실제 남은 구현/업무 WBS:
{pending_wbs}
검토 후 사용자가 확정할 검증 WBS:
{validation_wbs}

GitHub Evidence 총 {evidence.evidence_count}건, 최근 근거:
{recent_evidence}

위 근거만 사용하여 완료 후보 여부를 검토하세요."""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
