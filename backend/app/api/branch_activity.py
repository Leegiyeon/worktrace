from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.projects import GitHubBranchActivity
from app.services.github_branches import GitHubBranchActivityError, list_project_branch_activity
from app.services.projects import ProjectNotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/branch-activity", response_model=list[GitHubBranchActivity])
def get_project_branch_activity(
    project_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> list[GitHubBranchActivity]:
    try:
        return list_project_branch_activity(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except GitHubBranchActivityError as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "GITHUB_BRANCH_ACTIVITY_UNAVAILABLE",
            "GitHub 브랜치 활동을 불러오지 못했습니다.",
        ) from exc
