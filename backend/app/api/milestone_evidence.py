import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.milestone_evidence import MilestoneEvidenceSummary, MilestoneValidationUpdate
from app.services.milestone_completion import MilestoneValidationBlockedError, MilestoneConfirmationConflictError
from app.services.milestone_evidence import (
    get_milestone_evidence,
    update_milestone_validation_status,
)
from app.services.projects import ProjectMilestoneNotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "/{project_id}/milestones/{milestone_id}/evidence",
    response_model=MilestoneEvidenceSummary,
)
def get_project_milestone_evidence(
    project_id: UUID,
    milestone_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> MilestoneEvidenceSummary:
    try:
        return get_milestone_evidence(settings, owner_id, project_id, milestone_id)
    except ProjectMilestoneNotFoundError as exc:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_MILESTONE_NOT_FOUND",
            "Project milestone was not found.",
        ) from exc
    except psycopg.Error as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "Database is unavailable.",
        ) from exc


@router.patch(
    "/{project_id}/milestones/{milestone_id}/validation",
    response_model=MilestoneEvidenceSummary,
)
def patch_project_milestone_validation(
    project_id: UUID,
    milestone_id: UUID,
    payload: MilestoneValidationUpdate,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> MilestoneEvidenceSummary:
    try:
        return update_milestone_validation_status(
            settings,
            owner_id,
            project_id,
            milestone_id,
            payload,
        )
    except ProjectMilestoneNotFoundError as exc:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_MILESTONE_NOT_FOUND",
            "Project milestone was not found.",
        ) from exc
    except MilestoneConfirmationConflictError as exc:
        raise http_error(
            status.HTTP_409_CONFLICT,
            "MILESTONE_CONFIRMATION_CONFLICT",
            "성취 기준·업무·근거 또는 확인 이력이 변경되었습니다. 최신 근거를 다시 확인하세요.",
        ) from exc
    except MilestoneValidationBlockedError as exc:
        raise http_error(
            status.HTTP_409_CONFLICT,
            "MILESTONE_VALIDATION_BLOCKED",
            "성취 기준이 없거나 산정 대상 WBS가 미완료입니다. 최신 근거와 업무 상태를 확인하세요.",
        ) from exc
    except psycopg.Error as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "Database is unavailable.",
        ) from exc
