from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.projects import (
    ProjectCreate,
    ProjectSummary,
    ProjectTask,
    ProjectTaskCreate,
    ProjectTaskUpdate,
    ProjectUpdate,
    RepositorySource,
    RepositorySourceCreate,
    GitHubCommit,
)


class ProjectNotFoundError(Exception):
    pass


class ProjectTaskNotFoundError(Exception):
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
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.title ASC
            """,
            {"owner_id": owner_id},
        ).fetchall()

    return [_project_from_row(row) for row in rows]


def create_project(settings: Settings, owner_id: str, payload: ProjectCreate) -> ProjectSummary:
    with connect(settings) as connection:
        row = connection.execute(
            """
            INSERT INTO projects (owner_id, title, description, status, role)
            VALUES (%(owner_id)s, %(title)s, %(description)s, %(status)s, %(role)s)
            RETURNING id
            """,
            {
                "owner_id": owner_id,
                "title": payload.title,
                "description": payload.description,
                "status": payload.status,
                "role": payload.role,
            },
        ).fetchone()

    return get_project(settings, owner_id, UUID(str(row["id"])))


def get_project(settings: Settings, owner_id: str, project_id: UUID) -> ProjectSummary:
    with connect(settings) as connection:
        row = connection.execute(
            _PROJECT_SUMMARY_SQL + """
            WHERE p.owner_id = %(owner_id)s AND p.id = %(project_id)s
            GROUP BY p.id
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()

    if row is None:
        raise ProjectNotFoundError()
    return _project_from_row(row)


def update_project(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectUpdate) -> ProjectSummary:
    existing = get_project(settings, owner_id, project_id)
    next_values = {
        "title": payload.title if payload.title is not None else existing.title,
        "description": payload.description if payload.description is not None else existing.description,
        "status": payload.status if payload.status is not None else existing.status,
        "role": payload.role if payload.role is not None else existing.role,
    }
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE projects
            SET title = %(title)s,
                description = %(description)s,
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


def list_project_tasks(settings: Settings, owner_id: str, project_id: UUID) -> list[ProjectTask]:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT t.id::text, t.project_id::text, t.title, t.description, t.status,
                   t.priority, t.due_date::text, t.created_at::text, t.updated_at::text
            FROM project_tasks t
            JOIN projects p ON p.id = t.project_id AND p.owner_id = %(owner_id)s
            WHERE t.owner_id = %(owner_id)s AND t.project_id = %(project_id)s
            ORDER BY
              CASE t.status
                WHEN 'in_progress' THEN 1
                WHEN 'planned' THEN 2
                WHEN 'on_hold' THEN 3
                WHEN 'done' THEN 4
                ELSE 5
              END,
              CASE t.priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
              END,
              t.due_date ASC NULLS LAST,
              t.updated_at DESC,
              t.title ASC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()

    return [_task_from_row(row) for row in rows]


