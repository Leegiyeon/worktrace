import psycopg

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.ai import WorkLogDraftRequest, WorkLogDraftResponse
from app.services.ai_work_log_draft import (
    AiConfigurationError,
    AiDraftGenerationError,
    AiDraftProjectNotFoundError,
    generate_work_log_draft,
)

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
