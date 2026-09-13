from uuid import UUID

import psycopg

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.ai import (
    MilestoneReviewRequest,
    MilestoneReviewResponse,
    ProjectAnalystRequest,
    ProjectAnalystResponse,
    StoredMilestoneReview,
    WorkLogDraftRequest,
    WorkLogDraftResponse,
)
from app.services.ai_milestone_review import (
    AiMilestoneReviewConfigurationError,
    AiMilestoneReviewGenerationError,
    list_latest_milestone_reviews,
    review_milestone_completion,
)
from app.services.ai_project_analyst import (
    AiProjectAnalystConfigurationError,
    AiProjectAnalystGenerationError,
    analyze_project,
)
from app.services.ai_work_log_draft import (
    AiConfigurationError,
    AiDraftGenerationError,
    AiDraftProjectNotFoundError,
    generate_work_log_draft,
)
from app.services.projects import ProjectMilestoneNotFoundError, ProjectNotFoundError

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/work-log-draft", response_model=WorkLogDraftResponse)
def create_work_log_draft(
    payload: WorkLogDraftRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> WorkLogDraftResponse:
    try:
        return generate_work_log_draft(settings, owner_id, payload)
    except AiConfigurationError as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_CONFIG_MISSING", "AI 설정이 필요합니다.") from exc
    except AiDraftProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.") from exc
    except AiDraftGenerationError as exc:
        raise http_error(status.HTTP_502_BAD_GATEWAY, "AI_DRAFT_FAILED", "AI 초안을 생성하지 못했습니다.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/milestone-review", response_model=MilestoneReviewResponse)
def create_milestone_review(
    payload: MilestoneReviewRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> MilestoneReviewResponse:
    try:
        return review_milestone_completion(settings, owner_id, payload.project_id, payload.milestone_id)
    except AiMilestoneReviewConfigurationError as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_CONFIG_MISSING", "AI 설정이 필요합니다.") from exc
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.") from exc
    except ProjectMilestoneNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_MILESTONE_NOT_FOUND", "마일스톤을 찾을 수 없습니다.") from exc
    except AiMilestoneReviewGenerationError as exc:
        raise http_error(status.HTTP_502_BAD_GATEWAY, "AI_MILESTONE_REVIEW_FAILED", "AI 마일스톤 검토를 완료하지 못했습니다.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/milestone-reviews/{project_id}", response_model=list[StoredMilestoneReview])
def get_latest_milestone_reviews(
    project_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> list[StoredMilestoneReview]:
    try:
        return list_latest_milestone_reviews(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/project-analyst", response_model=ProjectAnalystResponse)
def create_project_analysis(
    payload: ProjectAnalystRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ProjectAnalystResponse:
    try:
        return analyze_project(settings, owner_id, payload.project_id)
    except AiProjectAnalystConfigurationError as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_CONFIG_MISSING", "AI 설정이 필요합니다.") from exc
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.") from exc
    except AiProjectAnalystGenerationError as exc:
        raise http_error(status.HTTP_502_BAD_GATEWAY, "AI_PROJECT_ANALYST_FAILED", "프로젝트 AI 분석을 완료하지 못했습니다.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
