"""Real SQL regressions for project lifecycle on disposable worktrace_test."""

import os
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.projects import ProjectLifecycleConfirm, ProjectTaskCreate, ProjectTaskUpdate, ProjectUpdate
from app.services import projects
from app.services.projects import (
    ProjectLifecycleConflictError,
    ProjectLifecycleValidationError,
    ProjectNotFoundError,
    ProjectStatusUpdateForbiddenError,
)


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    connection = psycopg.connect(url, row_factory=dict_row)
    outer = None
    try:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("SQL regression requires the disposable worktrace_test database")
        outer = connection.transaction()
        outer.__enter__()
        schema = f"project_lifecycle_{uuid4().hex}"
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        root = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
        for path in sorted(root.glob("*.sql")):
            connection.execute(path.read_text())

        @contextmanager
        def fake_connect(settings):
            yield connection

        monkeypatch.setattr(projects, "connect", fake_connect)
        yield connection
    finally:
        if outer is not None:
            outer.__exit__(Exception, Exception("rollback test transaction"), None)
        connection.close()


@pytest.fixture
def committed_database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    connection = psycopg.connect(url, row_factory=dict_row)
    schema = f"project_lifecycle_committed_{uuid4().hex}"
    try:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("SQL regression requires the disposable worktrace_test database")
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        root = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
        for path in sorted(root.glob("*.sql")):
            connection.execute(path.read_text())
        connection.commit()

        @contextmanager
        def fake_connect(settings):
            worker = psycopg.connect(url, row_factory=dict_row)
            try:
                worker.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
                worker.commit()
                yield worker
                worker.commit()
            except Exception:
                worker.rollback()
                raise
            finally:
                worker.close()

        monkeypatch.setattr(projects, "connect", fake_connect)
        yield connection
    finally:
        connection.rollback()
        connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        connection.commit()
        connection.close()


def lifecycle_payload(
    *,
    status="done",
    service_status="operating",
    reason="Owner confirmed lifecycle state.",
    incomplete_reason=None,
    ended_on=None,
    expected_version=0,
    request_id=None,
):
    return ProjectLifecycleConfirm(
        status=status,
        service_status=service_status,
        reason=reason,
        incomplete_reason=incomplete_reason,
        development_ended_on=ended_on,
        expected_version=expected_version,
        request_id=request_id or uuid4(),
    )


def seed_project(connection, *, owner="owner", status="in_progress", title="Lifecycle Project"):
    return connection.execute(
        "INSERT INTO projects(owner_id,title,status,role) VALUES(%s,%s,%s,'Owner') RETURNING id",
        (owner, title, status),
    ).fetchone()["id"]


