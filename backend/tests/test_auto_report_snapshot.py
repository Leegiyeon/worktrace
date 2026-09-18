from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.schemas.reports import AutoReportRequest
from app.schemas.report_activity import ReportActivity
from app.services import auto_report, projects
from test_project_lifecycle_postgres import committed_database
from test_weekly_report import sample_dataset
from test_auto_report_progress import summary


def activity(**overrides):
    return ReportActivity(**{
        "as_of": "2026-09-18T00:00:00Z", "timezone": "Asia/Seoul",
        "start_at": "2026-09-13T15:00:00Z", "end_exclusive": "2026-09-18T15:00:00Z",
        "transitions": [], "current_tasks": [], "issues": [], "outcomes": [], **overrides,
    })


def build(records):
    return auto_report.build_auto_report_response(sample_dataset(), "weekly", date(2026, 9, 14), date(2026, 9, 18), [summary()], records.as_of, records)


def test_content_fingerprint_is_stable_but_changes_with_source_content():
    first = build(activity())
    second = build(activity(as_of="2026-09-18T01:00:00Z"))
    assert first.activity.fingerprint == second.activity.fingerprint
    assert first.markdown != second.markdown
    assert len(first.activity.fingerprint) == 64
    assert first.activity.fingerprint in first.markdown
    issue = {"id": "log-id", "project_id": None, "project_title": "", "title": "Blocking question",
             "blockers": "Permission pending", "log_date": "2026-09-18", "updated_at": "2026-09-18T00:00:00Z"}
    changed = build(activity(issues=[issue]))
    assert changed.activity.fingerprint != first.activity.fingerprint
    assert "Permission pending" in changed.markdown and "log-id" in changed.markdown
    assert "해결됨" not in changed.markdown


def test_markdown_keeps_recorded_events_separate_from_current_status_and_outcome_dates():
    report = build(activity(
        transitions=[{"id": "event-id", "project_id": "p", "project_title": "Project", "task_id": "task-id", "task_title": "Task",
                      "current_status": "in_progress", "previous_status": "planned", "next_status": "done", "source": "user", "reason": "Reviewed",
                      "changed_at": "2026-09-15T00:00:00Z", "status_version": 2}],
        outcomes=[{"id": "outcome-id", "project_id": "p", "project_title": "Project", "title": "Recorded outcome", "outcome_type": "quantitative",
                   "before_state": "Before", "after_state": "After", "metric_name": "Duration", "metric_value": "0", "metric_unit": "minutes",
                   "updated_at": "2026-09-17T00:00:00Z", "evidence_work_log_ids": ["evidence-log"], "evidence_document_ids": []}],
    ))
    assert "예정 → 완료 / 현재 진행" in report.markdown
    assert "event-id" in report.markdown and "task-id" in report.markdown
    assert "기간 내 수정된 확인 성과" in report.markdown
    assert "Duration 0 minutes" in report.markdown and "evidence-log" in report.markdown
    assert "기간 종료일의 잔여량이 아닙니다" in report.markdown


def test_generation_keeps_one_snapshot_during_concurrent_source_change(committed_database, monkeypatch):
    writer = committed_database
    project_id = writer.execute("INSERT INTO projects(owner_id,title,updated_at) VALUES('owner','Before snapshot','2000-01-01') RETURNING id").fetchone()["id"]
    task_id = writer.execute("INSERT INTO project_tasks(owner_id,project_id,title,status) VALUES('owner',%s,'Recorded task','planned') RETURNING id", (project_id,)).fetchone()["id"]
    writer.commit()
    monkeypatch.setattr(auto_report, "connect", projects.connect)
    original = auto_report.list_projects
    changed = False

    def mutate_between_reads(settings, owner, *, connection):
        nonlocal changed
        assert connection.execute("SHOW transaction_isolation").fetchone()["transaction_isolation"] == "repeatable read"
        assert connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        if not changed:
            writer.execute("UPDATE projects SET title='After snapshot' WHERE id=%s", (project_id,))
            writer.execute("UPDATE project_tasks SET status='done' WHERE id=%s", (task_id,))
            writer.commit()
            changed = True
        return original(settings, owner, connection=connection)

    monkeypatch.setattr(auto_report, "list_projects", mutate_between_reads)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    request = AutoReportRequest(report_type="daily", start_date=today, end_date=today)
    first = auto_report.generate_auto_report(Settings(report_timezone="Asia/Seoul"), "owner", request)
    assert first.projects[0].title == "Before snapshot"
    assert first.activity.current_tasks[0].status == "planned"
    assert first.activity.current_tasks[0].progress_plan_status == "unapproved"
    assert all(row.next_status != "done" for row in first.activity.transitions)
    second = auto_report.generate_auto_report(Settings(report_timezone="Asia/Seoul"), "owner", request)
    assert second.projects[0].title == "After snapshot"
    assert not second.activity.current_tasks
    assert any(row.next_status == "done" for row in second.activity.transitions)
    assert first.activity.fingerprint != second.activity.fingerprint
    third = auto_report.generate_auto_report(Settings(report_timezone="Asia/Seoul"), "owner", request)
    assert second.activity.fingerprint == third.activity.fingerprint


def test_report_does_not_expose_foreign_project_reference_on_owned_log(committed_database, monkeypatch):
    connection = committed_database
    foreign_id = connection.execute("INSERT INTO projects(owner_id,title) VALUES('other','Private project') RETURNING id").fetchone()["id"]
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    connection.execute("INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers) VALUES('owner',%s,%s,'Owned log','Waiting')", (foreign_id, today))
    connection.commit()
    monkeypatch.setattr(auto_report, "connect", projects.connect)
    response = auto_report.generate_auto_report(Settings(), "owner", AutoReportRequest(report_type="daily", start_date=today, end_date=today))
    assert response.work_logs[0].project_id is None
    assert response.activity.issues[0].project_id is None
    assert str(foreign_id) not in response.model_dump_json()
    assert "Private project" not in response.model_dump_json()
