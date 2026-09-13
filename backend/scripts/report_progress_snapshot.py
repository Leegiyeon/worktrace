from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.connection import connect
from app.services.projects import list_project_milestones, list_projects


def main() -> None:
    settings = get_settings()
    owner_id = settings.default_owner_id

    print("=== Worktrace progress snapshot ===")
    projects = list_projects(settings, owner_id)
    with connect(settings) as connection:
        for project in projects:
            task_stats = connection.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE source_provider='derived-github')::int AS synthetic_total,
                    COUNT(*) FILTER (WHERE source_provider='derived-github' AND status='done')::int AS synthetic_done,
                    COUNT(*) FILTER (WHERE source_provider='github' AND source_key LIKE 'issue:%')::int AS github_issue_wbs
                FROM project_tasks
                WHERE owner_id=%s AND project_id=%s
                """,
                (owner_id, project.id),
            ).fetchone()
            evidence_count = connection.execute(
                "SELECT COUNT(*)::int AS count FROM project_milestone_evidence WHERE owner_id=%s AND project_id=%s",
                (owner_id, project.id),
            ).fetchone()["count"]

            basis = {
                "milestone": "milestone",
                "wbs": "wbs-fallback",
                "unscoped": "unscoped",
            }.get(project.progress_basis, project.progress_basis)
            progress_text = "산정 전" if project.progress_basis == "unscoped" else f"{project.progress_percent}%"
            print(
                f"PROJECT {project.title}: progress={progress_text} basis={basis} "
                f"wbs={project.completed_tasks}/{project.total_tasks} remaining={project.remaining_tasks} "
                f"milestones={project.milestone_count} evidence={evidence_count} "
                f"derived_wbs={task_stats['synthetic_done']}/{task_stats['synthetic_total']} "
                f"github_issue_wbs={task_stats['github_issue_wbs']}"
            )

            for milestone in list_project_milestones(settings, owner_id, project.id):
                if milestone.total_tasks == 0:
                    continue
                print(
                    f"  MILESTONE {milestone.title}: progress={milestone.progress_percent}% "
                    f"wbs={milestone.completed_tasks}/{milestone.total_tasks} weight={milestone.weight}%"
                )
    print("=== End progress snapshot ===")


if __name__ == "__main__":
    main()