def seed_task(connection, project_id, *, owner="owner", title="Task", status="planned", counts=True):
    return connection.execute(
        """
        INSERT INTO project_tasks(owner_id,project_id,title,status,counts_toward_progress)
        VALUES(%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (owner, project_id, title, status, counts),
    ).fetchone()["id"]


def task_snapshot(connection, project_id, *, owner="owner"):
    return connection.execute(
        """
        SELECT id::text, title, status, counts_toward_progress, updated_at
        FROM project_tasks
        WHERE owner_id=%s AND project_id=%s
        ORDER BY id
        """,
        (owner, project_id),
    ).fetchall()


def test_legacy_project_defaults_unknown_without_fabricated_dates(database):
    project_id = seed_project(database, status="done")

    lifecycle = projects.get_project_lifecycle(Settings(_env_file=None), "owner", project_id)
    summary = projects.get_project(Settings(_env_file=None), "owner", project_id)

    assert lifecycle.status == "done"
    assert lifecycle.service_status == "unknown"
    assert lifecycle.development_ended_on is None
    assert lifecycle.lifecycle_version == 0
    assert lifecycle.lifecycle_confirmed_at is None
    assert lifecycle.history == []
    assert summary.service_status == "unknown"
    assert summary.development_ended_on is None


def test_close_with_unfinished_guard_then_reason_preserves_wbs(database):
    project_id = seed_project(database)
    seed_task(database, project_id, title="Counted unfinished", status="planned", counts=True)
    seed_task(database, project_id, title="Uncounted unfinished", status="on_hold", counts=False)
    seed_task(database, project_id, title="Complete", status="done", counts=True)
    before = task_snapshot(database, project_id)

    with pytest.raises(ProjectLifecycleValidationError):
        projects.confirm_project_lifecycle(
            Settings(_env_file=None),
            "owner",
            project_id,
            lifecycle_payload(reason="Done but no incomplete reason."),
        )

    confirmed = projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(
            reason="Owner confirmed development ended.",
            incomplete_reason="Two managed tasks remain intentionally unfinished.",
            ended_on="2026-09-18",
        ),
    )
    after = task_snapshot(database, project_id)

    assert confirmed.status == "done"
    assert confirmed.service_status == "operating"
    assert confirmed.development_ended_on.isoformat() == "2026-09-18"
    assert confirmed.pending_task_count == 2
    assert confirmed.lifecycle_version == 1
    assert len(confirmed.history) == 1
    assert confirmed.history[0].previous_status == "in_progress"
    assert confirmed.history[0].status == "done"
    assert confirmed.history[0].incomplete_reason == "Two managed tasks remain intentionally unfinished."
    assert after == before


def test_reopen_clears_current_ended_date_but_retains_history(database):
    project_id = seed_project(database)
    closed = projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(reason="Closed by owner.", ended_on="2026-09-18"),
    )

    reopened = projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(
            status="in_progress",
            service_status="not_released",
            reason="Development resumed.",
            expected_version=closed.lifecycle_version,
        ),
    )

    assert reopened.status == "in_progress"
    assert reopened.service_status == "not_released"
    assert reopened.development_ended_on is None
    assert reopened.lifecycle_version == 2
    assert len(reopened.history) == 2
    assert reopened.history[0].previous_status == "done"
    assert reopened.history[0].status == "in_progress"
    assert reopened.history[1].development_ended_on.isoformat() == "2026-09-18"
    assert reopened.history[1].incomplete_reason == ""


def test_duplicate_same_request_uuid_replays_without_duplicate_history(database):
    project_id = seed_project(database)
    request_id = uuid4()
    payload = lifecycle_payload(reason="Explicit no-op confirmation.", request_id=request_id)

    first = projects.confirm_project_lifecycle(Settings(_env_file=None), "owner", project_id, payload)
    replay = projects.confirm_project_lifecycle(Settings(_env_file=None), "owner", project_id, payload)
    history_count = database.execute(
        "SELECT COUNT(*)::int AS count FROM project_lifecycle_history WHERE owner_id='owner' AND project_id=%s",
        (project_id,),
    ).fetchone()["count"]

    assert first.lifecycle_version == 1
    assert replay.lifecycle_version == 1
    assert replay.lifecycle_confirmed_at == first.lifecycle_confirmed_at
    assert history_count == 1


def test_lifecycle_cas_conflict_rejects_stale_expected_version(database):
    project_id = seed_project(database)
    projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(reason="First confirmation."),
    )

    with pytest.raises(ProjectLifecycleConflictError):
        projects.confirm_project_lifecycle(
            Settings(_env_file=None),
            "owner",
            project_id,
            lifecycle_payload(reason="Stale confirmation.", expected_version=0),
        )


def test_lifecycle_is_owner_scoped(database):
    project_id = seed_project(database, owner="owner")

    with pytest.raises(ProjectNotFoundError):
        projects.get_project_lifecycle(Settings(_env_file=None), "other-owner", project_id)

    with pytest.raises(ProjectNotFoundError):
        projects.confirm_project_lifecycle(
            Settings(_env_file=None),
            "other-owner",
            project_id,
            lifecycle_payload(reason="Wrong owner."),
        )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            database.execute(
                """
                INSERT INTO project_lifecycle_history (
                    owner_id, project_id, actor_owner_id, request_id, request_snapshot,
                    previous_status, next_status, previous_service_status, next_service_status, reason
                )
                VALUES ('other-owner', %s, 'other-owner', %s, '{}'::jsonb,
                        'in_progress', 'done', 'unknown', 'operating', 'Invalid owner')
                """,
                (project_id, uuid4()),
            )


def test_generic_patch_status_bypass_blocked_and_metadata_does_not_overwrite_lifecycle(database):
    project_id = seed_project(database)
    closed = projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(reason="Closed by lifecycle.", ended_on="2026-09-18"),
    )

    with pytest.raises(ProjectStatusUpdateForbiddenError):
        projects.update_project(Settings(_env_file=None), "owner", project_id, ProjectUpdate(status="in_progress"))

    edited = projects.update_project(
        Settings(_env_file=None),
        "owner",
        project_id,
        ProjectUpdate(title="Renamed", status="done", description="Metadata only"),
    )
    lifecycle = projects.get_project_lifecycle(Settings(_env_file=None), "owner", project_id)

    assert edited.title == "Renamed"
    assert edited.description == "Metadata only"
    assert edited.status == "done"
    assert edited.service_status == "operating"
    assert edited.lifecycle_version == closed.lifecycle_version
    assert lifecycle.status == "done"
    assert lifecycle.service_status == "operating"
    assert lifecycle.development_ended_on.isoformat() == "2026-09-18"
    assert lifecycle.lifecycle_version == closed.lifecycle_version


def test_blank_incomplete_reason_normalizes_to_null_and_response_string(database):
    project_id = seed_project(database)

    lifecycle = projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(reason="No unfinished tasks.", incomplete_reason=""),
    )
    stored = database.execute(
        "SELECT incomplete_reason FROM project_lifecycle_history WHERE owner_id='owner' AND project_id=%s",
        (project_id,),
    ).fetchone()["incomplete_reason"]

    assert stored is None
    assert lifecycle.history[0].incomplete_reason == ""


def test_history_delete_policy_blocks_direct_delete_but_allows_project_cascade(database):
    project_id = seed_project(database)
    projects.confirm_project_lifecycle(
        Settings(_env_file=None),
        "owner",
        project_id,
        lifecycle_payload(reason="Creates history."),
    )
    history_id = database.execute(
        "SELECT id FROM project_lifecycle_history WHERE owner_id='owner' AND project_id=%s",
        (project_id,),
    ).fetchone()["id"]

    with pytest.raises(psycopg.errors.RaiseException):
        with database.transaction():
            database.execute("DELETE FROM project_lifecycle_history WHERE id=%s", (history_id,))

    projects.delete_project(Settings(_env_file=None), "owner", project_id)
    remaining = database.execute(
        "SELECT COUNT(*)::int AS count FROM project_lifecycle_history WHERE id=%s",
        (history_id,),
    ).fetchone()["count"]

    assert remaining == 0


def test_task_create_waits_on_project_lifecycle_lock_before_mutation(committed_database):
    connection = committed_database
    project_id = seed_project(connection)
    connection.commit()

    blocker = connection.transaction()
    blocker.__enter__()
    released = False
    try:
        connection.execute("SELECT id FROM projects WHERE owner_id='owner' AND id=%s FOR UPDATE", (project_id,))

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                projects.create_project_task,
                Settings(_env_file=None),
                "owner",
                project_id,
                ProjectTaskCreate(title="Concurrent task"),
            )
            time.sleep(0.2)
            assert not future.done()
            blocker.__exit__(None, None, None)
            released = True
            task = future.result(timeout=5)
    except Exception:
        if not released:
            blocker.__exit__(Exception, Exception("rollback lifecycle lock test"), None)
        raise

    count = connection.execute(
        "SELECT COUNT(*)::int AS count FROM project_tasks WHERE owner_id='owner' AND project_id=%s",
        (project_id,),
    ).fetchone()["count"]

    assert task.title == "Concurrent task"
    assert count == 1


def test_metadata_task_update_waits_for_project_lock_then_preserves_latest_status(committed_database):
    connection = committed_database
    project_id = seed_project(connection)
    task_id = seed_task(connection, project_id, status="planned")
    connection.commit()

    blocker = connection.transaction()
    blocker.__enter__()
    released = False
    try:
        connection.execute("SELECT id FROM projects WHERE owner_id='owner' AND id=%s FOR UPDATE", (project_id,))

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                projects.update_project_task,
                Settings(_env_file=None),
                "owner",
                project_id,
                task_id,
                ProjectTaskUpdate(description="Metadata after status change"),
            )
            time.sleep(0.2)
            assert not future.done()
            connection.execute(
                "UPDATE project_tasks SET status='done' WHERE owner_id='owner' AND project_id=%s AND id=%s",
                (project_id, task_id),
            )
            blocker.__exit__(None, None, None)
            released = True
            task = future.result(timeout=5)
    except Exception:
        if not released:
            blocker.__exit__(Exception, Exception("rollback metadata lock test"), None)
        raise

    stored = connection.execute(
        "SELECT status, description FROM project_tasks WHERE owner_id='owner' AND project_id=%s AND id=%s",
        (project_id, task_id),
    ).fetchone()

    assert task.status == "done"
    assert task.description == "Metadata after status change"
    assert stored["status"] == "done"
    assert stored["description"] == "Metadata after status change"
