"""Transition audit regressions against an isolated, disposable PostgreSQL schema."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.projects import ProjectTaskCreate, ProjectTaskUpdate
from app.services import projects


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    with psycopg.connect(url, row_factory=dict_row) as connection:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("Requires disposable worktrace_test database")
        with connection.transaction(force_rollback=True):
            schema = f"task_history_{uuid4().hex}"
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
            migrations = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
            for path in sorted(migrations.glob("*.sql")):
                if path.name < "017":
                    connection.execute(path.read_text())
            project_id = connection.execute(
                "INSERT INTO projects(owner_id,title) VALUES('owner','Audit project') RETURNING id"
            ).fetchone()["id"]
            legacy_id = connection.execute(
                "INSERT INTO project_tasks(owner_id,project_id,title,status) VALUES('owner',%s,'Legacy','done') RETURNING id",
                (project_id,),
            ).fetchone()["id"]
            connection.execute((migrations / "017_task_status_history.sql").read_text())

            @contextmanager
            def fake_connect(settings):
                with connection.transaction():
                    yield connection

            monkeypatch.setattr(projects, "connect", fake_connect)
            yield connection, project_id, legacy_id


def history(project_id, task_id, owner="owner"):
    return projects.get_project_task_status_history(Settings(), owner, project_id, task_id)


def change(project_id, task_id, **values):
    return projects.update_project_task(Settings(), "owner", project_id, task_id, ProjectTaskUpdate(**values))


def test_legacy_completion_is_unknown_and_metadata_cannot_invent_it(database):
    connection, project_id, task_id = database
    task = change(project_id, task_id, title="Legacy edited")
    assert task.completed_at is None
    assert task.status_version == 0
    assert history(project_id, task_id).total == 0
    connection.execute("UPDATE project_tasks SET completed_at=now(),status_version=999 WHERE id=%s", (task_id,))
    task = projects.get_project_task(Settings(), "owner", project_id, task_id)
    assert task.completed_at is None and task.status_version == 0


def test_complete_edit_retry_reopen_and_recomplete_preserve_audit(database):
    _, project_id, _ = database
    task = projects.create_project_task(Settings(), "owner", project_id, ProjectTaskCreate(title="Real work"))
    task_id = UUID(task.id)
    assert task.status_version == 1 and task.completed_at is None
    done = change(project_id, task_id, status="done", expected_status_version=1, status_reason="Accepted result")
    assert done.status_version == 2 and done.completed_at
    edited = change(project_id, task_id, title="Clarified title")
    repeated = change(project_id, task_id, status="done", expected_status_version=2)
    assert edited.completed_at == repeated.completed_at == done.completed_at
    assert history(project_id, task_id).total == 2
    with pytest.raises(projects.ProjectTaskStatusConflictError):
        change(project_id, task_id, status="on_hold", expected_status_version=1)
    reopened = change(project_id, task_id, status="in_progress", expected_status_version=2, status_reason="Additional work")
    assert reopened.completed_at is None and reopened.status_version == 3
    finished = change(project_id, task_id, status="done", expected_status_version=3)
    assert finished.completed_at != done.completed_at and finished.status_version == 4
    audit = history(project_id, task_id)
    assert [item.status_version for item in audit.items] == [4, 3, 2, 1]
    assert [item.previous_status for item in audit.items] == ["in_progress", "done", "planned", None]
    assert audit.items[2].reason == "Accepted result"
    assert audit.items[2].changed_at == done.completed_at
    assert all(item.actor_owner_id == "owner" and item.source == "user" for item in audit.items)


def test_history_is_owner_scoped_immutable_and_cascades_with_task(database):
    connection, project_id, task_id = database
    change(project_id, task_id, status="planned", expected_status_version=0)
    with pytest.raises(projects.ProjectTaskNotFoundError):
        history(project_id, task_id, owner="other")
    with pytest.raises(projects.ProjectTaskNotFoundError):
        history(uuid4(), task_id)
    for statement in ("UPDATE project_task_status_history SET reason='rewrite'", "DELETE FROM project_task_status_history"):
        with pytest.raises(psycopg.Error, match="append-only"):
            with connection.transaction():
                connection.execute(statement)
    projects.delete_project_task(Settings(), "owner", project_id, task_id)
    assert connection.execute("SELECT count(*) AS n FROM project_task_status_history").fetchone()["n"] == 0


def test_system_transitions_and_latest_50_versions(database):
    connection, project_id, task_id = database
    for index in range(60):
        connection.execute("UPDATE project_tasks SET status=%s WHERE id=%s", ("planned" if index % 2 == 0 else "done", task_id))
    audit = history(project_id, task_id)
    assert audit.total == 60 and len(audit.items) == 50
    assert audit.items[0].status_version == 60 and audit.items[-1].status_version == 11
    assert all(item.source == "system" and item.actor_owner_id is None for item in audit.items)


def test_project_delete_cascades_task_history(database):
    connection, project_id, task_id = database
    change(project_id, task_id, status="planned", expected_status_version=0)
    connection.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    assert connection.execute("SELECT count(*) AS n FROM project_task_status_history").fetchone()["n"] == 0


def test_audit_failure_rolls_back_task_transition(database):
    connection, project_id, task_id = database
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            projects._set_task_status_context(connection, actor_owner_id="owner", source="user", reason="x" * 2001)
            connection.execute("UPDATE project_tasks SET status='planned' WHERE id=%s", (task_id,))
    task = projects.get_project_task(Settings(), "owner", project_id, task_id)
    assert task.status == "done" and task.status_version == 0 and task.completed_at is None
    assert history(project_id, task_id).total == 0
