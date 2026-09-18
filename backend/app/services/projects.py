from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.projects import (
    GitHubCommit,
    ProjectCreate,
    ProjectLifecycle,
    ProjectLifecycleConfirm,
    ProjectLifecycleHistoryItem,
    ProjectMilestone,
    ProjectMilestoneCreate,
    ProjectMilestoneUpdate,
    ProjectSummary,
    ProjectTask,
    ProjectTaskCreate,
    ProjectTaskUpdate,
    ProjectUpdate,
    RepositorySource,
    RepositorySourceCreate,
)


class ProjectNotFoundError(Exception):
    pass


class ProjectLifecycleConflictError(Exception):
    pass


class ProjectLifecycleValidationError(Exception):
    pass


class ProjectLifecycleRequestConflictError(Exception):
    pass


class ProjectStatusUpdateForbiddenError(Exception):
    pass


class ProjectTaskNotFoundError(Exception):
    pass


class ProjectMilestoneNotFoundError(Exception):
    pass


class ProjectMilestoneWeightError(Exception):
    pass


class RepositorySourceConflictError(Exception):
    pass


def upsert_repository_source(settings: Settings, owner_id: str, project_id: UUID, payload: RepositorySourceCreate) -> RepositorySource:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        existing = connection.execute(
            """
            SELECT id::text, project_id::text
            FROM repository_sources
            WHERE owner_id=%(owner_id)s AND provider='github' AND repository_id=%(repository_id)s
            """,
            {"owner_id": owner_id, "repository_id": payload.repository_id},
        ).fetchone()
        if existing is not None and str(existing["project_id"]) != str(project_id):
            raise RepositorySourceConflictError()
        row = connection.execute(
            """
            INSERT INTO repository_sources (owner_id, project_id, repository_id, full_name, default_branch)
            VALUES (%(owner_id)s, %(project_id)s, %(repository_id)s, %(full_name)s, %(default_branch)s)
            ON CONFLICT (owner_id, provider, repository_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                default_branch = EXCLUDED.default_branch,
                updated_at = now()
            WHERE repository_sources.project_id = EXCLUDED.project_id
            RETURNING id::text, project_id::text, repository_id, full_name, default_branch, updated_at::text
            """,
            {"owner_id": owner_id, "project_id": project_id, **payload.model_dump()},
        ).fetchone()
        if row is None:
            raise RepositorySourceConflictError()
    return RepositorySource(**row)


def get_repository_source(settings: Settings, owner_id: str, project_id: UUID) -> RepositorySource | None:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id::text, project_id::text, repository_id, full_name, default_branch, updated_at::text
            FROM repository_sources
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s AND provider = 'github'
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
    return RepositorySource(**row) if row else None


def list_project_commits(settings: Settings, owner_id: str, project_id: UUID) -> list[GitHubCommit]:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id::text, sha, message, author_name, committed_at::text, url
            FROM github_commits
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s
            ORDER BY committed_at DESC NULLS LAST, created_at DESC
            LIMIT 200
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
    return [GitHubCommit(**row) for row in rows]


def list_projects(settings: Settings, owner_id: str) -> list[ProjectSummary]:
    with connect(settings) as connection:
        rows = connection.execute(
            _PROJECT_SUMMARY_SQL + """
            WHERE p.owner_id = %(owner_id)s
            ORDER BY p.updated_at DESC, p.title ASC
            """,
            {"owner_id": owner_id},
        ).fetchall()
    return [_project_from_row(row) for row in rows]


def create_project(settings: Settings, owner_id: str, payload: ProjectCreate) -> ProjectSummary:
    with connect(settings) as connection:
        row = connection.execute(
            """
            INSERT INTO projects (owner_id, title, description, objective, success_criteria, status, role)
            VALUES (%(owner_id)s, %(title)s, %(description)s, %(objective)s, %(success_criteria)s, %(status)s, %(role)s)
            RETURNING id
            """,
            {"owner_id": owner_id, **payload.model_dump()},
        ).fetchone()
    return get_project(settings, owner_id, UUID(str(row["id"])))


