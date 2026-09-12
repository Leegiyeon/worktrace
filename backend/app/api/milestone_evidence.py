import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.milestone_evidence import MilestoneEvidenceSummary
from app.services.milestone_evidence import get_milestone_evidence
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
