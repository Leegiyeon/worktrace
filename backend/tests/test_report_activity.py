from datetime import date

from app.core.config import Settings
from app.schemas.projects import ProjectSummary
from app.services.report_activity import fetch_report_activity


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        if len(self.calls) == 1:
            return FakeResult(
                [
                    {
                        "id": "history-1",
                        "project_id": "project-1",
                        "project_title": "Project",
                        "task_id": "task-1",
                        "task_title": "Current task title",
                        "current_status": "in_progress",
                        "previous_status": "planned",
                        "next_status": "in_progress",
                        "source": "user",
                        "reason": "Started",
                        "changed_at": "2026-09-17 15:00:00+00",
                        "status_version": 2,
                    }
                ]
            )
        if len(self.calls) == 2:
            return FakeResult(
                [
                    {
                        "id": "task-1",
                        "project_id": "project-1",
                        "project_title": "Project",
                        "title": "Current task title",
                        "status": "in_progress",
                        "due_date": "2026-09-20",
                        "source_provider": "github",
                    },
                    {
                        "id": "task-2",
                        "project_id": "missing-summary",
                        "project_title": "No summary",
                        "title": "Fail closed",
                        "status": "planned",
                        "due_date": None,
                        "source_provider": None,
                    },
                ]
            )
        if len(self.calls) == 3:
            return FakeResult(
                [
                    {
                        "id": "worklog-1",
                        "project_id": None,
                        "project_title": "",
                        "title": "Blocked",
                        "blockers": "Waiting on access",
                        "log_date": "2026-09-18",
                        "updated_at": "2026-09-18 03:00:00+00",
                    }
                ]
            )
        return FakeResult(
            [
                {
                    "id": "outcome-1",
                    "project_id": "project-1",
                    "project_title": "Project",
                    "title": "Outcome",
                    "outcome_type": "qualitative",
                    "before_state": "manual",
                    "after_state": "automated",
                    "metric_name": "",
                    "metric_value": None,
                    "metric_unit": "",
                    "updated_at": "2026-09-18 04:00:00+00",
                    "evidence_work_log_ids": ["worklog-1"],
                    "evidence_document_ids": [],
                }
            ]
        )


def summary(project_id: str, status="approved", version=3) -> ProjectSummary:
    return ProjectSummary(
        id=project_id,
        title="Project",
        status="in_progress",
        progress_plan_status=status,
        progress_plan_version=version,
        updated_at="2026-09-18 00:00:00+00",
    )


def test_fetch_report_activity_uses_supplied_connection_owner_filters_and_summary_metadata():
    connection = FakeConnection()

    activity = fetch_report_activity(
        connection,
        Settings(report_timezone="Asia/Seoul"),
        "owner",
        date(2026, 9, 18),
        date(2026, 9, 18),
        "2026-09-18T12:00:00+09:00",
        [summary("project-1")],
    )

    assert activity.schema_version == "1"
    assert activity.fingerprint == ""
    assert activity.timezone == "Asia/Seoul"
    assert activity.start_at == "2026-09-18T00:00:00+09:00"
    assert activity.end_exclusive == "2026-09-19T00:00:00+09:00"
    assert activity.transitions[0].task_title == "Current task title"
    assert activity.current_tasks[0].progress_plan_status == "approved"
    assert activity.current_tasks[0].progress_plan_version == 3
    assert activity.current_tasks[1].progress_plan_status == "unapproved"
    assert activity.current_tasks[1].progress_plan_version == 0
    assert activity.issues[0].project_id is None
    assert activity.outcomes[0].evidence_work_log_ids == ["worklog-1"]

    assert len(connection.calls) == 4
    assert all(params["owner_id"] == "owner" for _, params in connection.calls)
    assert connection.calls[0][1]["start_at"].isoformat() == "2026-09-17T15:00:00+00:00"
    assert connection.calls[0][1]["end_exclusive"].isoformat() == "2026-09-18T15:00:00+00:00"
    assert all("owner_id" in query for query, _ in connection.calls)
    assert "source IN" not in connection.calls[0][0]
    assert "milestone-validation:" in connection.calls[0][0]
    assert "resume_ready IS TRUE" in connection.calls[3][0]
