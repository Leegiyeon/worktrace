from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.report_snapshots import (
    ReportSnapshotCreate,
    ReportSnapshotDetail,
    ReportSnapshotPage,
    ReportSnapshotSummary,
)
from app.schemas.reports import AutoReportRequest, AutoReportResponse
from app.services.auto_report import generate_auto_report


SCHEMA_VERSION = "1"


class ReportSnapshotNotFoundError(Exception):
    pass


class ReportSnapshotConflictError(Exception):
    pass


class ReportSnapshotIntegrityError(Exception):
    pass


def create_report_snapshot(settings: Settings, owner_id: str, request: ReportSnapshotCreate) -> ReportSnapshotDetail:
    request_uuid = UUID(str(request.request_id))
    with connect(settings) as connection:
        with connection.transaction():
            _lock_request(connection, owner_id, request_uuid)
            existing = _find_by_request_id(connection, owner_id, request_uuid)
            if existing is not None:
                _ensure_same_period(existing, request)
                return _detail_from_row(existing)

            report_request = AutoReportRequest(
                report_type=request.report_type,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            report = generate_auto_report(settings, owner_id, report_request)
            payload = report.model_dump(mode="json")
            payload_hash = _payload_sha256(payload)
            fingerprint = _activity_fingerprint(payload)
            as_of = _activity_as_of(payload)
            try:
                row = connection.execute(
                    """
                    INSERT INTO report_snapshots (
                        owner_id, request_id, report_type, start_date, end_date, as_of,
                        fingerprint, schema_version, report_payload, payload_sha256
                    )
                    VALUES (
                        %(owner_id)s, %(request_id)s, %(report_type)s, %(start_date)s, %(end_date)s, %(as_of)s,
                        %(fingerprint)s, %(schema_version)s, %(report_payload)s, %(payload_sha256)s
                    )
                    RETURNING id::text, request_id::text, report_type, start_date, end_date, as_of,
                              created_at::text, fingerprint, schema_version, report_payload, payload_sha256
                    """,
                    {
                        "owner_id": owner_id,
                        "request_id": request_uuid,
                        "report_type": request.report_type,
                        "start_date": request.start_date,
                        "end_date": request.end_date,
                        "as_of": as_of,
                        "fingerprint": fingerprint,
                        "schema_version": SCHEMA_VERSION,
                        "report_payload": Jsonb(payload),
                        "payload_sha256": payload_hash,
                    },
                ).fetchone()
            except errors.UniqueViolation as exc:
                raise ReportSnapshotConflictError() from exc
            return _detail_from_row(row)


def list_report_snapshots(settings: Settings, owner_id: str, limit: int = 20, offset: int = 0) -> ReportSnapshotPage:
    bounded_limit = min(max(limit, 1), 100)
    bounded_offset = max(offset, 0)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            WITH total AS (
                SELECT count(*)::int AS total
                FROM report_snapshots
                WHERE owner_id=%(owner_id)s
            ), page AS (
                SELECT id::text, request_id::text, report_type, start_date, end_date, as_of,
                       created_at::text, fingerprint, schema_version
                FROM report_snapshots
                WHERE owner_id=%(owner_id)s
                ORDER BY created_at DESC, id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            )
            SELECT page.id, page.request_id, page.report_type, page.start_date, page.end_date,
                   page.as_of, page.created_at, page.fingerprint, page.schema_version, total.total
            FROM total
            LEFT JOIN page ON true
            ORDER BY page.created_at DESC NULLS LAST, page.id DESC NULLS LAST
            """,
            {"owner_id": owner_id, "limit": bounded_limit, "offset": bounded_offset},
        ).fetchall()
    total = int(rows[0]["total"]) if rows else 0
    return ReportSnapshotPage(
        items=[_summary_from_row(row) for row in rows if row["id"] is not None],
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
    )


def get_report_snapshot(settings: Settings, owner_id: str, snapshot_id: UUID) -> ReportSnapshotDetail:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id::text, request_id::text, report_type, start_date, end_date, as_of,
                   created_at::text, fingerprint, schema_version, report_payload, payload_sha256
            FROM report_snapshots
            WHERE owner_id=%s AND id=%s
            """,
            (owner_id, snapshot_id),
        ).fetchone()
    if row is None:
        raise ReportSnapshotNotFoundError()
    return _detail_from_row(row)


def delete_report_snapshot(settings: Settings, owner_id: str, snapshot_id: UUID) -> None:
    with connect(settings) as connection:
        result = connection.execute(
            "DELETE FROM report_snapshots WHERE owner_id=%s AND id=%s",
            (owner_id, snapshot_id),
        )
    if result.rowcount == 0:
        raise ReportSnapshotNotFoundError()


def _lock_request(connection: Any, owner_id: str, request_id: UUID) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
        (owner_id, str(request_id)),
    )


def _find_by_request_id(connection: Any, owner_id: str, request_id: UUID) -> dict[str, Any] | None:
    return connection.execute(
        """
        SELECT id::text, request_id::text, report_type, start_date, end_date, as_of,
               created_at::text, fingerprint, schema_version, report_payload, payload_sha256
        FROM report_snapshots
        WHERE owner_id=%s AND request_id=%s
        """,
        (owner_id, request_id),
    ).fetchone()


def _ensure_same_period(row: dict[str, Any], request: ReportSnapshotCreate) -> None:
    if row["report_type"] != request.report_type or row["start_date"] != request.start_date or row["end_date"] != request.end_date:
        raise ReportSnapshotConflictError()


def _summary_from_row(row: dict[str, Any]) -> ReportSnapshotSummary:
    try:
        return ReportSnapshotSummary(
            id=row["id"],
            request_id=row["request_id"],
            report_type=row["report_type"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            as_of=row["as_of"],
            created_at=row["created_at"],
            fingerprint=row["fingerprint"],
            schema_version=row["schema_version"],
        )
    except ValidationError as exc:
        raise ReportSnapshotIntegrityError() from exc


def _detail_from_row(row: dict[str, Any]) -> ReportSnapshotDetail:
    try:
        payload = dict(row["report_payload"])
        if _payload_sha256(payload) != row["payload_sha256"]:
            raise ReportSnapshotIntegrityError()
        if payload.get("report_type") != row["report_type"]:
            raise ReportSnapshotIntegrityError()
        if payload.get("start_date") != row["start_date"].isoformat() or payload.get("end_date") != row["end_date"].isoformat():
            raise ReportSnapshotIntegrityError()
        activity = payload.get("activity") or {}
        if activity.get("as_of") != row["as_of"] or activity.get("fingerprint") != row["fingerprint"]:
            raise ReportSnapshotIntegrityError()
        if activity.get("schema_version") != SCHEMA_VERSION or row["schema_version"] != SCHEMA_VERSION:
            raise ReportSnapshotIntegrityError()
        report = AutoReportResponse(**payload)
    except (TypeError, ValueError, ValidationError) as exc:
        raise ReportSnapshotIntegrityError() from exc
    return ReportSnapshotDetail(**_summary_from_row(row).model_dump(), report=report)


def _payload_sha256(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _activity_fingerprint(payload: dict[str, Any]) -> str:
    activity = payload.get("activity") or {}
    fingerprint = activity.get("fingerprint") or ""
    if len(fingerprint) != 64:
        raise ReportSnapshotIntegrityError()
    return fingerprint


def _activity_as_of(payload: dict[str, Any]) -> str:
    activity = payload.get("activity") or {}
    as_of = activity.get("as_of")
    if not as_of:
        raise ReportSnapshotIntegrityError()
    return as_of
