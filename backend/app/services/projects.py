from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.projects import (
    GitHubCommit,
    ProjectCreate,
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


class ProjectTaskNotFoundError(Exception):
    pass


class ProjectMilestoneNotFoundError(Exception):
    pass


class ProjectMilestoneWeightError(Exception):
    pass


def upsert_repository_source(settings: Settings, owner_id: str, project_id: UUID, payload: RepositorySourceCreate) -> RepositorySource:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        row = connection.execute(
            """
            INSERT INTO repository_sources (owner_id, project_id, repository_id, full_name, default_branch)
            VALUES (%(owner_id)s, %(project_id)s, %(repository_id)s, %(full_name)s, %(default_branch)s)
            ON CONFLICT (owner_id, provider, repository_id) DO UPDATE
            SET project_id = EXCLUDED.project_id,
                full_name = EXCLUDED.full_name,
                default_branch = EXCLUDED.default_branch,
                updated_at = now()
            RETURNING id::text, project_id::text, repository_id, full_name, default_branch, updated_at::text
            """,
            {"owner_id": owner_id, "project_id": project_id, **payload.model_dump()},
        ).fetchone()
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
    existing = get_project(settings, owner_id, project_id)
    updates = payload.model_dump(exclude_unset=True)
    next_values = {
        "title": updates.get("title", existing.title),
        "description": updates.get("description", existing.description),
        "objective": updates.get("objective", existing.objective),
        "success_criteria": updates.get("success_criteria", existing.success_criteria),
        "status": updates.get("status", existing.status),
        "role": updates.get("role", existing.role),
    }
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE projects
            SET title = %(title)s,
                description = %(description)s,
                objective = %(objective)s,
                success_criteria = %(success_criteria)s,
                status = %(status)s,
                role = %(role)s,
                updated_at = now()
            WHERE owner_id = %(owner_id)s AND id = %(project_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id, **next_values},
        )
    return get_project(settings, owner_id, project_id)


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
    existing = get_project_task(settings, owner_id, project_id, task_id)
    updates = payload.model_dump(exclude_unset=True)
    milestone_id = updates.get("milestone_id", existing.milestone_id)
    if milestone_id is not None:
        _ensure_milestone_exists(settings, owner_id, project_id, UUID(str(milestone_id)))
    next_values = {
        "title": updates.get("title", existing.title),
        "description": updates.get("description", existing.description),
        "status": updates.get("status", existing.status),
        "priority": updates.get("priority", existing.priority),
        "due_date": updates.get("due_date", existing.due_date),
        "milestone_id": milestone_id,
        "counts_toward_progress": updates.get("counts_toward_progress", existing.counts_toward_progress),
    }
    with connect(settings) as connection:
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


def _ensure_milestone_exists(settings: Settings, owner_id: str, project_id: UUID, milestone_id: UUID) -> None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id FROM project_milestones WHERE owner_id=%s AND project_id=%s AND id=%s",
            (owner_id, project_id, milestone_id),
        ).fetchone()
    if row is None:
        raise ProjectMilestoneNotFoundError()


_PROJECT_SUMMARY_SQL = """
    SELECT p.id::text, p.title, p.description, p.objective, p.success_criteria, p.status, p.role, p.updated_at::text,
           COALESCE(ts.total_tasks, 0)::int AS total_tasks,
           COALESCE(ts.completed_tasks, 0)::int AS completed_tasks,
           COALESCE(ts.remaining_tasks, 0)::int AS remaining_tasks,
           COALESCE(ms.milestone_count, 0)::int AS milestone_count,
           CASE WHEN COALESCE(ms.milestone_count, 0) > 0 THEN 'milestone'
                WHEN COALESCE(ts.total_tasks, 0) > 0 THEN 'wbs'
                ELSE 'unscoped' END AS progress_basis,
           CASE WHEN COALESCE(ms.milestone_count, 0) > 0 THEN COALESCE(ms.weighted_progress, 0)
                WHEN COALESCE(ts.total_tasks, 0) > 0 THEN ROUND((ts.completed_tasks::numeric / ts.total_tasks::numeric) * 100)::int
                ELSE 0 END AS progress_percent
    FROM projects p
    LEFT JOIN LATERAL (
        SELECT COUNT(*) FILTER (WHERE t.counts_toward_progress)::int AS total_tasks,
               COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.status='done')::int AS completed_tasks,
               COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.status<>'done')::int AS remaining_tasks
        FROM project_tasks t
        WHERE t.owner_id=%(owner_id)s AND t.project_id=p.id
    ) ts ON true
    LEFT JOIN LATERAL (
        SELECT COUNT(*)::int AS milestone_count,
               ROUND(COALESCE(SUM(m.weight * COALESCE(mt.progress_percent, 0)), 0)::numeric / NULLIF(SUM(m.weight), 0))::int AS weighted_progress
        FROM project_milestones m
        LEFT JOIN LATERAL (
            SELECT CASE WHEN COUNT(*)=0 THEN 0
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
        status=row["status"], role=row.get("role") or "", total_tasks=row.get("total_tasks") or 0,
        completed_tasks=row.get("completed_tasks") or 0, remaining_tasks=row.get("remaining_tasks") or 0,
        milestone_count=row.get("milestone_count") or 0, progress_basis=row.get("progress_basis") or "unscoped",
        progress_percent=row.get("progress_percent") or 0, updated_at=row["updated_at"],
    )


def _milestone_from_row(row) -> ProjectMilestone:
    return ProjectMilestone(
        id=row["id"], project_id=row["project_id"], milestone_key=row["milestone_key"], title=row["title"],
        description=row.get("description") or "", acceptance_criteria=row.get("acceptance_criteria") or "",
        weight=row["weight"], sort_order=row.get("sort_order") or 0, total_tasks=row.get("total_tasks") or 0,
        completed_tasks=row.get("completed_tasks") or 0, progress_percent=row.get("progress_percent") or 0,
        updated_at=row["updated_at"],
    )


def _task_from_row(row) -> ProjectTask:
    return ProjectTask(
        id=row["id"], project_id=row["project_id"], title=row["title"], description=row.get("description") or "",
        status=row["status"], priority=row.get("priority") or "medium", due_date=row.get("due_date"),
        milestone_id=row.get("milestone_id"), counts_toward_progress=row.get("counts_toward_progress", True),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )
