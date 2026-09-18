import hashlib
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.milestone_evidence import MilestoneCompletion, MilestoneConfirmationRecord, MilestoneValidationUpdate
from app.services.projects import ProjectMilestoneNotFoundError, ProjectNotFoundError, _lock_project_for_write
from app.services.project_plan_state import approval_status, context_fingerprint


class MilestoneConfirmationConflictError(Exception):
    pass


class MilestoneValidationBlockedError(Exception):
    pass


def _context(connection, owner_id: str, project_id: UUID, milestone_id: UUID) -> dict:
    # One statement gives the criteria, tasks and linked evidence one MVCC snapshot.
    row = connection.execute(
        """
        SELECT jsonb_build_object(
          'milestone', jsonb_build_object('id', m.id, 'title', m.title, 'description', m.description,
              'acceptance_criteria', m.acceptance_criteria, 'updated_at', m.updated_at),
          'tasks', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'id', t.id, 'title', t.title, 'description', t.description, 'status', t.status,
              'status_version', t.status_version, 'counts_toward_progress', t.counts_toward_progress,
              'source_provider', t.source_provider, 'source_key', t.source_key, 'updated_at', t.updated_at
          ) ORDER BY t.id) FROM project_tasks t
             WHERE t.owner_id=m.owner_id AND t.project_id=m.project_id AND t.milestone_id=m.id), '[]'::jsonb),
          'commits', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'id', c.id, 'message', c.message, 'url', c.url, 'committed_at', c.committed_at
          ) ORDER BY c.id) FROM project_milestone_evidence e
             JOIN github_commits c ON c.id=e.github_commit_id AND c.owner_id=e.owner_id AND c.project_id=e.project_id
             WHERE e.owner_id=m.owner_id AND e.project_id=m.project_id AND e.milestone_id=m.id), '[]'::jsonb)
        ) AS context,
        worktrace_project_plan_context(m.owner_id, m.project_id) AS plan_context,
        (SELECT jsonb_build_object('version', a.version, 'context_fingerprint', a.context_fingerprint)
         FROM project_plan_approvals a WHERE a.owner_id=m.owner_id AND a.project_id=m.project_id
         ORDER BY a.version DESC LIMIT 1) AS plan_approval
        FROM project_milestones m WHERE m.owner_id=%s AND m.project_id=%s AND m.id=%s
        """,
        (owner_id, project_id, milestone_id),
    ).fetchone()
    if row is None:
        raise ProjectMilestoneNotFoundError()
    context = row["context"]
    # Existing confirmations without exclusions keep their original context contract.
    if any(not task["counts_toward_progress"] and not is_legacy_validation(task) for task in context["tasks"]):
        context["plan"] = {
            "status": approval_status(row["plan_context"], row["plan_approval"]),
            "version": (row["plan_approval"] or {}).get("version", 0),
            "context_fingerprint": context_fingerprint(row["plan_context"]),
        }
    return context


def _fingerprint(context: dict) -> str:
    return hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def is_legacy_validation(task: dict) -> bool:
    return task.get("source_provider") == "derived-github" and (task.get("source_key") or "").startswith("milestone-validation:")


def _block_reasons(context: dict) -> list[str]:
    reasons = []
    if not (context["milestone"].get("acceptance_criteria") or "").strip():
        reasons.append("성취 기준을 먼저 등록하세요.")
    pending = sum(1 for task in context["tasks"] if task["counts_toward_progress"] and task["status"] != "done" and not is_legacy_validation(task))
    if pending:
        reasons.append(f"산정 대상 WBS {pending}개가 미완료입니다.")
    excluded = any(not task["counts_toward_progress"] and not is_legacy_validation(task) for task in context["tasks"])
    if excluded and context.get("plan", {}).get("status") != "approved":
        reasons.append("산정 제외 업무의 사유를 프로젝트 계획에서 승인하세요.")
    return reasons


def get_milestone_completion_in_connection(connection, owner_id: str, project_id: UUID, milestone_id: UUID) -> MilestoneCompletion:
    context = _context(connection, owner_id, project_id, milestone_id)
    fingerprint = _fingerprint(context)
    rows = connection.execute(
        """SELECT id::text, status, version, actor_owner_id, reason, evidence_note,
                  confirmed_at::text, context_fingerprint
           FROM project_milestone_confirmations
           WHERE owner_id=%s AND project_id=%s AND milestone_id=%s ORDER BY version DESC LIMIT 20""",
        (owner_id, project_id, milestone_id),
    ).fetchall()
    latest = rows[0] if rows else None
    reasons = _block_reasons(context)
    stale = bool(latest and latest["status"] == "done" and latest["context_fingerprint"] != fingerprint)
    return MilestoneCompletion(
        status=latest["status"] if latest else "planned", version=latest["version"] if latest else 0,
        context_fingerprint=fingerprint, is_stale=stale, can_confirm=not reasons,
        block_reasons=reasons, history=[MilestoneConfirmationRecord(**row) for row in rows],
    )


def confirm_milestone(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID, payload: MilestoneValidationUpdate) -> None:
    with connect(settings) as connection:
        try:
            _lock_project_for_write(connection, owner_id, project_id)
        except ProjectNotFoundError as exc:
            raise ProjectMilestoneNotFoundError() from exc
        # Keep the criterion row stable for the recorded confirmation snapshot.
        if connection.execute("SELECT id FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id=%s FOR UPDATE",
                              (owner_id, project_id, milestone_id)).fetchone() is None:
            raise ProjectMilestoneNotFoundError()
        request_snapshot = payload.model_dump(mode="json")
        previous = connection.execute(
            "SELECT request_snapshot FROM project_milestone_confirmations WHERE owner_id=%s AND milestone_id=%s AND request_id=%s",
            (owner_id, milestone_id, payload.request_id),
        ).fetchone()
        if previous:
            if previous["request_snapshot"] != request_snapshot:
                raise MilestoneConfirmationConflictError()
            return
        context = _context(connection, owner_id, project_id, milestone_id)
        fingerprint = _fingerprint(context)
        latest = connection.execute(
            "SELECT version FROM project_milestone_confirmations WHERE owner_id=%s AND milestone_id=%s ORDER BY version DESC LIMIT 1",
            (owner_id, milestone_id),
        ).fetchone()
        version = latest["version"] if latest else 0
        if version != payload.expected_version or fingerprint != payload.expected_context_fingerprint:
            raise MilestoneConfirmationConflictError()
        if payload.status == "done" and _block_reasons(context):
            raise MilestoneValidationBlockedError()
        connection.execute(
            """INSERT INTO project_milestone_confirmations
               (owner_id,project_id,milestone_id,actor_owner_id,status,version,request_id,request_snapshot,
                context_fingerprint,context_snapshot,reason,evidence_note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (owner_id, project_id, milestone_id, owner_id, payload.status, version + 1, payload.request_id,
             Jsonb(request_snapshot), fingerprint, Jsonb(context), payload.reason, payload.evidence_note),
        )