def get_project(settings: Settings, owner_id: str, project_id: UUID) -> ProjectSummary:
    with connect(settings) as connection:
        row = connection.execute(
            _PROJECT_SUMMARY_SQL + """
            WHERE p.owner_id = %(owner_id)s AND p.id = %(project_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
    if row is None:
        raise ProjectNotFoundError()
    return _project_from_row(row)


def update_project(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectUpdate) -> ProjectSummary:
    updates = payload.model_dump(exclude_unset=True)
    with connect(settings) as connection:
        current = connection.execute(
            "SELECT status FROM projects WHERE owner_id=%s AND id=%s",
            (owner_id, project_id),
        ).fetchone()
        if current is None:
            raise ProjectNotFoundError()
        if "status" in updates and updates["status"] != current["status"]:
            raise ProjectStatusUpdateForbiddenError()
        row = connection.execute(
            """
            UPDATE projects
            SET title = COALESCE(%(title)s, title),
                description = COALESCE(%(description)s, description),
                objective = COALESCE(%(objective)s, objective),
                success_criteria = COALESCE(%(success_criteria)s, success_criteria),
                role = COALESCE(%(role)s, role),
                updated_at = now()
            WHERE owner_id = %(owner_id)s AND id = %(project_id)s
            RETURNING id
            """,
            {
                "owner_id": owner_id,
                "project_id": project_id,
                "title": updates.get("title"),
                "description": updates.get("description"),
                "objective": updates.get("objective"),
                "success_criteria": updates.get("success_criteria"),
                "role": updates.get("role"),
            },
        ).fetchone()
    if row is None:
        raise ProjectNotFoundError()
    return get_project(settings, owner_id, project_id)


def get_project_lifecycle(settings: Settings, owner_id: str, project_id: UUID) -> ProjectLifecycle:
    with connect(settings) as connection:
        return _get_project_lifecycle_in_connection(connection, owner_id, project_id)


def confirm_project_lifecycle(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    payload: ProjectLifecycleConfirm,
) -> ProjectLifecycle:
    snapshot = payload.model_dump(mode="json")
    with connect(settings) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{owner_id}:{project_id}",))
            project = connection.execute(
                """
                SELECT id, status, service_status, development_ended_on, lifecycle_version
                FROM projects
                WHERE owner_id=%s AND id=%s
                FOR UPDATE
                """,
                (owner_id, project_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError()

            replay = connection.execute(
                """
                SELECT request_snapshot
                FROM project_lifecycle_history
                WHERE owner_id=%s AND project_id=%s AND request_id=%s
                """,
                (owner_id, project_id, payload.request_id),
            ).fetchone()
            if replay is not None:
                if replay["request_snapshot"] == snapshot:
                    return _get_project_lifecycle_in_connection(connection, owner_id, project_id)
                raise ProjectLifecycleRequestConflictError()

            if int(project["lifecycle_version"]) != payload.expected_version:
                raise ProjectLifecycleConflictError()

            pending_task_count = _pending_task_count(connection, owner_id, project_id)
            incomplete_reason = payload.incomplete_reason
            if payload.status == "done" and pending_task_count > 0 and not incomplete_reason:
                raise ProjectLifecycleValidationError()

            if payload.development_ended_on is not None and payload.development_ended_on > datetime.now(ZoneInfo("Asia/Seoul")).date():
                raise ProjectLifecycleValidationError()

            next_ended_on = payload.development_ended_on if payload.status == "done" else None
            history_row = connection.execute(
                """
                INSERT INTO project_lifecycle_history (
                    owner_id, project_id, actor_owner_id, request_id, request_snapshot,
                    previous_status, next_status, previous_service_status, next_service_status,
                    reason, incomplete_reason, development_ended_on
                )
                VALUES (
                    %(owner_id)s, %(project_id)s, %(actor_owner_id)s, %(request_id)s, %(request_snapshot)s,
                    %(previous_status)s, %(next_status)s, %(previous_service_status)s, %(next_service_status)s,
                    %(reason)s, %(incomplete_reason)s, %(development_ended_on)s
                )
                RETURNING confirmed_at
                """,
                {
                    "owner_id": owner_id,
                    "project_id": project_id,
                    "actor_owner_id": owner_id,
                    "request_id": payload.request_id,
                    "request_snapshot": Jsonb(snapshot),
                    "previous_status": project["status"],
                    "next_status": payload.status,
                    "previous_service_status": project["service_status"],
                    "next_service_status": payload.service_status,
                    "reason": payload.reason,
                    "incomplete_reason": incomplete_reason,
                    "development_ended_on": next_ended_on,
                },
            ).fetchone()
            connection.execute(
                """
                UPDATE projects
                SET status=%(status)s,
                    service_status=%(service_status)s,
                    development_ended_on=%(development_ended_on)s,
                    lifecycle_version=lifecycle_version + 1,
                    lifecycle_confirmed_at=%(confirmed_at)s,
                    updated_at=now()
                WHERE owner_id=%(owner_id)s AND id=%(project_id)s
                """,
                {
                    "owner_id": owner_id,
                    "project_id": project_id,
                    "status": payload.status,
                    "service_status": payload.service_status,
                    "development_ended_on": next_ended_on,
                    "confirmed_at": history_row["confirmed_at"],
                },
            )
            return _get_project_lifecycle_in_connection(connection, owner_id, project_id)


def delete_project(settings: Settings, owner_id: str, project_id: UUID) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            "DELETE FROM projects WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        )
    if result.rowcount == 0:
        raise ProjectNotFoundError()


def list_project_milestones(settings: Settings, owner_id: str, project_id: UUID) -> list[ProjectMilestone]:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        rows = connection.execute(
            _MILESTONE_SQL + """
            WHERE m.owner_id = %(owner_id)s AND m.project_id = %(project_id)s
            GROUP BY m.id
            ORDER BY m.sort_order, m.created_at, m.title
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
    return [_milestone_from_row(row) for row in rows]


def create_project_milestone(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectMilestoneCreate) -> ProjectMilestone:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        current_weight = connection.execute(
            "SELECT COALESCE(SUM(weight), 0)::int AS total FROM project_milestones WHERE owner_id=%s AND project_id=%s",
            (owner_id, project_id),
        ).fetchone()["total"]
        if current_weight + payload.weight > 100:
            raise ProjectMilestoneWeightError()
        row = connection.execute(
            """
            INSERT INTO project_milestones (owner_id, project_id, milestone_key, title, description, acceptance_criteria, weight, sort_order)
            VALUES (%(owner_id)s, %(project_id)s, %(milestone_key)s, %(title)s, %(description)s, %(acceptance_criteria)s, %(weight)s, %(sort_order)s)
            RETURNING id
            """,
            {"owner_id": owner_id, "project_id": project_id, **payload.model_dump()},
        ).fetchone()
    return get_project_milestone(settings, owner_id, project_id, UUID(str(row["id"])))


def get_project_milestone(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID) -> ProjectMilestone:
    with connect(settings) as connection:
        row = connection.execute(
            _MILESTONE_SQL + """
            WHERE m.owner_id = %(owner_id)s AND m.project_id = %(project_id)s AND m.id = %(milestone_id)s
            GROUP BY m.id
            """,
            {"owner_id": owner_id, "project_id": project_id, "milestone_id": milestone_id},
        ).fetchone()
    if row is None:
        raise ProjectMilestoneNotFoundError()
    return _milestone_from_row(row)


def update_project_milestone(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID, payload: ProjectMilestoneUpdate) -> ProjectMilestone:
    existing = get_project_milestone(settings, owner_id, project_id, milestone_id)
    updates = payload.model_dump(exclude_unset=True)
    next_weight = updates.get("weight", existing.weight)
    with connect(settings) as connection:
        other_weight = connection.execute(
            "SELECT COALESCE(SUM(weight), 0)::int AS total FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id<>%s",
            (owner_id, project_id, milestone_id),
        ).fetchone()["total"]
        if other_weight + next_weight > 100:
            raise ProjectMilestoneWeightError()
        row = connection.execute(
            """
            UPDATE project_milestones
            SET title=%(title)s, description=%(description)s, acceptance_criteria=%(acceptance_criteria)s,
                weight=%(weight)s, sort_order=%(sort_order)s, updated_at=now()
            WHERE owner_id=%(owner_id)s AND project_id=%(project_id)s AND id=%(milestone_id)s
            RETURNING id
            """,
            {
                "owner_id": owner_id,
                "project_id": project_id,
                "milestone_id": milestone_id,
                "title": updates.get("title", existing.title),
                "description": updates.get("description", existing.description),
                "acceptance_criteria": updates.get("acceptance_criteria", existing.acceptance_criteria),
                "weight": next_weight,
                "sort_order": updates.get("sort_order", existing.sort_order),
            },
        ).fetchone()
    if row is None:
        raise ProjectMilestoneNotFoundError()
    return get_project_milestone(settings, owner_id, project_id, milestone_id)


def delete_project_milestone(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            "DELETE FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id=%s",
            (owner_id, project_id, milestone_id),
        )
    if result.rowcount == 0:
        raise ProjectMilestoneNotFoundError()


def list_project_tasks(settings: Settings, owner_id: str, project_id: UUID) -> list[ProjectTask]:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT t.id::text, t.project_id::text, t.title, t.description, t.status,
                   t.priority, t.due_date::text, t.milestone_id::text, t.counts_toward_progress,
                   t.created_at::text, t.updated_at::text
            FROM project_tasks t
            JOIN projects p ON p.id = t.project_id AND p.owner_id = %(owner_id)s
            WHERE t.owner_id = %(owner_id)s AND t.project_id = %(project_id)s
            ORDER BY
              CASE t.status WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2 WHEN 'on_hold' THEN 3 WHEN 'done' THEN 4 ELSE 5 END,
              CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
              t.due_date ASC NULLS LAST, t.updated_at DESC, t.title ASC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def create_project_task(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectTaskCreate) -> ProjectTask:
    _ensure_project_exists(settings, owner_id, project_id)
    if payload.milestone_id is not None:
        _ensure_milestone_exists(settings, owner_id, project_id, payload.milestone_id)
    with connect(settings) as connection:
        _lock_project_for_write(connection, owner_id, project_id)
        row = connection.execute(
            """
            INSERT INTO project_tasks (owner_id, project_id, title, description, status, priority, due_date, milestone_id, counts_toward_progress)
            VALUES (%(owner_id)s, %(project_id)s, %(title)s, %(description)s, %(status)s, %(priority)s, %(due_date)s, %(milestone_id)s, %(counts_toward_progress)s)
            RETURNING id::text, project_id::text, title, description, status, priority, due_date::text,
                      milestone_id::text, counts_toward_progress, created_at::text, updated_at::text
            """,
            {"owner_id": owner_id, "project_id": project_id, **payload.model_dump()},
        ).fetchone()
        connection.execute("UPDATE projects SET updated_at=now() WHERE owner_id=%s AND id=%s", (owner_id, project_id))
    return _task_from_row(row)


def update_project_task(settings: Settings, owner_id: str, project_id: UUID, task_id: UUID, payload: ProjectTaskUpdate) -> ProjectTask:
    updates = payload.model_dump(exclude_unset=True)
    with connect(settings) as connection:
        _lock_project_for_write(connection, owner_id, project_id)
        existing = connection.execute(
            """
            SELECT t.id::text, t.project_id::text, t.title, t.description, t.status, t.priority,
                   t.due_date::text, t.milestone_id::text, t.counts_toward_progress,
                   t.created_at::text, t.updated_at::text
            FROM project_tasks t
            WHERE t.owner_id=%s AND t.project_id=%s AND t.id=%s
            FOR UPDATE
            """,
            (owner_id, project_id, task_id),
        ).fetchone()
        if existing is None:
            raise ProjectTaskNotFoundError()
        milestone_id = updates["milestone_id"] if "milestone_id" in updates else existing.get("milestone_id")
        if "milestone_id" in updates and milestone_id is not None:
            _ensure_milestone_exists_in_connection(connection, owner_id, project_id, UUID(str(milestone_id)))
        next_values = {
            "title": updates.get("title", existing["title"]),
            "description": updates.get("description", existing.get("description") or ""),
            "status": updates.get("status", existing["status"]),
            "priority": updates.get("priority", existing.get("priority") or "medium"),
            "due_date": updates["due_date"] if "due_date" in updates else existing.get("due_date"),
            "milestone_id": milestone_id,
            "counts_toward_progress": updates.get("counts_toward_progress", existing.get("counts_toward_progress", True)),
        }
        row = connection.execute(
            """
            UPDATE project_tasks t
            SET title=%(title)s, description=%(description)s, status=%(status)s, priority=%(priority)s,
                due_date=%(due_date)s, milestone_id=%(milestone_id)s, counts_toward_progress=%(counts_toward_progress)s,
                updated_at=now()
            FROM projects p
            WHERE p.id=t.project_id AND p.owner_id=%(owner_id)s AND t.owner_id=%(owner_id)s
              AND t.project_id=%(project_id)s AND t.id=%(task_id)s
            RETURNING t.id::text, t.project_id::text, t.title, t.description, t.status, t.priority,
                      t.due_date::text, t.milestone_id::text, t.counts_toward_progress,
                      t.created_at::text, t.updated_at::text
            """,
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id, **next_values},
        ).fetchone()
        if row is None:
            raise ProjectTaskNotFoundError()
        connection.execute("UPDATE projects SET updated_at=now() WHERE owner_id=%s AND id=%s", (owner_id, project_id))
    return _task_from_row(row)


