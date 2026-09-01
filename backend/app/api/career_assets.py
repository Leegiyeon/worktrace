import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.career_assets import (
    CareerAsset,
    CareerAssetGenerateRequest,
    CareerAssetUpdateRequest,
)
from app.services.career_assets import (
    CareerAssetNotFoundError,
    CareerAssetProjectNotFoundError,
    generate_project_career_asset,
    list_project_career_assets,
    update_project_career_asset,
)

router = APIRouter(prefix="/projects/{project_id}/career-assets", tags=["career-assets"])


def _project_not_found() -> Exception:
    return http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.")


def _career_asset_not_found() -> Exception:
    return http_error(status.HTTP_404_NOT_FOUND, "CAREER_ASSET_NOT_FOUND", "Career asset was not found.")


def _database_unavailable() -> Exception:
    return http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.")


@router.get("", response_model=list[CareerAsset])
def get_career_assets(
    project_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> list[CareerAsset]:
    try:
        return list_project_career_assets(settings, owner_id, project_id)
    except CareerAssetProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise _database_unavailable() from exc


@router.post("/generate", response_model=CareerAsset, status_code=status.HTTP_201_CREATED)
def generate_career_asset(
    project_id: UUID,
    payload: CareerAssetGenerateRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> CareerAsset:
    try:
        return generate_project_career_asset(settings, owner_id, project_id, payload.target_role)
    except CareerAssetProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise _database_unavailable() from exc


@router.patch("/{career_asset_id}", response_model=CareerAsset)
def patch_career_asset(
    project_id: UUID,
    career_asset_id: UUID,
    payload: CareerAssetUpdateRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> CareerAsset:
    try:
        return update_project_career_asset(settings, owner_id, project_id, career_asset_id, payload)
    except CareerAssetProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except CareerAssetNotFoundError as exc:
        raise _career_asset_not_found() from exc
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
