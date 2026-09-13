import hashlib
import json
from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect


def build_milestone_review_context_fingerprint(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    milestone_id: UUID,
) -> str:
    with connect(settings) as connection:
        milestone = connection.execute(
            """
            SELECT title, description, acceptance_criteria
            FROM project_milestones
            WHERE owner_id=%s AND project_id=%s AND id=%s
            """,
            (owner_id, project_id, milestone_id),
        ).fetchone()
        task_rows = connection.execute(
            """
            SELECT id::text, title, status, priority, COALESCE(description, '') AS description,
                   COALESCE(source_provider, '') AS source_provider,
                   COALESCE(source_key, '') AS source_key,
                   counts_toward_progress
            FROM project_tasks
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
            ORDER BY id
            """,
            (owner_id, project_id, milestone_id),
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT github_commit_id::text AS id
            FROM project_milestone_evidence
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
            ORDER BY github_commit_id
            """,
            (owner_id, project_id, milestone_id),
        ).fetchall()

    payload = {
        "milestone": dict(milestone) if milestone else None,
        "tasks": [dict(row) for row in task_rows],
        "commit_evidence_ids": [row["id"] for row in evidence_rows],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def latest_review_allows_completion(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    milestone_id: UUID,
) -> bool:
    current_fingerprint = build_milestone_review_context_fingerprint(settings, owner_id, project_id, milestone_id)
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT verdict, context_fingerprint
            FROM project_milestone_reviews
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
            ORDER BY reviewed_at DESC
            LIMIT 1
            """,
            (owner_id, project_id, milestone_id),
        ).fetchone()
    return bool(
        row
        and row["verdict"] == "ready_candidate"
        and row.get("context_fingerprint")
        and row["context_fingerprint"] == current_fingerprint
    )
