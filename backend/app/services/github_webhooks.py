import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.projects import GitHubDelivery, ProjectGitHubStatus, RepositorySource


class GitHubWebhookNotConfiguredError(Exception):
    pass


class GitHubWebhookSignatureError(Exception):
    pass


class GitHubDeliveryNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class GitHubWebhookResult:
    status: str
    reason: str
    commits_stored: int = 0


def verify_github_signature(settings: Settings, body: bytes, signature: str | None) -> None:
    if not settings.github_webhook_secret:
        raise GitHubWebhookNotConfiguredError()
    if not signature:
        raise GitHubWebhookSignatureError()
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise GitHubWebhookSignatureError()


def ingest_github_event(
    settings: Settings,
    delivery_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> GitHubWebhookResult:
    repository = payload.get("repository") or {}
    repository_id = repository.get("id")
    full_name = str(repository.get("full_name") or "")
    ref = str(payload.get("ref") or "")

    with connect(settings) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%(delivery_id)s, 0))",
            {"delivery_id": delivery_id},
        )
        existing = connection.execute(
            "SELECT status, reason FROM github_deliveries WHERE delivery_id = %(delivery_id)s",
            {"delivery_id": delivery_id},
        ).fetchone()
        if existing:
            return GitHubWebhookResult(status=existing["status"], reason="duplicate_delivery")

        if event_name != "push":
            return _record_ignored(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, "unsupported_event")
        source = connection.execute(
            """
            SELECT id::text, project_id::text, default_branch
            FROM repository_sources
            WHERE owner_id = %(owner_id)s AND provider = 'github' AND repository_id = %(repository_id)s
            """,
            {"owner_id": settings.default_owner_id, "repository_id": repository_id},
        ).fetchone()
        if source is None:
            return _record_ignored(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, "repository_not_linked")
        if ref != f"refs/heads/{source['default_branch']}":
            return _record_ignored(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, "non_default_ref")

        stored = _store_push_commits(connection, settings.default_owner_id, source, payload)

        _record_delivery(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, "processed", "")
        connection.execute(
            "UPDATE projects SET updated_at = now() WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": settings.default_owner_id, "project_id": source["project_id"]},
        )
        return GitHubWebhookResult(status="processed", reason="", commits_stored=stored)


def get_project_github_status(
    settings: Settings,
    owner_id: str,
    project_id: str,
) -> ProjectGitHubStatus:
    with connect(settings) as connection:
        source = connection.execute(
            """
            SELECT id::text, project_id::text, repository_id, full_name, default_branch, updated_at::text
            FROM repository_sources
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s AND provider = 'github'
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
        if source is None:
            return ProjectGitHubStatus()

        summary = connection.execute(
            """
            SELECT
                (SELECT COUNT(*)::int FROM github_commits c
                 WHERE c.owner_id = %(owner_id)s AND c.repository_source_id = %(source_id)s) AS stored_commit_count,
                (SELECT MAX(d.received_at)::text FROM github_deliveries d
                 WHERE d.owner_id = %(owner_id)s AND d.repository_id = %(repository_id)s
                   AND d.status = 'processed') AS last_success_at
            """,
            {"owner_id": owner_id, "source_id": source["id"], "repository_id": source["repository_id"]},
        ).fetchone()
        deliveries = connection.execute(
            """
            SELECT id::text, delivery_id, event_name, ref, status, reason, processing_attempts,
                   received_at::text, last_processed_at::text
            FROM github_deliveries
            WHERE owner_id = %(owner_id)s AND repository_id = %(repository_id)s
            ORDER BY received_at DESC
            LIMIT 20
            """,
            {"owner_id": owner_id, "repository_id": source["repository_id"]},
        ).fetchall()

    return ProjectGitHubStatus(
        repository=RepositorySource(**source),
        stored_commit_count=summary["stored_commit_count"],
        last_success_at=summary["last_success_at"],
        deliveries=[GitHubDelivery(**row) for row in deliveries],
    )


def reprocess_github_delivery(
    settings: Settings,
    owner_id: str,
    project_id: str,
    delivery_id: str,
) -> GitHubWebhookResult:
    with connect(settings) as connection:
        delivery = connection.execute(
            """
            SELECT d.id::text, d.event_name, d.payload, d.processing_attempts,
                   r.id::text AS source_id, r.project_id::text, r.default_branch
            FROM github_deliveries d
            JOIN repository_sources r
              ON r.owner_id = d.owner_id AND r.repository_id = d.repository_id
            WHERE d.owner_id = %(owner_id)s AND r.project_id = %(project_id)s AND d.delivery_id = %(delivery_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id, "delivery_id": delivery_id},
        ).fetchone()
        if delivery is None:
            raise GitHubDeliveryNotFoundError()
        payload = delivery["payload"]
        event_name = delivery["event_name"]
        ref = str(payload.get("ref") or "")
        status = "processed"
        reason = ""
        stored = 0
        if event_name != "push":
            status, reason = "ignored", "unsupported_event"
        elif ref != f"refs/heads/{delivery['default_branch']}":
            status, reason = "ignored", "non_default_ref"
        else:
            stored = _store_push_commits(
                connection,
                owner_id,
                {"id": delivery["source_id"], "project_id": delivery["project_id"]},
                payload,
            )
        connection.execute(
            """
            UPDATE github_deliveries
            SET status = %(status)s, reason = %(reason)s,
                processing_attempts = processing_attempts + 1, last_processed_at = now()
            WHERE owner_id = %(owner_id)s AND id = %(id)s
            """,
            {"owner_id": owner_id, "id": delivery["id"], "status": status, "reason": reason},
        )
        if status == "processed":
            connection.execute(
                "UPDATE projects SET updated_at = now() WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
                {"owner_id": owner_id, "project_id": project_id},
            )
    return GitHubWebhookResult(status=status, reason=reason, commits_stored=stored)


