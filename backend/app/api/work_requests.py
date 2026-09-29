from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.work_requests import WorkRequest, WorkRequestCreate, WorkRequestPage
from app.services.projects import ProjectNotFoundError
from app.services.work_requests import WorkRequestConflictError, create_work_request, list_work_requests


router = APIRouter(prefix="/projects", tags=["work-requests"])


@router.post("/{project_id}/requests", response_model=WorkRequest, status_code=201)
def post_work_request(
    project_id: UUID,
    payload: WorkRequestCreate,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> WorkRequest:
    try:
        return create_work_request(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise http_error(404, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except WorkRequestConflictError as exc:
        raise http_error(409, "WORK_REQUEST_CONFLICT", "Request id was used with different content.") from exc
    except psycopg.Error as exc:
        raise http_error(503, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/requests", response_model=WorkRequestPage)
def get_work_requests(
    project_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> WorkRequestPage:
    try:
        return list_work_requests(settings, owner_id, project_id, limit, offset)
    except ProjectNotFoundError as exc:
        raise http_error(404, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except psycopg.Error as exc:
        raise http_error(503, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
