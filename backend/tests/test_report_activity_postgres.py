"""Report activity read-model regressions against an isolated PostgreSQL schema."""

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.projects import ProjectSummary
from app.services.report_activity import fetch_report_activity


@pytest.fixture
def database():
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    with psycopg.connect(url, row_factory=dict_row) as connection:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("Requires disposable worktrace_test database")
        with connection.transaction(force_rollback=True):
            schema = f"report_activity_{uuid4().hex}"
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
            for path in sorted((Path(__file__).resolve().parents[2] / "infrastructure/postgres/init").glob("*.sql")):
                connection.execute(path.read_text())
            yield connection


def project_summary(project_id, *, status="approved", version=7) -> ProjectSummary:
    return ProjectSummary(
        id=str(project_id),
        title="Owner Project",
        status="in_progress",
        progress_plan_status=status,
        progress_plan_version=version,
        updated_at="2026-01-15 00:00:00+00",
    )


def insert_project(connection, owner, title):
    return connection.execute(
        "INSERT INTO projects(owner_id,title,status) VALUES(%s,%s,'in_progress') RETURNING id",
        (owner, title),
    ).fetchone()["id"]


def insert_task(connection, owner, project_id, title, status="planned", **overrides):
    values = {
        "source_provider": overrides.get("source_provider"),
        "source_key": overrides.get("source_key"),
        "counts_toward_progress": overrides.get("counts_toward_progress", True),
        "due_date": overrides.get("due_date"),
    }
    return connection.execute(
        """
        INSERT INTO project_tasks(
            owner_id, project_id, title, status, source_provider, source_key,
            counts_toward_progress, due_date
        )
        VALUES(%(owner_id)s,%(project_id)s,%(title)s,%(status)s,%(source_provider)s,%(source_key)s,
               %(counts_toward_progress)s,%(due_date)s)
        RETURNING id
        """,
        {"owner_id": owner, "project_id": project_id, "title": title, "status": status, **values},
    ).fetchone()["id"]


