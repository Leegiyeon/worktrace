from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.github_items import GitHubItem, GitHubItemDecisionRequest, GitHubItemListResponse, GitHubItemReviewFilter
from app.services.github_items import (
    GitHubItemConflictError,
    GitHubItemInvalidDecisionError,
    GitHubItemNotFoundError,
    decide_github_item,
    list_github_items,
)
from app.services.projects import ProjectNotFoundError


router = APIRouter(prefix="/projects", tags=["github-items"])


@router.get("/{project_id}/github-items", response_model=GitHubItemListResponse)
def get_project_github_items(
    project_id: UUID,
    review_status: GitHubItemReviewFilter = "pending",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> GitHubItemListResponse:
    try:
        return list_github_items(settings, owner_id, project_id, review_status, limit, offset)
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/github-items/{item_id}/decision", response_model=GitHubItem)
def post_project_github_item_decision(
    project_id: UUID,
    item_id: UUID,
    payload: GitHubItemDecisionRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> GitHubItem:
    try:
        return decide_github_item(settings, owner_id, project_id, item_id, payload)
    except ProjectNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.") from exc
    except GitHubItemNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "GITHUB_ITEM_NOT_FOUND", "GitHub item was not found.") from exc
    except GitHubItemConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "GITHUB_ITEM_DECISION_CONFLICT", "GitHub item decision is stale or conflicts with current state.") from exc
    except GitHubItemInvalidDecisionError as exc:
        raise http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "GITHUB_ITEM_DECISION_INVALID", "GitHub item decision payload is invalid for the current item state.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
