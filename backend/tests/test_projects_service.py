from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.projects import RepositorySourceCreate
from app.services import projects
from app.services.projects import RepositorySourceConflictError


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
