from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.github_items import (
    GitHubItem,
    GitHubItemCounts,
    GitHubItemDecisionRequest,
    GitHubItemListResponse,
    GitHubItemReviewFilter,
)
from app.services.projects import ProjectNotFoundError


BODY_RESPONSE_LIMIT = 20_000


class GitHubItemNotFoundError(Exception):
    pass


class GitHubItemConflictError(Exception):
    pass


class GitHubItemInvalidDecisionError(Exception):
    pass


def list_github_items(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    review_status: GitHubItemReviewFilter = "pending",
    limit: int = 20,
    offset: int = 0,
) -> GitHubItemListResponse:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    status_clause = "" if review_status == "all" else "AND gi.review_status = %(review_status)s"
    params: dict[str, Any] = {
        "owner_id": owner_id,
        "project_id": project_id,
        "review_status": review_status,
        "limit": limit,
        "offset": offset,
    }
    with connect(settings) as connection:
        if connection.info.transaction_status != TransactionStatus.IDLE:
            counts_row, total, rows = _list_github_item_rows(connection, owner_id, project_id, params, status_clause)
            return GitHubItemListResponse(
                items=[_item_from_row(row) for row in rows],
                total=total,
                counts=GitHubItemCounts(**(counts_row or {})),
            )
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            counts_row, total, rows = _list_github_item_rows(connection, owner_id, project_id, params, status_clause)
    return GitHubItemListResponse(
        items=[_item_from_row(row) for row in rows],
        total=total,
        counts=GitHubItemCounts(**(counts_row or {})),
    )


def _list_github_item_rows(connection, owner_id: str, project_id: UUID, params: dict[str, Any], status_clause: str):
    source = connection.execute(
        "SELECT id FROM repository_sources WHERE owner_id=%s AND project_id=%s AND provider='github'",
        (owner_id, project_id),
    ).fetchone()
    if source is None:
        project = connection.execute("SELECT id FROM projects WHERE owner_id=%s AND id=%s", (owner_id, project_id)).fetchone()
        if project is None:
            raise ProjectNotFoundError()
    counts_row = connection.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE gi.review_status='pending')::int AS pending,
          COUNT(*) FILTER (WHERE gi.review_status='adopted')::int AS adopted,
          COUNT(*) FILTER (WHERE gi.review_status='ignored')::int AS ignored
        FROM github_items gi
        JOIN repository_sources rs ON rs.owner_id=gi.owner_id AND rs.id=gi.repository_source_id
        WHERE gi.owner_id=%(owner_id)s AND rs.project_id=%(project_id)s
        """,
        params,
    ).fetchone()
    total = connection.execute(
        f"""
        SELECT COUNT(*)::int AS total
        FROM github_items gi
        JOIN repository_sources rs ON rs.owner_id=gi.owner_id AND rs.id=gi.repository_source_id
        WHERE gi.owner_id=%(owner_id)s AND rs.project_id=%(project_id)s {status_clause}
        """,
        params,
    ).fetchone()["total"]
    rows = connection.execute(
        f"""
        SELECT gi.id::text, gi.number, gi.kind, gi.payload, gi.source_updated_at,
               encode(digest(gi.payload::text, 'sha256'), 'hex') AS source_digest,
               gi.collected_at, gi.review_status, gi.version, gi.task_id::text,
               t.title AS task_title, gi.reviewed_at, gi.decision_source_updated_at, gi.decision_source_digest
        FROM github_items gi
        JOIN repository_sources rs ON rs.owner_id=gi.owner_id AND rs.id=gi.repository_source_id
        LEFT JOIN project_tasks t ON t.owner_id=gi.owner_id AND t.id=gi.task_id
        WHERE gi.owner_id=%(owner_id)s AND rs.project_id=%(project_id)s {status_clause}
        ORDER BY gi.source_updated_at DESC, gi.collected_at DESC, gi.number DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return counts_row, total, rows