def delete_project_task(settings: Settings, owner_id: str, project_id: UUID, task_id: UUID) -> None:
    with connect(settings) as connection:
        _lock_project_for_write(connection, owner_id, project_id)
        result = connection.execute(
            """DELETE FROM project_tasks t USING projects p
               WHERE p.id=t.project_id AND p.owner_id=%(owner_id)s AND t.owner_id=%(owner_id)s
                 AND t.project_id=%(project_id)s AND t.id=%(task_id)s""",
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id},
        )
        if result.rowcount == 0:
            raise ProjectTaskNotFoundError()
        connection.execute("UPDATE projects SET updated_at=now() WHERE owner_id=%s AND id=%s", (owner_id, project_id))


def get_project_task(settings: Settings, owner_id: str, project_id: UUID, task_id: UUID) -> ProjectTask:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT t.id::text, t.project_id::text, t.title, t.description, t.status, t.priority,
                   t.due_date::text, t.milestone_id::text, t.counts_toward_progress,
                   t.created_at::text, t.updated_at::text
            FROM project_tasks t
            JOIN projects p ON p.id=t.project_id AND p.owner_id=%(owner_id)s
            WHERE t.owner_id=%(owner_id)s AND t.project_id=%(project_id)s AND t.id=%(task_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id},
        ).fetchone()
    if row is None:
        raise ProjectTaskNotFoundError()
    return _task_from_row(row)


