from contextlib import contextmanager
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Response, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.report_snapshots import ReportSnapshotCreate, ReportSnapshotDetail, ReportSnapshotPage
from app.services import report_snapshots
from app.services.weekly_report import ReportConfigurationError, ReportDataContractError

router = APIRouter(prefix="/reports/snapshots", tags=["reports"])


@contextmanager
def snapshot_errors():
    try:
        yield
    except report_snapshots.ReportSnapshotNotFoundError as exc:
        raise http_error(404, "REPORT_SNAPSHOT_NOT_FOUND", "보관한 리포트를 찾을 수 없습니다.") from exc
    except report_snapshots.ReportSnapshotConflictError as exc:
        raise http_error(409, "REPORT_SNAPSHOT_REQUEST_CONFLICT", "다른 생성 조건에 사용한 요청입니다. 새 요청으로 생성하세요.") from exc
    except report_snapshots.ReportSnapshotIntegrityError as exc:
        raise http_error(500, "REPORT_SNAPSHOT_INTEGRITY_ERROR", "보관한 리포트의 무결성을 확인할 수 없습니다.") from exc
    except ReportConfigurationError as exc:
        raise http_error(503, "INVALID_REPORT_TIMEZONE", "리포트 시간대 설정을 확인하세요.") from exc
    except ReportDataContractError as exc:
        raise http_error(500, "REPORT_DATA_CONTRACT_INVALID", "저장된 자료의 상태 또는 유형을 확인하세요.") from exc
    except psycopg.Error as exc:
        raise http_error(503, "DATABASE_UNAVAILABLE", "리포트 저장소에 연결할 수 없습니다. DB와 마이그레이션 상태를 확인하세요.") from exc


@router.post("", response_model=ReportSnapshotDetail)
def create_snapshot(
    request: ReportSnapshotCreate,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ReportSnapshotDetail:
    with snapshot_errors():
        return report_snapshots.create_report_snapshot(settings, owner_id, request)


@router.get("", response_model=ReportSnapshotPage)
def list_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ReportSnapshotPage:
    with snapshot_errors():
        return report_snapshots.list_report_snapshots(settings, owner_id, limit=limit, offset=offset)


@router.get("/{snapshot_id}", response_model=ReportSnapshotDetail)
def get_snapshot(
    snapshot_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ReportSnapshotDetail:
    with snapshot_errors():
        return report_snapshots.get_report_snapshot(settings, owner_id, snapshot_id)


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(
    snapshot_id: UUID,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> Response:
    with snapshot_errors():
        report_snapshots.delete_report_snapshot(settings, owner_id, snapshot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
