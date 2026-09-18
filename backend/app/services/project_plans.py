from typing import Any
from uuid import UUID

from psycopg import errors
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.project_plans import ProjectPlan, ProjectPlanApprovalHistoryItem, ProjectPlanApprove
from app.services.project_plan_state import approval_status, context_fingerprint


class ProjectPlanNotFoundError(Exception):
    pass


class ProjectPlanConflictError(Exception):
    pass


class ProjectPlanRequestConflictError(Exception):
    pass


class ProjectPlanPolicyError(Exception):
    pass


def get_project_plan(settings: Settings, owner_id: str, project_id: UUID) -> ProjectPlan:
    with connect(settings) as connection:
        return _get_project_plan_in_connection(connection, owner_id, project_id)


def approve_project_plan(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectPlanApprove) -> ProjectPlan:
    request_snapshot = payload.model_dump(mode="json")
    with connect(settings) as connection:
        with connection.transaction():
            _lock_project_for_approval(connection, owner_id, project_id)
            replay = connection.execute(
                """
                SELECT request_snapshot
                FROM project_plan_approvals
                WHERE owner_id=%s AND project_id=%s AND request_id=%s
                """,
                (owner_id, project_id, payload.request_id),
            ).fetchone()
            if replay is not None:
                if replay["request_snapshot"] == request_snapshot:
                    return _get_project_plan_in_connection(connection, owner_id, project_id)
                raise ProjectPlanRequestConflictError()

            state = _read_project_plan_state(connection, owner_id, project_id)
            latest = state["latest"]
            expected_version = int(latest["version"]) if latest else 0
            if payload.expected_version != expected_version:
                raise ProjectPlanConflictError()
            if payload.expected_context_fingerprint != state["fingerprint"]:
                raise ProjectPlanConflictError()

            errors_for_policy = state["policy_errors"][payload.policy]
            if errors_for_policy:
                raise ProjectPlanPolicyError(errors_for_policy)
            if state["derived_task_count"] > 0 and not payload.reviewed_derived:
                raise ProjectPlanPolicyError(["GitHub에서 파생된 WBS는 사용자가 검토했음을 명시해야 합니다."])
            if state["excluded_tasks"] and not payload.exclusion_reason.strip():
                raise ProjectPlanPolicyError(["진척률에서 제외한 업무가 있으면 제외 사유를 입력해야 합니다."])

            version = expected_version + 1
            try:
                connection.execute(
                    """
                    INSERT INTO project_plan_approvals (
                        owner_id, project_id, version, policy, context_fingerprint, context_snapshot,
                        request_id, request_snapshot, reason, exclusion_reason, reviewed_derived, actor_owner_id
                    )
                    VALUES (
                        %(owner_id)s, %(project_id)s, %(version)s, %(policy)s, %(context_fingerprint)s, %(context_snapshot)s,
                        %(request_id)s, %(request_snapshot)s, %(reason)s, %(exclusion_reason)s, %(reviewed_derived)s, %(actor_owner_id)s
                    )
                    """,
                    {
                        "owner_id": owner_id,
                        "project_id": project_id,
                        "version": version,
                        "policy": payload.policy,
                        "context_fingerprint": state["fingerprint"],
                        "context_snapshot": Jsonb(state["context"]),
                        "request_id": payload.request_id,
                        "request_snapshot": Jsonb(request_snapshot),
                        "reason": payload.reason,
                        "exclusion_reason": payload.exclusion_reason,
                        "reviewed_derived": payload.reviewed_derived,
                        "actor_owner_id": owner_id,
                    },
                )
            except errors.UniqueViolation as exc:
                raise ProjectPlanConflictError() from exc
            return _get_project_plan_in_connection(connection, owner_id, project_id)


def _lock_project_for_approval(connection, owner_id: str, project_id: UUID) -> None:
    row = connection.execute(
        "SELECT id FROM projects WHERE owner_id=%s AND id=%s FOR UPDATE",
        (owner_id, project_id),
    ).fetchone()
    if row is None:
        raise ProjectPlanNotFoundError()