def decide_github_item(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    item_id: UUID,
    payload: GitHubItemDecisionRequest,
) -> GitHubItem:
    request_snapshot = _canonical_request(payload)
    with connect(settings) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"github-item-decision:{owner_id}:{payload.request_id}",),
            )
            existing_audit = connection.execute(
                """
                SELECT github_item_id::text, request_payload
                FROM github_item_decision_audits
                WHERE owner_id=%s AND request_id=%s
                """,
                (owner_id, payload.request_id),
            ).fetchone()
            if existing_audit is not None:
                if existing_audit["request_payload"] != request_snapshot or str(existing_audit["github_item_id"]) != str(item_id):
                    raise GitHubItemConflictError()
                try:
                    return _get_item_for_update(connection, owner_id, project_id, UUID(str(existing_audit["github_item_id"])), lock=False)
                except GitHubItemNotFoundError as exc:
                    raise GitHubItemConflictError() from exc

            item = _get_item_row(connection, owner_id, project_id, item_id, lock=True)
            if item is None:
                project = connection.execute("SELECT id FROM projects WHERE owner_id=%s AND id=%s", (owner_id, project_id)).fetchone()
                if project is None:
                    raise ProjectNotFoundError()
                raise GitHubItemNotFoundError()
            if item["version"] != payload.expected_version:
                raise GitHubItemConflictError()
            if _normalize_dt(item["source_updated_at"]) != _normalize_dt(payload.expected_source_updated_at):
                raise GitHubItemConflictError()

            previous_status = item["review_status"]
            previous_task_id = item.get("task_id")
            next_status = previous_status
            next_task_id = previous_task_id
            reviewed_at = "now()"

            if payload.action == "create":
                if previous_status == "ignored" or (previous_status == "adopted" and previous_task_id is not None):
                    raise GitHubItemConflictError()
                title = (payload.title or "").strip()
                if not title:
                    raise GitHubItemInvalidDecisionError()
                task_row = connection.execute(
                    """
                    INSERT INTO project_tasks (
                        owner_id, project_id, title, description, status, priority,
                        counts_toward_progress, source_provider, source_key
                    ) VALUES (
                        %(owner_id)s, %(project_id)s, %(title)s, %(description)s,
                        'planned', 'medium', %(counts_toward_progress)s,
                        'github-adopted', %(source_key)s
                    )
                    ON CONFLICT (owner_id, source_provider, source_key)
                        WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
                    DO NOTHING
                    RETURNING id::text
                    """,
                    {
                        "owner_id": owner_id,
                        "project_id": project_id,
                        "title": title[:240],
                        "description": _task_description(item),
                        "counts_toward_progress": payload.counts_toward_progress,
                        "source_key": f"github-item:{item['id']}",
                    },
                ).fetchone()
                if task_row is None:
                    task_row = connection.execute(
                        """
                        SELECT id::text FROM project_tasks
                        WHERE owner_id=%s AND source_provider='github-adopted' AND source_key=%s
                        """,
                        (owner_id, f"github-item:{item['id']}"),
                    ).fetchone()
                next_task_id = task_row["id"]
                next_status = "adopted"
            elif payload.action == "link":
                if payload.task_id is None:
                    raise GitHubItemInvalidDecisionError()
                if previous_status == "ignored":
                    raise GitHubItemConflictError()
                if previous_status == "adopted" and previous_task_id is not None:
                    existing_task = connection.execute(
                        "SELECT id FROM project_tasks WHERE owner_id=%s AND project_id=%s AND id=%s",
                        (owner_id, project_id, previous_task_id),
                    ).fetchone()
                    if existing_task is not None:
                        raise GitHubItemConflictError()
                task = connection.execute(
                    "SELECT id::text FROM project_tasks WHERE owner_id=%s AND project_id=%s AND id=%s",
                    (owner_id, project_id, payload.task_id),
                ).fetchone()
                if task is None:
                    raise GitHubItemInvalidDecisionError()
                next_task_id = task["id"]
                next_status = "adopted"
            elif payload.action == "ignore":
                if previous_status != "pending":
                    raise GitHubItemConflictError()
                next_status = "ignored"
                next_task_id = None
            elif payload.action == "restore":
                if previous_status != "ignored":
                    raise GitHubItemConflictError()
                next_status = "pending"
                next_task_id = None
                reviewed_at = "NULL"

            updated = connection.execute(
                f"""
                UPDATE github_items
                SET review_status=%(review_status)s,
                    task_id=%(task_id)s,
                    reviewed_at={reviewed_at},
                    decision_source_updated_at=source_updated_at,
                    decision_source_digest=encode(digest(payload::text, 'sha256'), 'hex'),
                    version=version + 1
                WHERE owner_id=%(owner_id)s AND id=%(item_id)s
                RETURNING id::text, version
                """,
                {"owner_id": owner_id, "item_id": item_id, "review_status": next_status, "task_id": next_task_id},
            ).fetchone()
            connection.execute(
                """
                INSERT INTO github_item_decision_audits (
                    owner_id, github_item_id, request_id, action, request_payload,
                    source_payload, source_version, source_updated_at,
                    previous_review_status, previous_task_id, next_review_status, next_task_id, actor_owner_id
                ) VALUES (
                    %(owner_id)s, %(github_item_id)s, %(request_id)s, %(action)s, %(request_payload)s,
                    %(source_payload)s, %(source_version)s, %(source_updated_at)s,
                    %(previous_review_status)s, %(previous_task_id)s, %(next_review_status)s, %(next_task_id)s, %(actor_owner_id)s
                )
                """,
                {
                    "owner_id": owner_id,
                    "github_item_id": item_id,
                    "request_id": payload.request_id,
                    "action": payload.action,
                    "request_payload": Jsonb(request_snapshot),
                    "source_payload": Jsonb(item["payload"]),
                    "source_version": item["version"],
                    "source_updated_at": item["source_updated_at"],
                    "previous_review_status": previous_status,
                    "previous_task_id": previous_task_id,
                    "next_review_status": next_status,
                    "next_task_id": next_task_id,
                    "actor_owner_id": owner_id,
                },
            )
            connection.execute("UPDATE projects SET updated_at=now() WHERE owner_id=%s AND id=%s", (owner_id, project_id))
            return _get_item_for_update(connection, owner_id, project_id, UUID(str(updated["id"])), lock=False)