def _ensure_project_exists(settings: Settings, owner_id: str, project_id: UUID) -> None:
    with connect(settings) as connection:
        row = connection.execute("SELECT id FROM projects WHERE owner_id=%s AND id=%s", (owner_id, project_id)).fetchone()
    if row is None:
        raise ProjectNotFoundError()


def _lock_project_for_write(connection, owner_id: str, project_id: UUID) -> None:
    row = connection.execute(
        "SELECT id FROM projects WHERE owner_id=%s AND id=%s FOR UPDATE",
        (owner_id, project_id),
    ).fetchone()
    if row is None:
        raise ProjectNotFoundError()


def _ensure_milestone_exists(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID) -> None:
    with connect(settings) as connection:
        row = _select_milestone(connection, owner_id, project_id, milestone_id)
    if row is None:
        raise ProjectMilestoneNotFoundError()


def _ensure_milestone_exists_in_connection(connection, owner_id: str, project_id: UUID, milestone_id: UUID) -> None:
    if _select_milestone(connection, owner_id, project_id, milestone_id) is None:
        raise ProjectMilestoneNotFoundError()


def _select_milestone(connection, owner_id: str, project_id: UUID, milestone_id: UUID):
    return connection.execute(
        "SELECT id FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id=%s",
        (owner_id, project_id, milestone_id),
    ).fetchone()