def _store_push_commits(connection, owner_id: str, source: dict[str, Any], payload: dict[str, Any]) -> int:
    stored = 0
    for commit in payload.get("commits") or []:
        sha = commit.get("id") or ""
        if not sha:
            continue
        result = connection.execute(
            """
            INSERT INTO github_commits (
                repository_source_id, project_id, owner_id, sha, message, author_name,
                author_email, committed_at, url, added_paths, modified_paths, removed_paths
            ) VALUES (
                %(source_id)s, %(project_id)s, %(owner_id)s, %(sha)s, %(message)s, %(author_name)s,
                %(author_email)s, %(committed_at)s, %(url)s, %(added)s::jsonb, %(modified)s::jsonb, %(removed)s::jsonb
            )
            ON CONFLICT (owner_id, repository_source_id, sha) DO NOTHING
            """,
            {
                "source_id": source["id"],
                "project_id": source["project_id"],
                "owner_id": owner_id,
                "sha": sha,
                "message": commit.get("message") or "",
                "author_name": (commit.get("author") or {}).get("name") or "",
                "author_email": (commit.get("author") or {}).get("email") or "",
                "committed_at": commit.get("timestamp"),
                "url": commit.get("url") or "",
                "added": json.dumps(commit.get("added") or []),
                "modified": json.dumps(commit.get("modified") or []),
                "removed": json.dumps(commit.get("removed") or []),
            },
        )
        stored += max(result.rowcount, 0)
        if result.rowcount > 0:
            _sync_commit_work_items(connection, owner_id, source["id"], source["project_id"], sha, commit)
    return stored


def _sync_commit_work_items(connection, owner_id: str, source_id: str, project_id: str, sha: str, commit: dict[str, Any]) -> None:
    committed_at = commit.get("timestamp")
    if not committed_at:
        return
    summary = connection.execute(
        """
        SELECT committed_at::date AS log_date, COUNT(*)::int AS commit_count,
               string_agg('- ' || split_part(message, E'\n', 1), E'\n' ORDER BY committed_at) AS content
        FROM github_commits
        WHERE owner_id = %(owner_id)s AND repository_source_id = %(source_id)s
          AND committed_at::date = %(committed_at)s::timestamptz::date
        GROUP BY committed_at::date
        """,
        {"owner_id": owner_id, "source_id": source_id, "committed_at": committed_at},
    ).fetchone()
    if summary is None:
        return
    # Legacy logs may contain edits without an audit trail. Preserve every existing row.
    connection.execute(
        """
        INSERT INTO work_logs (
            owner_id, project_id, log_date, work_type, title, content, decisions,
            next_actions, duration_minutes, source_provider, source_key
        ) VALUES (
            %(owner_id)s, %(project_id)s, %(log_date)s, 'development', %(title)s,
            %(content)s, '기준 브랜치 커밋 근거 수집 시점의 요약',
            '최신 근거는 프로젝트 커밋 목록에서 확인한다.', 0, 'github', %(source_key)s
        )
        ON CONFLICT (owner_id, source_provider, source_key)
            WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
        DO NOTHING
        """,
        {"owner_id": owner_id, "project_id": project_id, "log_date": summary["log_date"],
         "title": f"GitHub 작업 · {summary['commit_count']}개 커밋", "content": summary["content"],
         "source_key": f"day:{source_id}:{summary['log_date']}"},
    )


def _record_ignored(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, reason):
    _record_delivery(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, "ignored", reason)
    return GitHubWebhookResult(status="ignored", reason=reason)


def _record_delivery(connection, settings, delivery_id, event_name, repository_id, full_name, ref, payload, status, reason):
    connection.execute(
        """
        INSERT INTO github_deliveries (
            owner_id, delivery_id, event_name, repository_id, repository_full_name, ref, status, reason, payload
        ) VALUES (
            %(owner_id)s, %(delivery_id)s, %(event_name)s, %(repository_id)s,
            %(full_name)s, %(ref)s, %(status)s, %(reason)s, %(payload)s::jsonb
        )
        """,
        {
            "owner_id": settings.default_owner_id,
            "delivery_id": delivery_id,
            "event_name": event_name,
            "repository_id": repository_id,
            "full_name": full_name,
            "ref": ref,
            "status": status,
            "reason": reason,
            "payload": json.dumps(payload),
        },
    )
