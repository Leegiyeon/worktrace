from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.db.connection import connect

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/health/ready")
def readiness_check() -> dict[str, str]:
    settings = get_settings()

    try:
        with connect(settings, row_factory=None) as connection:
            connection.execute("SELECT 1")
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from error

    return {
        "status": "ready",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