_PROJECT_SUMMARY_SQL = """
    SELECT p.id::text, p.title, p.description, p.objective, p.success_criteria, p.status,
           COALESCE(p.service_status, 'unknown') AS service_status,
           p.development_ended_on,
           COALESCE(p.lifecycle_version, 0)::bigint AS lifecycle_version,
           p.lifecycle_confirmed_at,
           p.role, p.updated_at::text,
           COALESCE(ts.total_tasks, 0)::int AS total_tasks,
           COALESCE(ts.completed_tasks, 0)::int AS completed_tasks,
           COALESCE(ts.remaining_tasks, 0)::int AS remaining_tasks,
           COALESCE(ts.derived_task_count, 0)::int AS derived_task_count,
           COALESCE(ms.milestone_count, 0)::int AS milestone_count,
           CASE WHEN COALESCE(ts.total_tasks, 0) > 0
                     AND COALESCE(ms.scoped_task_count, 0) = COALESCE(ts.total_tasks, 0)
                     AND COALESCE(ms.scoped_task_count, 0) > 0 THEN 'milestone'
                WHEN COALESCE(ts.total_tasks, 0) > 0 THEN 'wbs'
                ELSE 'unscoped' END AS progress_basis,
           CASE WHEN COALESCE(ts.total_tasks, 0) > 0
                     AND COALESCE(ms.scoped_task_count, 0) = COALESCE(ts.total_tasks, 0)
                     AND COALESCE(ms.scoped_task_count, 0) > 0 THEN COALESCE(ms.weighted_progress, 0)
                WHEN COALESCE(ts.total_tasks, 0) > 0 THEN ROUND((ts.completed_tasks::numeric / ts.total_tasks::numeric) * 100)::int
                ELSE 0 END AS progress_percent
    FROM projects p
    LEFT JOIN LATERAL (
        SELECT COUNT(*) FILTER (WHERE t.counts_toward_progress)::int AS total_tasks,
               COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.status='done')::int AS completed_tasks,
               COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.status<>'done')::int AS remaining_tasks,
               COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.source_provider='derived-github')::int AS derived_task_count
        FROM project_tasks t
        WHERE t.owner_id=%(owner_id)s AND t.project_id=p.id
    ) ts ON true
    LEFT JOIN LATERAL (
        SELECT COUNT(*)::int AS milestone_count,
               COALESCE(SUM(mt.task_count), 0)::int AS scoped_task_count,
               ROUND(COALESCE(SUM(m.weight * COALESCE(mt.progress_percent, 0)), 0)::numeric / NULLIF(SUM(m.weight), 0))::int AS weighted_progress
        FROM project_milestones m
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS task_count,
                   CASE WHEN COUNT(*)=0 THEN 0
                        ELSE ROUND((COUNT(*) FILTER (WHERE t.status='done')::numeric / COUNT(*)::numeric) * 100)::int END AS progress_percent
            FROM project_tasks t
            WHERE t.owner_id=%(owner_id)s AND t.project_id=p.id AND t.milestone_id=m.id AND t.counts_toward_progress
        ) mt ON true
        WHERE m.owner_id=%(owner_id)s AND m.project_id=p.id
    ) ms ON true
"""