def insert_history(connection, owner, project_id, task_id, version, changed_at, *, source="user", previous="planned", next_status="in_progress"):
    return connection.execute(
        """
        INSERT INTO project_task_status_history(
            owner_id, project_id, task_id, previous_status, next_status,
            actor_owner_id, source, reason, changed_at, status_version
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (owner, project_id, task_id, previous, next_status, owner if source == "user" else None, source, "Recorded", changed_at, version),
    ).fetchone()["id"]


def test_report_activity_enforces_period_filters_sources_owner_scope_and_evidence(database):
    owner_project = insert_project(database, "owner", "Owner Project")
    other_project = insert_project(database, "other", "Other Project")
    missing_summary_project = insert_project(database, "owner", "Missing Summary Project")

    active_task = insert_task(database, "owner", owner_project, "Current metadata title", "in_progress", source_provider="github", due_date=date(2026, 1, 20))
    done_task = insert_task(database, "owner", owner_project, "Done task", "done")
    legacy_task = insert_task(
        database,
        "owner",
        owner_project,
        "Legacy validation",
        "planned",
        source_provider="derived-github",
        source_key="milestone-validation:legacy",
    )
    uncounted_task = insert_task(database, "owner", owner_project, "Reference only", "planned", counts_toward_progress=False)
    missing_summary_task = insert_task(database, "owner", missing_summary_project, "No summary task", "planned")
    other_task = insert_task(database, "other", other_project, "Other owner task", "planned")

    insert_history(database, "owner", owner_project, active_task, 2, "2026-01-14 14:59:59+00")
    included_start = insert_history(database, "owner", owner_project, active_task, 3, "2026-01-14 15:00:00+00")
    reopened = insert_history(
        database,
        "owner",
        owner_project,
        active_task,
        4,
        "2026-01-15 14:59:59+00",
        previous="done",
        next_status="in_progress",
    )
    insert_history(database, "owner", owner_project, active_task, 5, "2026-01-15 15:00:00+00")
    insert_history(database, "owner", owner_project, legacy_task, 2, "2026-01-15 01:00:00+00")
    milestone_transition = insert_history(database, "owner", owner_project, done_task, 2, "2026-01-15 02:00:00+00", source="milestone_validation")
    insert_history(database, "other", other_project, other_task, 2, "2026-01-15 03:00:00+00")

    worklog_id = database.execute(
        """
        INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers,updated_at)
        VALUES('owner',%s,'2026-01-15','Blocked work',' Waiting on access ','2026-01-15 04:00:00+00')
        RETURNING id
        """,
        (owner_project,),
    ).fetchone()["id"]
    null_project_log = database.execute(
        """
        INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers,updated_at)
        VALUES('owner',NULL,'2026-01-15','Unscoped blocker','Needs triage','2026-01-15 04:30:00+00')
        RETURNING id
        """
    ).fetchone()["id"]
    database.execute(
        "INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers) VALUES('owner',%s,'2026-01-15','Blank blocker','   ')",
        (owner_project,),
    )
    database.execute(
        "INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers) VALUES('other',%s,'2026-01-15','Other blocker','Hidden')",
        (other_project,),
    )

    document_id = database.execute(
        "INSERT INTO documents(owner_id,project_id,filename) VALUES('owner',%s,'evidence.md') RETURNING id",
        (owner_project,),
    ).fetchone()["id"]
    other_document_id = database.execute(
        "INSERT INTO documents(owner_id,project_id,filename) VALUES('other',%s,'other.md') RETURNING id",
        (other_project,),
    ).fetchone()["id"]
    other_worklog_id = database.execute(
        "INSERT INTO work_logs(owner_id,project_id,log_date,title,blockers) VALUES('other',%s,'2026-01-15','Other evidence','') RETURNING id",
        (other_project,),
    ).fetchone()["id"]
    ready_outcome = database.execute(
        """
        INSERT INTO project_outcomes(
            owner_id, project_id, title, outcome_type, before_state, after_state,
            metric_name, metric_value, metric_unit, evidence_work_log_ids,
            evidence_document_ids, resume_ready, updated_at
        )
        VALUES(
            'owner', %(project_id)s, 'Ready outcome', 'quantitative', 'Manual', 'Automated',
            'Hours saved', 2.5, 'hours', %(work_logs)s::uuid[],
            %(documents)s::uuid[], true, '2026-01-15 05:00:00+00'
        )
        RETURNING id
        """,
        {
            "project_id": owner_project,
            "work_logs": [worklog_id, other_worklog_id],
            "documents": [document_id, other_document_id],
        },
    ).fetchone()["id"]
    database.execute(
        """
        INSERT INTO project_outcomes(owner_id,project_id,title,resume_ready,updated_at)
        VALUES('owner',%s,'Unconfirmed',false,'2026-01-15 05:30:00+00'),
              ('owner',%s,'End excluded',true,'2026-01-15 15:00:00+00'),
              ('other',%s,'Other owner outcome',true,'2026-01-15 05:00:00+00')
        """,
        (owner_project, owner_project, other_project),
    )

    activity = fetch_report_activity(
        database,
        Settings(report_timezone="Asia/Seoul"),
        "owner",
        date(2026, 1, 15),
        date(2026, 1, 15),
        "2026-01-15T12:00:00+09:00",
        [project_summary(owner_project)],
    )

    assert [transition.id for transition in activity.transitions] == [str(included_start), str(milestone_transition), str(reopened)]
    assert activity.transitions[0].task_title == "Current metadata title"
    assert activity.transitions[1].source == "milestone_validation"
    assert activity.transitions[2].previous_status == "done"
    assert activity.transitions[2].next_status == "in_progress"

    assert [task.title for task in activity.current_tasks] == ["No summary task", "Current metadata title"]
    by_title = {task.title: task for task in activity.current_tasks}
    assert by_title["Current metadata title"].progress_plan_status == "approved"
    assert by_title["Current metadata title"].progress_plan_version == 7
    assert by_title["Current metadata title"].source_provider == "github"
    assert by_title["No summary task"].progress_plan_status == "unapproved"
    assert by_title["No summary task"].progress_plan_version == 0
    assert "Legacy validation" not in by_title
    assert "Reference only" not in by_title
    assert "Done task" not in by_title

    assert [issue.id for issue in activity.issues] == [str(worklog_id), str(null_project_log)]
    assert activity.issues[0].blockers == "Waiting on access"
    assert activity.issues[1].project_id is None
    assert activity.issues[1].project_title == ""

    assert [outcome.id for outcome in activity.outcomes] == [str(ready_outcome)]
    assert activity.outcomes[0].metric_value == "2.5000"
    assert activity.outcomes[0].evidence_work_log_ids == [str(worklog_id)]
    assert activity.outcomes[0].evidence_document_ids == [str(document_id)]


def test_report_activity_honors_non_default_timezone_boundaries(database):
    project_id = insert_project(database, "owner", "UTC Project")
    task_id = insert_task(database, "owner", project_id, "UTC boundary", "planned")
    excluded_before = insert_history(database, "owner", project_id, task_id, 2, "2026-01-15 04:59:59+00")
    included = insert_history(database, "owner", project_id, task_id, 3, "2026-01-15 05:00:00+00")
    excluded_end = insert_history(database, "owner", project_id, task_id, 4, "2026-01-16 05:00:00+00")

    activity = fetch_report_activity(
        database,
        Settings(report_timezone="America/New_York"),
        "owner",
        date(2026, 1, 15),
        date(2026, 1, 15),
        "2026-01-15T09:00:00-05:00",
        [project_summary(project_id)],
    )

    assert [transition.id for transition in activity.transitions] == [str(included)]
    assert str(excluded_before) not in [transition.id for transition in activity.transitions]
    assert str(excluded_end) not in [transition.id for transition in activity.transitions]
    assert activity.start_at == "2026-01-15T00:00:00-05:00"
    assert activity.end_exclusive == "2026-01-16T00:00:00-05:00"
