"""Real SQL regression on an explicitly configured, disposable worktrace_test DB."""

import os
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.services import github_webhooks
from scripts.sync_github_data import sync_repo


@pytest.fixture
def database():
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    connection = psycopg.connect(url, row_factory=dict_row)
    try:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("SQL regression requires the disposable worktrace_test database")
        schema = f"preservation_{uuid4().hex}"
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        root = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
        for path in sorted(root.glob("*.sql")):
            if path.name < "014":
                connection.execute(path.read_text())
        yield connection, root
    finally:
        connection.rollback()
        connection.close()


def snapshot(connection):
    return {
        table: connection.execute(sql.SQL("SELECT * FROM {} ORDER BY id").format(sql.Identifier(table))).fetchall()
        for table in ("projects", "project_tasks", "work_logs", "project_milestones")
    }


def test_migration_and_repeated_sync_preserve_work_and_external_version(database, monkeypatch):
    connection, root = database
    project = connection.execute(
        "INSERT INTO projects(owner_id,title,status,role) VALUES('owner','My project','done','Confirmed role') RETURNING id"
    ).fetchone()["id"]
    source = connection.execute(
        "INSERT INTO repository_sources(owner_id,project_id,repository_id,full_name,default_branch) "
        "VALUES('owner',%s,123,'Owner/repo','release') RETURNING id", (project,),
    ).fetchone()["id"]
    milestone = connection.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,acceptance_criteria,weight) "
        "VALUES('owner',%s,'core-delivery','User milestone','Confirmed criteria',100) RETURNING id", (project,),
    ).fetchone()["id"]
    commit = connection.execute(
        "INSERT INTO github_commits(owner_id,project_id,repository_source_id,sha,message,committed_at) "
        "VALUES('owner',%s,%s,'abc123','feat: useful work','2026-09-18T01:00:00Z') RETURNING id", (project, source),
    ).fetchone()["id"]
    connection.execute(
        "INSERT INTO project_milestone_evidence(owner_id,project_id,milestone_id,github_commit_id) VALUES('owner',%s,%s,%s)",
        (project, milestone, commit),
    )
    connection.execute("UPDATE project_tasks SET title='User edited',description='Keep me',status='on_hold',counts_toward_progress=false")
    connection.execute(
        "INSERT INTO work_logs(owner_id,project_id,log_date,title,content,source_provider,source_key) "
        "VALUES('owner',%s,'2026-09-18','User log','User detail','github',%s)",
        (project, f"day:{source}:2026-09-18"),
    )
    before = snapshot(connection)
    assert len(before["project_tasks"]) == 2
    migration = (root / "014_github_source_preservation.sql").read_text()
    connection.execute(migration)
    connection.execute(migration)
    assert snapshot(connection) == before

    class Client:
        timestamp = "2026-09-18T03:00:00Z"
        title = "Latest external issue"

        def get(self, path):
            return {"id": 123, "full_name": "Owner/renamed", "default_branch": "main", "description": "Remote description"}

        def pages(self, path, **params):
            if path.endswith("/commits"):
                assert params["sha"] == "release"
                return [{"sha": "abc123", "commit": {"message": "feat: useful work", "committer": {"date": "2026-09-18T01:00:00Z"}}}]
            return [{"id": 10, "number": 1, "state": "closed", "title": self.title, "updated_at": self.timestamp},
                    {"id": 11, "number": 2, "state": "closed", "pull_request": {}, "updated_at": self.timestamp}]

    client = Client()
    for _ in range(3):
        sync_repo(connection, client, "owner", ("Owner/repo", "repo", "fallback", "Unconfirmed role"), 100)
    client.timestamp, client.title = "2026-09-17T00:00:00Z", "Stale external issue"
    sync_repo(connection, client, "owner", ("Owner/repo", "repo", "fallback", "Unconfirmed role"), 100)
    assert snapshot(connection) == before
    items = connection.execute("SELECT kind,payload FROM github_items ORDER BY number").fetchall()
    assert len(items) == 2
    assert items[0]["payload"]["title"] == "Latest external issue"
    assert items[1]["kind"] == "pr"

    monkeypatch.setattr(github_webhooks, "connect", lambda settings: nullcontext(connection))
    event = {"repository": {"id": 123}, "ref": "refs/heads/release", "commits": [
        {"id": "def456", "message": "Another activity", "timestamp": "2026-09-18T02:00:00Z"},
    ]}
    settings = Settings(default_owner_id="owner")
    first = github_webhooks.ingest_github_event(settings, "delivery-1", "push", event)
    assert first.commits_stored == 1
    assert github_webhooks.ingest_github_event(settings, "delivery-1", "push", event).reason == "duplicate_delivery"
    assert github_webhooks.ingest_github_event(settings, "delivery-2", "push", event).commits_stored == 0
    after = snapshot(connection)
    assert after["project_tasks"] == before["project_tasks"]
    assert after["work_logs"] == before["work_logs"]
    assert after["projects"][0]["status"] == "done"

    connection.execute(
        "INSERT INTO project_tasks(owner_id,project_id,title,source_provider,source_key) "
        "VALUES('owner',%s,'User imported Issue','github','issue:Owner/repo:1')", (project,),
    )
    connection.execute("SELECT worktrace_refresh_commit_derived_wbs('owner',%s)", (project,))
    derived = connection.execute("SELECT * FROM project_tasks WHERE source_provider='derived-github' ORDER BY id").fetchall()
    assert derived == before["project_tasks"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection.transaction():
            connection.execute(
                "INSERT INTO github_items(owner_id,repository_source_id,external_id,number,kind,source_updated_at,payload) "
                "VALUES('other-owner',%s,12,3,'issue',now(),'{}')", (source,),
            )
