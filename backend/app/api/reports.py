import psycopg
from fastapi import APIRouter, Depends, status

from app.api.errors import http_error
from app.core.config import Settings, get_settings
from app.api.security import require_report_access
from app.schemas.reports import AutoReportRequest, AutoReportResponse, WeeklyReportRequest, WeeklyReportResponse
from app.services.weekly_report import (
    ReportConfigurationError,
    ReportDataContractError,
    build_weekly_report_response,
    fetch_weekly_report_dataset,
)
from app.services.auto_report import generate_auto_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/weekly", response_model=WeeklyReportResponse)
def create_weekly_report(
    request: WeeklyReportRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> WeeklyReportResponse:
    """Generate a grounded Markdown weekly report for one selected period."""

    try:
        dataset = fetch_weekly_report_dataset(settings, request.start_date, request.end_date, owner_id)
    except ReportConfigurationError as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "INVALID_REPORT_TIMEZONE",
            "REPORT_TIMEZONE is invalid. Set it to a valid IANA timezone such as Asia/Seoul.",
        ) from exc
    except ReportDataContractError as exc:
        raise http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "REPORT_DATA_CONTRACT_INVALID",
            "Stored report data violates the expected status/type contract.",
        ) from exc
    except psycopg.Error as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            (
                "Database is unavailable or the report schema is not initialized. "
                "Run `python backend/scripts/init_db.py` or start Docker Compose."
            ),
        ) from exc

    return build_weekly_report_response(dataset, request.start_date, request.end_date)


@router.post("/automatic", response_model=AutoReportResponse)
def create_automatic_report(
    request: AutoReportRequest,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> AutoReportResponse:
    """Generate an internal automatic report from stored work/project records."""

    try:
        return generate_auto_report(settings, owner_id, request)
    except ReportConfigurationError as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "INVALID_REPORT_TIMEZONE",
            "REPORT_TIMEZONE is invalid. Set it to a valid IANA timezone such as Asia/Seoul.",
        ) from exc
    except ReportDataContractError as exc:
        raise http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "REPORT_DATA_CONTRACT_INVALID",
            "Stored report data violates the expected status/type contract.",
        ) from exc
    except psycopg.Error as exc:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            (
                "Database is unavailable or the report schema is not initialized. "
                "Run `python backend/scripts/init_db.py` or start Docker Compose."
            ),
        ) from exc