_MILESTONE_SQL = """
    SELECT m.id::text, m.project_id::text, m.milestone_key, m.title, m.description, m.acceptance_criteria,
           m.weight, m.sort_order, m.updated_at::text,
           COUNT(t.id) FILTER (WHERE t.counts_toward_progress)::int AS total_tasks,
           COUNT(t.id) FILTER (WHERE t.counts_toward_progress AND t.status='done')::int AS completed_tasks,
           COUNT(t.id) FILTER (WHERE t.counts_toward_progress AND t.source_provider='derived-github')::int AS derived_task_count,
           CASE WHEN COUNT(t.id) FILTER (WHERE t.counts_toward_progress)=0 THEN 0
                ELSE ROUND((COUNT(t.id) FILTER (WHERE t.counts_toward_progress AND t.status='done')::numeric /
                            COUNT(t.id) FILTER (WHERE t.counts_toward_progress)::numeric) * 100)::int END AS progress_percent
    FROM project_milestones m
    LEFT JOIN project_tasks t ON t.milestone_id=m.id AND t.owner_id=%(owner_id)s
"""


def _project_from_row(row) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"], title=row["title"], description=row.get("description") or "",
        objective=row.get("objective") or "", success_criteria=row.get("success_criteria") or "",
        status=row["status"], service_status=row.get("service_status") or "unknown",
        development_ended_on=row.get("development_ended_on"),
        lifecycle_version=row.get("lifecycle_version") or 0,
        lifecycle_confirmed_at=row.get("lifecycle_confirmed_at"),
        role=row.get("role") or "", total_tasks=row.get("total_tasks") or 0,
        completed_tasks=row.get("completed_tasks") or 0, remaining_tasks=row.get("remaining_tasks") or 0,
        derived_task_count=row.get("derived_task_count") or 0, milestone_count=row.get("milestone_count") or 0,
        progress_basis=row.get("progress_basis") or "unscoped",
        progress_percent=row.get("progress_percent") or 0, updated_at=row["updated_at"],
    )


