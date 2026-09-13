import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.milestone_evidence import MilestoneEvidenceSummary, MilestoneValidationUpdate
from app.services.milestone_evidence import (
    MilestoneValidationBlockedError,
    MilestoneValidationTaskNotFoundError,
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
            payload.status,
        )
    except ProjectMilestoneNotFoundError as exc:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_MILESTONE_NOT_FOUND",
            "Project milestone was not found.",
        ) from exc
    except MilestoneValidationTaskNotFoundError as exc:
        raise http_error(
            status.HTTP_404_NOT_FOUND,
            "MILESTONE_VALIDATION_TASK_NOT_FOUND",
            "검증 WBS를 찾을 수 없습니다.",
        ) from exc
    except MilestoneValidationBlockedError as exc:
        raise http_error(
            status.HTTP_409_CONFLICT,
            "MILESTONE_VALIDATION_BLOCKED",
            "최신 AI 검토가 완료 후보가 아니거나 검토 이후 Evidence·WBS·성취 기준이 변경되었습니다. 다시 AI 검토한 뒤 완료해 주세요.",
        ) from exc
    except psycopg.Error as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "Database is unavailable.",
        ) from exc
