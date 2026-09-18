from inspect import getsource
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.projects import ProjectUpdate, RepositorySourceCreate
from app.services import projects
from app.services.projects import ProjectStatusUpdateForbiddenError, RepositorySourceConflictError


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT id FROM projects" in query:
            return FakeResult({"id": params[1]})
        if "SELECT id::text, project_id::text" in query:
            return FakeResult(None)
        if "INSERT INTO repository_sources" in query:
            return FakeResult(None)
        raise AssertionError(query)


class FakeProjectUpdateConnection:
    def __init__(self, current_status="in_progress"):
        self.calls = []
        self.current_status = current_status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT status FROM projects" in query:
            return FakeResult({"status": self.current_status})
        if "UPDATE projects" in query:
            return FakeResult({"id": params["project_id"]})
        raise AssertionError(query)


def test_repository_source_concurrent_cross_project_conflict_returns_error(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(projects, "connect", lambda settings: connection)

    with pytest.raises(RepositorySourceConflictError):
        projects.upsert_repository_source(
            Settings(_env_file=None),
            "owner",
            uuid4(),
            RepositorySourceCreate(repository_id=123, full_name="Owner/repo", default_branch="main"),
        )

    insert_sql = next(query for query, _params in connection.calls if "INSERT INTO repository_sources" in query)
    assert "WHERE repository_sources.project_id = EXCLUDED.project_id" in insert_sql


def test_generic_project_update_blocks_status_bypass_before_metadata_write(monkeypatch):
    connection = FakeProjectUpdateConnection(current_status="in_progress")
    monkeypatch.setattr(projects, "connect", lambda settings: connection)

    with pytest.raises(ProjectStatusUpdateForbiddenError):
        projects.update_project(Settings(_env_file=None), "owner", uuid4(), ProjectUpdate(status="done"))

    assert not any("UPDATE projects" in query for query, _params in connection.calls)


def test_generic_project_update_metadata_uses_sparse_update_without_stale_status(monkeypatch):
    connection = FakeProjectUpdateConnection(current_status="done")
    project_id = uuid4()
    monkeypatch.setattr(projects, "connect", lambda settings: connection)
    monkeypatch.setattr(projects, "get_project", lambda settings, owner_id, project_id: "project")

    assert projects.update_project(Settings(_env_file=None), "owner", project_id, ProjectUpdate(title="Renamed")) == "project"

    update_sql, update_params = next((query, params) for query, params in connection.calls if "UPDATE projects" in query)
    assert "status =" not in update_sql
    assert update_params["title"] == "Renamed"
    assert update_params["description"] is None


def test_lifecycle_service_uses_all_unfinished_tasks_and_does_not_update_wbs():
    source = getsource(projects.confirm_project_lifecycle)
    pending_source = getsource(projects._pending_task_count)

    assert "status<>'done'" in pending_source
    assert "counts_toward_progress" not in pending_source
    assert "UPDATE project_tasks" not in source
    assert "lifecycle_version=lifecycle_version + 1" in source
    assert "pg_advisory_xact_lock" in source
    assert "request_snapshot" in source


def test_task_mutations_lock_project_before_wbs_write():
    create_source = getsource(projects.create_project_task)
    update_source = getsource(projects.update_project_task)
    delete_source = getsource(projects.delete_project_task)
    lock_source = getsource(projects._lock_project_for_write)

    assert "FOR UPDATE" in lock_source
    assert create_source.index("_lock_project_for_write") < create_source.index("INSERT INTO project_tasks")
    assert update_source.index("_lock_project_for_write") < update_source.index("UPDATE project_tasks")
    assert delete_source.index("_lock_project_for_write") < delete_source.index("DELETE FROM project_tasks")


def test_lifecycle_reopen_clears_current_development_ended_date():
    source = getsource(projects.confirm_project_lifecycle)

    assert "next_ended_on = payload.development_ended_on if payload.status == \"done\" else None" in source