def create_project_task(settings: Settings, owner_id: str, project_id: UUID, payload: ProjectTaskCreate) -> ProjectTask:
    _ensure_project_exists(settings, owner_id, project_id)
    with connect(settings) as connection:
        row = connection.execute(
            """
            INSERT INTO project_tasks (owner_id, project_id, title, description, status, priority, due_date)
            VALUES (%(owner_id)s, %(project_id)s, %(title)s, %(description)s, %(status)s, %(priority)s, %(due_date)s)
            RETURNING id::text, project_id::text, title, description, status, priority, due_date::text,
                      created_at::text, updated_at::text
            """,
            {
                "owner_id": owner_id,
                "project_id": project_id,
                "title": payload.title,
                "description": payload.description,
                "status": payload.status,
                "priority": payload.priority,
                "due_date": payload.due_date,
            },
        ).fetchone()
        connection.execute(
            "UPDATE projects SET updated_at = now() WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        )

    return _task_from_row(row)


def update_project_task(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    task_id: UUID,
    payload: ProjectTaskUpdate,
) -> ProjectTask:
    existing = get_project_task(settings, owner_id, project_id, task_id)
    updates = payload.model_dump(exclude_unset=True)
    next_values = {
        "title": updates.get("title", existing.title),
        "description": updates.get("description", existing.description),
        "status": updates.get("status", existing.status),
        "priority": updates.get("priority", existing.priority),
        "due_date": updates.get("due_date", existing.due_date),
    }
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE project_tasks t
            SET title = %(title)s,
                description = %(description)s,
                status = %(status)s,
                priority = %(priority)s,
                due_date = %(due_date)s,
                updated_at = now()
            FROM projects p
            WHERE p.id = t.project_id
              AND p.owner_id = %(owner_id)s
              AND t.owner_id = %(owner_id)s
              AND t.project_id = %(project_id)s
              AND t.id = %(task_id)s
            RETURNING t.id::text, t.project_id::text, t.title, t.description, t.status, t.priority,
                      t.due_date::text, t.created_at::text, t.updated_at::text
            """,
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id, **next_values},
        ).fetchone()
        if row is None:
            raise ProjectTaskNotFoundError()
        connection.execute(
            "UPDATE projects SET updated_at = now() WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        )

    return _task_from_row(row)


def delete_project_task(settings: Settings, owner_id: str, project_id: UUID, task_id: UUID) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            """
            DELETE FROM project_tasks t
            USING projects p
            WHERE p.id = t.project_id
              AND p.owner_id = %(owner_id)s
              AND t.owner_id = %(owner_id)s
              AND t.project_id = %(project_id)s
              AND t.id = %(task_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id},
        )
        if result.rowcount == 0:
            raise ProjectTaskNotFoundError()
        connection.execute(
            "UPDATE projects SET updated_at = now() WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        )


def get_project_task(settings: Settings, owner_id: str, project_id: UUID, task_id: UUID) -> ProjectTask:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT t.id::text, t.project_id::text, t.title, t.description, t.status,
                   t.priority, t.due_date::text, t.created_at::text, t.updated_at::text
            FROM project_tasks t
            JOIN projects p ON p.id = t.project_id AND p.owner_id = %(owner_id)s
            WHERE t.owner_id = %(owner_id)s
              AND t.project_id = %(project_id)s
              AND t.id = %(task_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id, "task_id": task_id},
        ).fetchone()
    if row is None:
        raise ProjectTaskNotFoundError()
    return _task_from_row(row)


def _ensure_project_exists(settings: Settings, owner_id: str, project_id: UUID) -> None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id FROM projects WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
    if row is None:
        raise ProjectNotFoundError()


_PROJECT_SUMMARY_SQL = """
    SELECT p.id::text,
           p.title,
           p.description,
           p.status,
           p.role,
           p.updated_at::text,
           COUNT(t.id)::int AS total_tasks,
           COUNT(t.id) FILTER (WHERE t.status = 'done')::int AS completed_tasks,
           COUNT(t.id) FILTER (WHERE t.status <> 'done')::int AS remaining_tasks,
           CASE
             WHEN COUNT(t.id) = 0 THEN 0
             ELSE ROUND((COUNT(t.id) FILTER (WHERE t.status = 'done')::numeric / COUNT(t.id)::numeric) * 100)::int
           END AS progress_percent
    FROM projects p
    LEFT JOIN project_tasks t ON t.project_id = p.id AND t.owner_id = %(owner_id)s
"""


def _project_from_row(row) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"],
        title=row["title"],
        description=row.get("description") or "",
        status=row["status"],
        role=row.get("role") or "",
        total_tasks=row.get("total_tasks") or 0,
        completed_tasks=row.get("completed_tasks") or 0,
        remaining_tasks=row.get("remaining_tasks") or 0,
        progress_percent=row.get("progress_percent") or 0,
        updated_at=row["updated_at"],
    )


def _task_from_row(row) -> ProjectTask:
    return ProjectTask(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        description=row.get("description") or "",
        status=row["status"],
        priority=row.get("priority") or "medium",
        due_date=row.get("due_date"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
