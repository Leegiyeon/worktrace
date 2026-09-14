from uuid import uuid4

import pytest

from app.services import projects as project_service
from scripts import sync_github_data


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class ProjectForConnection:
    def __init__(self, status: str):
        self.project_id = str(uuid4())
        self.source_id = str(uuid4())
        self.status = status
        self.queries: list[str] = []

    def execute(self, query, params):
        normalized = " ".join(query.split())
        self.queries.append(normalized)
        if "SELECT project_id::text FROM repository_sources" in normalized:
            return Result({"project_id": self.project_id})
        if "UPDATE projects SET title" in normalized and "status='in_progress'" in normalized:
            self.status = "in_progress"
        return Result(None)


@pytest.mark.parametrize("existing_status", ["done", "on_hold"])
def test_project_for_does_not_reset_existing_project_status(existing_status, monkeypatch) -> None:
    connection = ProjectForConnection(existing_status)
    monkeypatch.setattr(sync_github_data, "ensure_project_blueprint", lambda *args, **kwargs: None)
    metadata = {"id": 123, "full_name": "Owner/repo", "description": "GitHub description", "default_branch": "main"}

    sync_github_data.project_for(connection, "owner", metadata, "repo", "fallback", "developer")
    sync_github_data.project_for(connection, "owner", metadata, "repo", "fallback", "developer")

    assert connection.status == existing_status
    assert all("status='in_progress'" not in query for query in connection.queries)
    assert any("UPDATE projects SET title=%s, description=%s, role=%s" in query for query in connection.queries)


def test_project_summary_exposes_derived_task_count_mapping() -> None:
    project = project_service._project_from_row(
        {
            "id": "project-1",
            "title": "Project",
            "description": "",
            "objective": "",
            "success_criteria": "",
            "status": "in_progress",
            "role": "",
            "total_tasks": 5,
            "completed_tasks": 3,
            "remaining_tasks": 2,
            "derived_task_count": 2,
            "milestone_count": 1,
            "progress_basis": "wbs",
            "progress_percent": 60,
            "updated_at": "2026-01-01T00:00:00",
        }
    )

    assert project.derived_task_count == 2


def test_project_milestone_exposes_derived_task_count_mapping() -> None:
    milestone = project_service._milestone_from_row(
        {
            "id": "milestone-1",
            "project_id": "project-1",
            "milestone_key": "delivery",
            "title": "Delivery",
            "description": "",
            "acceptance_criteria": "",
            "weight": 50,
            "sort_order": 10,
            "total_tasks": 4,
            "completed_tasks": 3,
            "derived_task_count": 1,
            "progress_percent": 75,
            "updated_at": "2026-01-01T00:00:00",
        }
    )

    assert milestone.derived_task_count == 1


def test_project_summary_sql_counts_only_progress_derived_github_tasks() -> None:
    sql = project_service._PROJECT_SUMMARY_SQL

    assert "COUNT(*) FILTER (WHERE t.counts_toward_progress AND t.source_provider='derived-github')::int AS derived_task_count" in sql
    assert "COALESCE(ts.derived_task_count, 0)::int AS derived_task_count" in sql


def test_milestone_sql_counts_only_progress_derived_github_tasks() -> None:
    sql = project_service._MILESTONE_SQL

    assert "COUNT(t.id) FILTER (WHERE t.counts_toward_progress AND t.source_provider='derived-github')::int AS derived_task_count" in sql