def _pending_task_count(connection, owner_id: str, project_id: UUID) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)::int AS count
            FROM project_tasks
            WHERE owner_id=%s AND project_id=%s AND status<>'done'
            """,
            (owner_id, project_id),
        ).fetchone()["count"]
    )


def _get_project_lifecycle_in_connection(connection, owner_id: str, project_id: UUID) -> ProjectLifecycle:
    project = connection.execute(
        """
        SELECT status,
               COALESCE(service_status, 'unknown') AS service_status,
               development_ended_on,
               COALESCE(lifecycle_version, 0)::bigint AS lifecycle_version,
               lifecycle_confirmed_at
        FROM projects
        WHERE owner_id=%s AND id=%s
        """,
        (owner_id, project_id),
    ).fetchone()
    if project is None:
        raise ProjectNotFoundError()
    rows = connection.execute(
        """
        SELECT id::text, actor_owner_id, previous_status, next_status AS status,
               previous_service_status, next_service_status AS service_status,
               reason, incomplete_reason, development_ended_on, confirmed_at
        FROM project_lifecycle_history
        WHERE owner_id=%s AND project_id=%s
        ORDER BY confirmed_at DESC, id DESC
        LIMIT 20
        """,
        (owner_id, project_id),
    ).fetchall()
    return ProjectLifecycle(
        status=project["status"],
        service_status=project["service_status"],
        development_ended_on=project.get("development_ended_on"),
        lifecycle_version=project["lifecycle_version"],
        lifecycle_confirmed_at=project.get("lifecycle_confirmed_at"),
        pending_task_count=_pending_task_count(connection, owner_id, project_id),
        history=[ProjectLifecycleHistoryItem(**{**row, "incomplete_reason": row.get("incomplete_reason") or ""}) for row in rows],
    )


def _milestone_from_row(row) -> ProjectMilestone:
    return ProjectMilestone(
        id=row["id"], project_id=row["project_id"], milestone_key=row["milestone_key"], title=row["title"],
        description=row.get("description") or "", acceptance_criteria=row.get("acceptance_criteria") or "",
        weight=row["weight"], sort_order=row.get("sort_order") or 0, total_tasks=row.get("total_tasks") or 0,
        completed_tasks=row.get("completed_tasks") or 0, derived_task_count=row.get("derived_task_count") or 0,
        progress_percent=row.get("progress_percent") or 0, updated_at=row["updated_at"],
    )


def _task_from_row(row) -> ProjectTask:
    return ProjectTask(
        id=row["id"], project_id=row["project_id"], title=row["title"], description=row.get("description") or "",
        status=row["status"], priority=row.get("priority") or "medium", due_date=row.get("due_date"),
        milestone_id=row.get("milestone_id"), counts_toward_progress=row.get("counts_toward_progress", True),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )
