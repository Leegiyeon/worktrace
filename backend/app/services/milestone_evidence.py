from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.milestone_evidence import MilestoneEvidenceItem, MilestoneEvidenceSummary, MilestoneWorkItem
from app.services.projects import ProjectMilestoneNotFoundError


class MilestoneValidationTaskNotFoundError(Exception):
    pass


class MilestoneValidationBlockedError(Exception):
    pass


def get_milestone_evidence(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    milestone_id: UUID,
) -> MilestoneEvidenceSummary:
    with connect(settings) as connection:
        milestone = connection.execute(
            """
            SELECT id::text, acceptance_criteria
            FROM project_milestones
            WHERE owner_id=%s AND project_id=%s AND id=%s
            """,
            (owner_id, project_id, milestone_id),
        ).fetchone()
        if milestone is None:
            raise ProjectMilestoneNotFoundError()

        wbs_rows = connection.execute(
            """
            SELECT id::text, title, status, priority, COALESCE(description, '') AS description,
                   COALESCE(source_provider, '') AS source_provider,
                   COALESCE(source_key, '') AS source_key
            FROM project_tasks
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s AND counts_toward_progress
            ORDER BY
              CASE status WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2 WHEN 'on_hold' THEN 3 WHEN 'done' THEN 4 ELSE 5 END,
              CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
              updated_at DESC
            """,
            (owner_id, project_id, milestone_id),
        ).fetchall()

        commit_rows = connection.execute(
            """
            SELECT c.id::text, c.message, c.url, c.committed_at::text AS occurred_at
            FROM project_milestone_evidence e
            JOIN github_commits c ON c.id=e.github_commit_id
            WHERE e.owner_id=%s AND e.project_id=%s AND e.milestone_id=%s
            ORDER BY c.committed_at DESC NULLS LAST, c.created_at DESC
            LIMIT 20
            """,
            (owner_id, project_id, milestone_id),
        ).fetchall()

        pr_rows = connection.execute(
            """
            SELECT id::text, title, description AS url, updated_at::text AS occurred_at, status
            FROM project_tasks
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
              AND source_provider='github' AND source_key LIKE 'pr:%%'
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            (owner_id, project_id, milestone_id),
        ).fetchall()

        evidence_count = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM project_milestone_evidence e
               WHERE e.owner_id=%s AND e.project_id=%s AND e.milestone_id=%s)
              +
              (SELECT COUNT(*) FROM project_tasks t
               WHERE t.owner_id=%s AND t.project_id=%s AND t.milestone_id=%s
                 AND t.source_provider='github' AND t.source_key LIKE 'pr:%%') AS total
            """,
            (owner_id, project_id, milestone_id, owner_id, project_id, milestone_id),
        ).fetchone()["total"]

    evidence = [
        MilestoneEvidenceItem(
            kind="commit",
            id=row["id"],
            title=(row["message"].splitlines()[0] if row["message"] else "제목 없는 커밋")[:240],
            url=row["url"] or "",
            occurred_at=row.get("occurred_at"),
        )
        for row in commit_rows
    ]
    evidence.extend(
        MilestoneEvidenceItem(
            kind="pull_request",
            id=row["id"],
            title=row["title"],
            url=row.get("url") or "",
            occurred_at=row.get("occurred_at"),
            status=row.get("status") or "evidence",
        )
        for row in pr_rows
    )
    evidence.sort(key=lambda item: item.occurred_at or "", reverse=True)

    work_items = [_work_item_from_row(row) for row in wbs_rows]
    completed_wbs = sum(1 for row in wbs_rows if row["status"] == "done")
    pending = [item for item in work_items if item.status != "done"]
    validation = next((item for item in work_items if item.is_validation_task), None)

    return MilestoneEvidenceSummary(
        milestone_id=milestone["id"],
        acceptance_criteria=milestone.get("acceptance_criteria") or "",
        total_wbs=len(wbs_rows),
        completed_wbs=completed_wbs,
        pending_wbs=pending,
        validation_wbs=validation,
        evidence_count=int(evidence_count or 0),
        recent_evidence=evidence[:20],
    )


def update_milestone_validation_status(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    milestone_id: UUID,
    next_status: str,
) -> MilestoneEvidenceSummary:
    with connect(settings) as connection:
        milestone = connection.execute(
            """
            SELECT id, COALESCE(acceptance_criteria, '') AS acceptance_criteria
            FROM project_milestones
            WHERE owner_id=%s AND project_id=%s AND id=%s
            """,
            (owner_id, project_id, milestone_id),
        ).fetchone()
        if milestone is None:
            raise ProjectMilestoneNotFoundError()

        validation = connection.execute(
            """
            SELECT id
            FROM project_tasks
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
              AND source_provider='derived-github'
              AND source_key='milestone-validation:' || %s::text
            """,
            (owner_id, project_id, milestone_id, milestone_id),
        ).fetchone()
        if validation is None:
            raise MilestoneValidationTaskNotFoundError()

        if next_status == "done":
            substantive_pending = connection.execute(
                """
                SELECT COUNT(*)::int AS total
                FROM project_tasks
                WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
                  AND counts_toward_progress
                  AND status <> 'done'
                  AND NOT (
                    source_provider='derived-github'
                    AND source_key='milestone-validation:' || %s::text
                  )
                """,
                (owner_id, project_id, milestone_id, milestone_id),
            ).fetchone()["total"]
            if substantive_pending > 0 or not milestone["acceptance_criteria"].strip():
                raise MilestoneValidationBlockedError()

        connection.execute(
            """
            UPDATE project_tasks
            SET status=%s, updated_at=now()
            WHERE owner_id=%s AND project_id=%s AND milestone_id=%s
              AND source_provider='derived-github'
              AND source_key='milestone-validation:' || %s::text
            """,
            (next_status, owner_id, project_id, milestone_id, milestone_id),
        )
        connection.execute(
            "UPDATE projects SET updated_at=now() WHERE owner_id=%s AND id=%s",
            (owner_id, project_id),
        )

    return get_milestone_evidence(settings, owner_id, project_id, milestone_id)


def _work_item_from_row(row) -> MilestoneWorkItem:
    source_provider = row.get("source_provider") or ""
    source_key = row.get("source_key") or ""
    return MilestoneWorkItem(
        id=row["id"],
        title=row["title"],
        status=row["status"],
        priority=row["priority"],
        source_provider=source_provider,
        source_key=source_key,
        is_validation_task=(
            source_provider == "derived-github"
            and source_key.startswith("milestone-validation:")
        ),
    )
