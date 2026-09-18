import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.project_plans import ProjectPlan, ProjectPlanApprove
from app.services.project_plans import (
    ProjectPlanConflictError,
    ProjectPlanNotFoundError,
    ProjectPlanPolicyError,
    ProjectPlanRequestConflictError,
    approve_project_plan,
    get_project_plan,
)

router = APIRouter(prefix="/projects", tags=["project-plans"])


@router.get("/{project_id}/plan", response_model=ProjectPlan)
def get_plan(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectPlan:
    try:
        return get_project_plan(settings, owner_id, project_id)
    except ProjectPlanNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/plan", response_model=ProjectPlan)
def post_plan(
    project_id: UUID,
    payload: ProjectPlanApprove,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ProjectPlan:
    try:
        return approve_project_plan(settings, owner_id, project_id, payload)
    except ProjectPlanNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except ProjectPlanRequestConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_PLAN_REQUEST_CONFLICT", "Plan approval request id was already used with a different payload.") from exc
    except ProjectPlanConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_PLAN_VERSION_CONFLICT", "Project plan version or context fingerprint does not match.") from exc
    except ProjectPlanPolicyError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_PLAN_POLICY_BLOCKED", "Project plan policy requirements are not satisfied.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