def _get_project_plan_in_connection(connection, owner_id: str, project_id: UUID) -> ProjectPlan:
    state = _read_project_plan_state(connection, owner_id, project_id)
    latest = state["latest"]
    status = approval_status(state["context"], latest)
    policy = latest["policy"] if latest else "wbs"
    version = int(latest["version"]) if latest else 0
    return ProjectPlan(
        version=version,
        status=status,
        policy=policy,
        context_fingerprint=state["fingerprint"],
        total_tasks=state["total_tasks"],
        derived_task_count=state["derived_task_count"],
        tasks=state["context"].get("tasks", []),
        milestones=state["context"].get("milestones", []),
        excluded_tasks=state["excluded_tasks"],
        policy_errors=state["policy_errors"],
        history=[ProjectPlanApprovalHistoryItem(**item) for item in state["history"]],
    )


def _read_project_plan_state(connection, owner_id: str, project_id: UUID) -> dict[str, Any]:
    row = connection.execute(
        """
        WITH project AS (
            SELECT id FROM projects WHERE owner_id=%(owner_id)s AND id=%(project_id)s
        ),
        context AS (
            SELECT worktrace_project_plan_context(%(owner_id)s, %(project_id)s) AS snapshot FROM project
        ),
        latest AS (
            SELECT version, policy, context_fingerprint
            FROM project_plan_approvals
            WHERE owner_id=%(owner_id)s AND project_id=%(project_id)s
            ORDER BY version DESC
            LIMIT 1
        ),
        history AS (
            SELECT COALESCE(jsonb_agg(to_jsonb(h) ORDER BY h.version DESC), '[]'::jsonb) AS items
            FROM (
                SELECT id::text, version, policy, reason, exclusion_reason, reviewed_derived, approved_at, actor_owner_id
                FROM project_plan_approvals
                WHERE owner_id=%(owner_id)s AND project_id=%(project_id)s
                ORDER BY version DESC
                LIMIT 20
            ) h
        )
        SELECT (SELECT snapshot FROM context) AS context,
               (SELECT to_jsonb(latest) FROM latest) AS latest,
               (SELECT items FROM history) AS history
        FROM project
        """,
        {"owner_id": owner_id, "project_id": project_id},
    ).fetchone()
    if row is None:
        raise ProjectPlanNotFoundError()
    context = row["context"] or {"tasks": [], "milestones": []}
    latest = row["latest"]
    tasks = context.get("tasks", [])
    milestones = context.get("milestones", [])
    counted = [task for task in tasks if task.get("counts_toward_progress")]
    excluded = [{"id": task["id"], "title": task["title"]} for task in tasks if not task.get("counts_toward_progress")]
    milestone_ids = {milestone["id"] for milestone in milestones}
    assigned_milestone_ids = {task.get("milestone_id") for task in counted if task.get("milestone_id")}
    weighted_milestone_ids = {milestone["id"] for milestone in milestones if int(milestone.get("weight") or 0) > 0}

    wbs_errors: list[str] = []
    milestone_errors: list[str] = []
    if not counted:
        wbs_errors.append("진척률에 포함되는 WBS가 1개 이상 필요합니다.")
        milestone_errors.append("진척률에 포함되는 WBS가 1개 이상 필요합니다.")
    missing_assignment = [task["id"] for task in counted if not task.get("milestone_id") or task.get("milestone_id") not in milestone_ids]
    if missing_assignment:
        milestone_errors.append("마일스톤 정책을 사용하려면 모든 포함 WBS가 이 프로젝트의 마일스톤에 연결되어야 합니다.")
    if sum(int(milestone.get("weight") or 0) for milestone in milestones) != 100:
        milestone_errors.append("마일스톤 가중치 합계는 100이어야 합니다.")
    if weighted_milestone_ids - assigned_milestone_ids:
        milestone_errors.append("가중치가 있는 모든 마일스톤에는 포함 WBS가 1개 이상 필요합니다.")

    return {
        "context": context,
        "fingerprint": context_fingerprint(context),
        "latest": latest,
        "history": row["history"] or [],
        "total_tasks": len(counted),
        "derived_task_count": sum(1 for task in counted if task.get("source_provider") == "derived-github"),
        "excluded_tasks": excluded,
        "policy_errors": {"wbs": wbs_errors, "milestone": milestone_errors},
    }