def _get_item_for_update(connection, owner_id: str, project_id: UUID, item_id: UUID, *, lock: bool) -> GitHubItem:
    row = _get_item_row(connection, owner_id, project_id, item_id, lock=lock)
    if row is None:
        raise GitHubItemNotFoundError()
    return _item_from_row(row)


def _get_item_row(connection, owner_id: str, project_id: UUID, item_id: UUID, *, lock: bool):
    lock_clause = "FOR UPDATE OF gi" if lock else ""
    return connection.execute(
        f"""
        SELECT gi.id::text, gi.number, gi.kind, gi.payload, gi.source_updated_at,
               encode(digest(gi.payload::text, 'sha256'), 'hex') AS source_digest,
               gi.collected_at, gi.review_status, gi.version, gi.task_id::text,
               t.title AS task_title, gi.reviewed_at, gi.decision_source_updated_at, gi.decision_source_digest
        FROM github_items gi
        JOIN repository_sources rs ON rs.owner_id=gi.owner_id AND rs.id=gi.repository_source_id
        LEFT JOIN project_tasks t ON t.owner_id=gi.owner_id AND t.id=gi.task_id
        WHERE gi.owner_id=%s AND rs.project_id=%s AND gi.id=%s
        {lock_clause}
        """,
        (owner_id, project_id, item_id),
    ).fetchone()


def _item_from_row(row) -> GitHubItem:
    payload = row.get("payload") or {}
    body = str(payload.get("body") or "")
    body_truncated = len(body) > BODY_RESPONSE_LIMIT
    if body_truncated:
        body = body[:BODY_RESPONSE_LIMIT] + "\n[truncated]"
    source_updated_at = row.get("source_updated_at")
    decision_source_updated_at = row.get("decision_source_updated_at")
    decision_source_digest = row.get("decision_source_digest")
    source_digest = row.get("source_digest")
    return GitHubItem(
        id=row["id"],
        number=row["number"],
        kind=row["kind"],
        title=str(payload.get("title") or ""),
        body=body,
        body_truncated=body_truncated,
        url=_safe_github_url(payload.get("html_url")),
        external_state=str(payload.get("state") or ""),
        source_updated_at=_isoformat(source_updated_at),
        collected_at=_isoformat(row["collected_at"]),
        review_status=row["review_status"],
        version=row.get("version") or 0,
        task_id=row.get("task_id"),
        task_title=row.get("task_title"),
        reviewed_at=_isoformat(row.get("reviewed_at")) if row.get("reviewed_at") else None,
        source_changed=bool(
            decision_source_updated_at
            and (
                _normalize_dt(decision_source_updated_at) != _normalize_dt(source_updated_at)
                or (decision_source_digest is not None and source_digest is not None and decision_source_digest != source_digest)
            )
        ),
    )


def _safe_github_url(value: Any) -> str:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return ""
    return parsed.geturl()


def _task_description(row) -> str:
    payload = row.get("payload") or {}
    parts = [f"GitHub {row['kind']} #{row['number']}"]
    url = _safe_github_url(payload.get("html_url"))
    if url:
        parts.append(url)
    body = str(payload.get("body") or "")
    if body:
        parts.append(body[:BODY_RESPONSE_LIMIT])
    return "\n\n".join(parts)


def _canonical_request(payload: GitHubItemDecisionRequest) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    if data.get("title") is not None:
        data["title"] = data["title"].strip()
    return json.loads(json.dumps(data, sort_keys=True, separators=(",", ":")))


def _normalize_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        if len(text) >= 3 and text[-3] in {"+", "-"} and text[-2:].isdigit():
            text = f"{text}:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _isoformat(value: Any) -> str:
    return _normalize_dt(value).isoformat()
