from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.work_requests import WorkRequest, WorkRequestCreate, WorkRequestPage
from app.services.projects import ProjectNotFoundError


class WorkRequestConflictError(Exception):
    pass


_SELECT_COLUMNS = """
    id::text, project_id::text, request_id, title, body,
    desired_outcome, constraints, source, created_at::text
"""


def create_work_request(
    settings: Settings, owner_id: str, project_id: UUID, payload: WorkRequestCreate
) -> WorkRequest:
    with connect(settings) as connection:
        with connection.transaction():
            # Keep the same lock order as other project-scoped writes and prevent
            # deleting a project between the ownership check and insert.
            project = connection.execute(
                "SELECT id FROM projects WHERE owner_id=%s AND id=%s FOR UPDATE",
                (owner_id, project_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError()
            connection.execute(
                """
                INSERT INTO work_requests (
                    owner_id, project_id, request_id, title, body,
                    desired_outcome, constraints, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (owner_id, request_id) DO NOTHING
                """,
                (
                    owner_id, project_id, payload.request_id, payload.title,
                    payload.body, payload.desired_outcome, payload.constraints, payload.source,
                ),
            )
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM work_requests WHERE owner_id=%s AND request_id=%s",
                (owner_id, payload.request_id),
            ).fetchone()
            if row is None:
                raise WorkRequestConflictError()
            if str(row["project_id"]) != str(project_id) or any(
                row[field] != getattr(payload, field)
                for field in ("title", "body", "desired_outcome", "constraints", "source")
            ):
                raise WorkRequestConflictError()
    return WorkRequest(**row)


def list_work_requests(
    settings: Settings, owner_id: str, project_id: UUID, limit: int = 20, offset: int = 0
) -> WorkRequestPage:
    with connect(settings) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            project = connection.execute(
                "SELECT id FROM projects WHERE owner_id=%s AND id=%s",
                (owner_id, project_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError()
            total = connection.execute(
                "SELECT COUNT(*)::int AS total FROM work_requests WHERE owner_id=%s AND project_id=%s",
                (owner_id, project_id),
            ).fetchone()["total"]
            rows = connection.execute(
                f"""SELECT {_SELECT_COLUMNS} FROM work_requests
                    WHERE owner_id=%s AND project_id=%s
                    ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
                (owner_id, project_id, limit, offset),
            ).fetchall()
    return WorkRequestPage(
        items=[WorkRequest(**row) for row in rows], total=total, limit=limit, offset=offset
    )
