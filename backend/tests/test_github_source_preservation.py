from contextlib import nullcontext
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services import github_webhooks
from scripts import sync_github_data as sync


class Result:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, branch="release", duplicate=False):
        self.calls = []
        self.branch = branch
        self.duplicate = duplicate

    def execute(self, query, params):
        self.calls.append((query, params))
        if "SELECT status, reason FROM github_deliveries" in query:
            return Result({"status": "processed", "reason": ""} if self.duplicate else None)
        if "SELECT project_id::text FROM repository_sources" in query:
            return Result({"project_id": "project-id"})
        if "FROM repository_sources" in query:
            return Result({"id": "source-id", "project_id": "project-id", "default_branch": self.branch})
        if "FROM github_deliveries d" in query:
            return Result({"id": "delivery-row", "source_id": "source-id", "project_id": "project-id",
                           "event_name": "push", "default_branch": self.branch,
                           "payload": payload("release")})
        if "INSERT INTO github_commits" in query:
            return Result({"id": "commit-id"})
        return Result()


class Client:
    def __init__(self):
        self.requests = []

    def get(self, path):
        return {"id": 123, "full_name": "Owner/renamed", "default_branch": "main", "description": "External description"}

    def pages(self, path, **params):
        self.requests.append((path, params))
        if path.endswith("/commits"):
            return [{"sha": "abc123", "commit": {"message": "feat: useful work", "committer": {"date": "2026-09-18T01:00:00Z"}}}]
        return [{"id": 10, "number": 1, "title": "Changed remotely", "state": "closed", "updated_at": "2026-09-18T01:00:00Z"},
                {"id": 11, "number": 2, "title": "Not necessarily merged", "state": "closed", "pull_request": {},
                 "updated_at": "2026-09-18T02:00:00Z"}]


def payload(branch):
    return {"repository": {"id": 123, "full_name": "Owner/repo"}, "ref": f"refs/heads/{branch}", "commits": []}


def test_sync_preserves_project_work_and_logs_while_storing_external_items():
    connection, client = Connection(), Client()
    counts = sync.sync_repo(connection, client, "owner", ("Owner/repo", "repo", "fallback", "developer"), 100)

    assert counts == (1, 2, 1)
    assert client.requests[0][1] == {"sha": "release"}
    queries = [query for query, _ in connection.calls]
    assert all("UPDATE projects" not in query for query in queries)
    assert all("project_tasks" not in query for query in queries)
    assert all("INSERT INTO project_milestones" not in query for query in queries)
    source_query = next(query for query in queries if "INSERT INTO repository_sources" in query)
    conflict = source_query.split("DO UPDATE SET", 1)[1]
    assert "project_id=" not in conflict and "default_branch=" not in conflict
    log_query = next(query for query in queries if "INSERT INTO work_logs" in query)
    assert "DO NOTHING" in log_query and "DO UPDATE" not in log_query
    items = [(query, params) for query, params in connection.calls if "INSERT INTO github_items" in query]
    assert len(items) == 2
    assert items[0][1][:5] == ("owner", "source-id", 10, 1, "issue")
    assert items[1][1][4] == "pr"
    assert all("source_updated_at <= excluded.source_updated_at" in query for query, _ in items)


def test_new_project_does_not_invent_role_or_plan():
    class NewConnection(Connection):
        def execute(self, query, params):
            result = super().execute(query, params)
            if "SELECT project_id::text FROM repository_sources" in query:
                return Result()
            if "INSERT INTO projects" in query:
                return Result({"id": "new-project"})
            return result

    connection = NewConnection()
    sync.project_for(connection, "owner", {"id": 123, "full_name": "Owner/repo"}, "repo", "fallback", "assumed role")
    queries = [query for query, _ in connection.calls]
    assert any("'idea'" in query for query in queries)
    assert all("lower(title)" not in query for query in queries)
    assert all("UPDATE projects" not in query for query in queries)
    assert all("INSERT INTO project_milestones" not in query for query in queries)
    insert = next((query, params) for query, params in connection.calls if "INSERT INTO projects" in query)
    assert "role" not in insert[0] and "assumed role" not in insert[1]


def test_pagination_limit_is_failure_not_partial_success(monkeypatch):
    client = sync.GitHubClient()
    monkeypatch.setattr(client, "get", lambda path: [{"id": 1}] * 100)
    with pytest.raises(RuntimeError, match="Incomplete GitHub pagination"):
        client.pages("/repos/owner/repo/commits")


def test_pagination_returns_complete_pages(monkeypatch):
    client = sync.GitHubClient()
    batches = iter([[{"id": 1}] * 100, [{"id": 2}]])
    monkeypatch.setattr(client, "get", lambda path: next(batches))
    assert len(client.pages("/repos/owner/repo/commits")) == 101


@pytest.mark.parametrize("branch,expected", [("release", "processed"), ("main", "ignored")])
def test_webhook_uses_configured_branch(monkeypatch, branch, expected):
    connection = Connection()
    monkeypatch.setattr(github_webhooks, "connect", lambda settings: nullcontext(connection))
    result = github_webhooks.ingest_github_event(Settings(), "delivery-1", "push", payload(branch))
    assert result.status == expected
    assert result.reason == ("" if expected == "processed" else "non_default_ref")
    assert "pg_advisory_xact_lock" in connection.calls[0][0]


def test_reprocess_uses_same_configured_branch(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(github_webhooks, "connect", lambda settings: nullcontext(connection))
    result = github_webhooks.reprocess_github_delivery(Settings(), "owner", "project-id", "delivery-1")
    assert result.status == "processed"


def test_duplicate_delivery_does_not_write_work(monkeypatch):
    connection = Connection(duplicate=True)
    monkeypatch.setattr(github_webhooks, "connect", lambda settings: nullcontext(connection))
    result = github_webhooks.ingest_github_event(Settings(), "delivery-1", "push", payload("release"))
    assert result.reason == "duplicate_delivery"
    assert len(connection.calls) == 2


def test_repeated_sha_does_not_recreate_deleted_log(monkeypatch):
    connection = Connection()
    calls = []
    monkeypatch.setattr(github_webhooks, "_sync_commit_work_items", lambda *args: calls.append(args))
    event = {"commits": [{"id": "same-sha", "message": "old work"}]}
    for _ in range(3):
        assert github_webhooks._store_push_commits(connection, "owner", {"id": "source-id", "project_id": "project-id"}, event) == 0
    assert calls == []


def test_preservation_migration_is_additive_and_disables_destructive_derivation():
    root = Path(__file__).resolve().parents[2]
    sql = (root / "infrastructure/postgres/init/014_github_source_preservation.sql").read_text()
    assert "DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_evidence" in sql
    assert "DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_issue" in sql
    assert "FOREIGN KEY (owner_id, repository_source_id)" in sql
    assert "UNIQUE (owner_id, repository_source_id, number)" in sql
    assert "DELETE FROM" not in sql and "UPDATE project_tasks" not in sql
