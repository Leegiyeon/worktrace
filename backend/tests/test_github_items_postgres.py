"""Real SQL regression for GitHub item review/adoption on disposable worktrace_test."""

import os
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.schemas.github_items import GitHubItemDecisionRequest
from app.services.github_items import GitHubItemConflictError, GitHubItemInvalidDecisionError, decide_github_item, list_github_items


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
        schema = f"github_items_{uuid4().hex}"
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        root = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
        for path in sorted(root.glob("*.sql")):
            connection.execute(path.read_text())

        @contextmanager
        def fake_connect(settings):
            with connection.transaction():
                yield connection

        monkeypatch.setattr("app.services.github_items.connect", fake_connect)
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
    schema = f"github_items_committed_{uuid4().hex}"
    try:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("SQL regression requires the disposable worktrace_test database")
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        root = Path(__file__).resolve().parents[2] / "infrastructure/postgres/init"
        for path in sorted(root.glob("*.sql")):
            connection.execute(path.read_text())
        connection.commit()

        barrier = threading.Barrier(2)

        @contextmanager
        def fake_connect(settings):
            worker = psycopg.connect(url, row_factory=dict_row)
            try:
                worker.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
                worker.commit()
                barrier.wait(timeout=5)
                yield worker
                worker.commit()
            except Exception:
                worker.rollback()
                raise
            finally:
                worker.close()

        monkeypatch.setattr("app.services.github_items.connect", fake_connect)
        yield connection, schema
    finally:
        connection.rollback()
        connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        connection.commit()
        connection.close()


def seed_item(connection, *, owner="owner", project=None, number=1, kind="issue", state="open", title="Imported", body="Body"):
    project_id = project or connection.execute(
        "INSERT INTO projects(owner_id,title,status) VALUES(%s,'Project','in_progress') RETURNING id", (owner,)
    ).fetchone()["id"]
    source = connection.execute(
        "SELECT id FROM repository_sources WHERE owner_id=%s AND project_id=%s AND provider='github' ORDER BY created_at LIMIT 1",
        (owner, project_id),
    ).fetchone()
    if source is None:
        source_id = connection.execute(
            "INSERT INTO repository_sources(owner_id,project_id,repository_id,full_name,default_branch) VALUES(%s,%s,%s,%s,'main') RETURNING id",
            (owner, project_id, number + 1000, f"Owner/repo-{number}"),
        ).fetchone()["id"]
    else:
        source_id = source["id"]
    item_id = connection.execute(
        """
        INSERT INTO github_items(owner_id,repository_source_id,external_id,number,kind,source_updated_at,payload)
        VALUES(%s,%s,%s,%s,%s,'2026-09-18T01:00:00Z',%s::jsonb)
        RETURNING id
        """,
        (owner, source_id, number + 10000, number, kind, Jsonb({"title": title, "body": body, "state": state, "html_url": f"https://github.com/Owner/repo/issues/{number}"})),
    ).fetchone()["id"]
    return project_id, source_id, item_id


def request(action, *, version=0, source="2026-09-18T01:00:00Z", request_id=None, title=None, task_id=None, counts=True):
    return GitHubItemDecisionRequest(
        action=action,
        expected_version=version,
        expected_source_updated_at=source,
        request_id=request_id or uuid4(),
        title=title,
        task_id=task_id,
        counts_toward_progress=counts,
    )


def test_list_counts_pagination_url_sanitization_and_body_cap(database):
    project_id, source_id, item_id = seed_item(database, body="x" * 20050)
    database.execute(
        """
        INSERT INTO github_items(owner_id,repository_source_id,external_id,number,kind,source_updated_at,payload,review_status)
        VALUES('owner',%s,2,2,'issue','2026-09-18T02:00:00Z',%s::jsonb,'ignored')
        """,
        (source_id, Jsonb({"title": "Ignored", "body": "", "state": "open", "html_url": "http://evil.test/2"})),
    )

    listed = list_github_items(Settings(_env_file=None), "owner", project_id, "all", 1, 0)

    assert listed.total == 2
    assert listed.counts.pending == 1
    assert listed.counts.ignored == 1
    assert len(listed.items) == 1
    assert listed.items[0].body_truncated is False
    pending = list_github_items(Settings(_env_file=None), "owner", project_id, "pending", 20, 0).items[0]
    assert pending.id == str(item_id)
    assert pending.body_truncated is True
    assert pending.body.endswith("[truncated]")
    assert "T" in pending.source_updated_at
    assert pending.source_updated_at.endswith("+00:00")
    assert "T" in pending.collected_at


def test_create_adopts_closed_pr_as_planned_not_done_and_retry_is_idempotent(database):
    project_id, _source_id, item_id = seed_item(database, kind="pr", state="closed", title="Closed PR")
    request_id = uuid4()
    payload = request("create", request_id=request_id, title="Review closed PR", counts=False)

    first = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, payload)
    retry = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, payload)
    task = database.execute("SELECT status, counts_toward_progress, source_provider, source_key FROM project_tasks WHERE id=%s", (first.task_id,)).fetchone()
    audits = database.execute("SELECT COUNT(*)::int AS count FROM github_item_decision_audits WHERE request_id=%s", (request_id,)).fetchone()["count"]
    audit = database.execute("SELECT source_payload, source_version FROM github_item_decision_audits WHERE request_id=%s", (request_id,)).fetchone()

    assert first.review_status == "adopted"
    assert retry.task_id == first.task_id
    assert task["status"] == "planned"
    assert task["counts_toward_progress"] is False
    assert task["source_provider"] == "github-adopted"
    assert task["source_key"] == f"github-item:{item_id}"
    assert audits == 1
    assert audit["source_payload"]["title"] == "Closed PR"
    assert audit["source_version"] == 0


def test_database_rejects_cross_owner_task_reference(database):
    _project_id, _source_id, item_id = seed_item(database)
    other_project = database.execute("INSERT INTO projects(owner_id,title,status) VALUES('other','Other','in_progress') RETURNING id").fetchone()["id"]
    other_task = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('other',%s,'Other task') RETURNING id", (other_project,)).fetchone()["id"]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            database.execute("UPDATE github_items SET task_id=%s WHERE id=%s", (other_task, item_id))


def test_database_rejects_same_owner_cross_project_task_reference(database):
    _project_id, _source_id, item_id = seed_item(database)
    other_project = database.execute("INSERT INTO projects(owner_id,title,status) VALUES('owner','Other','in_progress') RETURNING id").fetchone()["id"]
    other_task = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('owner',%s,'Other task') RETURNING id", (other_project,)).fetchone()["id"]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            database.execute("UPDATE github_items SET task_id=%s WHERE id=%s", (other_task, item_id))


def test_database_rejects_moving_linked_source_or_task_project(database):
    project_id, source_id, item_id = seed_item(database)
    task = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('owner',%s,'Task') RETURNING id", (project_id,)).fetchone()["id"]
    other_project = database.execute("INSERT INTO projects(owner_id,title,status) VALUES('owner','Other','in_progress') RETURNING id").fetchone()["id"]
    database.execute("UPDATE github_items SET task_id=%s WHERE id=%s", (task, item_id))

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            database.execute("UPDATE repository_sources SET project_id=%s WHERE id=%s", (other_project, source_id))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            database.execute("UPDATE project_tasks SET project_id=%s WHERE id=%s", (other_project, task))


def test_duplicate_request_id_with_different_payload_conflicts(database):
    project_id, _source_id, item_id = seed_item(database)
    request_id = uuid4()
    decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("ignore", request_id=request_id))

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("restore", version=1, request_id=request_id))


def test_duplicate_request_id_for_different_item_conflicts(database):
    project_id, _source_id, item_id = seed_item(database, number=1)
    _project_id, _source_id_2, other_item_id = seed_item(database, project=project_id, number=2)
    request_id = uuid4()
    decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("ignore", request_id=request_id))

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, other_item_id, request("ignore", request_id=request_id))


def test_duplicate_request_id_for_same_item_wrong_project_conflicts(database):
    project_id, _source_id, item_id = seed_item(database, number=1)
    other_project = database.execute("INSERT INTO projects(owner_id,title,status) VALUES('owner','Other','in_progress') RETURNING id").fetchone()["id"]
    request_id = uuid4()
    payload = request("ignore", request_id=request_id)
    decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, payload)

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", other_project, item_id, payload)


def test_decision_state_machine_rejects_ignored_adoption_and_adopted_intact_changes(database):
    project_id, _source_id, item_id = seed_item(database, number=1)
    ignored = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("ignore"))
    task = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('owner',%s,'Task') RETURNING id", (project_id,)).fetchone()["id"]

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("create", version=ignored.version, title="No"))
    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("link", version=ignored.version, task_id=task))

    _project_id, _source_id_2, adopted_item_id = seed_item(database, project=project_id, number=2)
    adopted = decide_github_item(Settings(_env_file=None), "owner", project_id, adopted_item_id, request("link", task_id=task))
    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, adopted_item_id, request("ignore", version=adopted.version))
    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, adopted_item_id, request("link", version=adopted.version, task_id=task))


def test_stale_version_and_source_are_rejected(database):
    project_id, _source_id, item_id = seed_item(database)
    decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("ignore"))

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("restore", version=0))
    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("restore", version=1, source="2026-09-17T01:00:00Z"))


def test_same_timestamp_payload_change_bumps_version_and_marks_source_changed(database):
    project_id, _source_id, item_id = seed_item(database, title="Original")
    adopted = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("create", title="Adopt original"))
    assert adopted.version == 1
    assert adopted.source_changed is False

    database.execute("UPDATE github_items SET collected_at=now() WHERE id=%s", (item_id,))
    recollected = list_github_items(Settings(_env_file=None), "owner", project_id, "adopted", 20, 0).items[0]
    assert recollected.version == 1
    assert recollected.source_changed is False

    database.execute(
        """
        UPDATE github_items
        SET payload=%s::jsonb, source_updated_at='2026-09-18T01:00:00Z', collected_at=now()
        WHERE id=%s
        """,
        (Jsonb({"title": "Changed", "body": "Body", "state": "open", "html_url": "https://github.com/Owner/repo/issues/1"}), item_id),
    )
    changed = list_github_items(Settings(_env_file=None), "owner", project_id, "adopted", 20, 0).items[0]
    assert changed.version == 2
    assert changed.source_changed is True

    with pytest.raises(GitHubItemConflictError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("link", version=adopted.version, task_id=UUID(adopted.task_id)))


def test_link_requires_same_project_scope(database):
    project_id, _source_id, item_id = seed_item(database)
    other_project = database.execute("INSERT INTO projects(owner_id,title,status) VALUES('owner','Other','in_progress') RETURNING id").fetchone()["id"]
    other_task = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('owner',%s,'Other task') RETURNING id", (other_project,)).fetchone()["id"]

    with pytest.raises(GitHubItemInvalidDecisionError):
        decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("link", task_id=other_task))


def test_ignore_survives_resync_and_restore_returns_pending(database):
    project_id, _source_id, item_id = seed_item(database)
    ignored = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("ignore"))
    database.execute(
        """
        UPDATE github_items
        SET payload=%s::jsonb, source_updated_at='2026-09-18T02:00:00Z', collected_at=now()
        WHERE id=%s
        """,
        (Jsonb({"title": "Changed", "body": "New", "state": "open", "html_url": "https://github.com/Owner/repo/issues/1"}), item_id),
    )

    after_sync = list_github_items(Settings(_env_file=None), "owner", project_id, "ignored", 20, 0).items[0]
    assert after_sync.review_status == "ignored"
    assert after_sync.source_changed is True
    database.execute(
        "UPDATE github_items SET decision_source_updated_at=source_updated_at, decision_source_digest=encode(digest(payload::text, 'sha256'), 'hex') WHERE id=%s",
        (item_id,),
    )
    assert list_github_items(Settings(_env_file=None), "owner", project_id, "ignored", 20, 0).items[0].source_changed is False

    restored = decide_github_item(
        Settings(_env_file=None),
        "owner",
        project_id,
        item_id,
        request("restore", version=after_sync.version, source="2026-09-18T02:00:00Z"),
    )
    assert restored.review_status == "pending"
    assert restored.reviewed_at is None


def test_deleted_task_leaves_adopted_orphan_and_allows_relink(database):
    project_id, _source_id, item_id = seed_item(database)
    adopted = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("create", title="Adopt me"))
    database.execute("DELETE FROM project_tasks WHERE id=%s", (adopted.task_id,))
    orphan = list_github_items(Settings(_env_file=None), "owner", project_id, "adopted", 20, 0).items[0]
    replacement = database.execute("INSERT INTO project_tasks(owner_id,project_id,title) VALUES('owner',%s,'Replacement') RETURNING id", (project_id,)).fetchone()["id"]

    relinked = decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, request("link", version=orphan.version, task_id=replacement))

    assert orphan.review_status == "adopted"
    assert orphan.task_id is None
    assert relinked.task_id == str(replacement)


def test_concurrent_duplicate_request_replays_without_duplicate_work(committed_database):
    connection, _schema = committed_database
    project_id, _source_id, item_id = seed_item(connection)
    connection.commit()
    request_id = uuid4()
    payload = request("create", request_id=request_id, title="Concurrent adoption")

    def run_decision():
        return decide_github_item(Settings(_env_file=None), "owner", project_id, item_id, payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = [future.result(timeout=10) for future in [executor.submit(run_decision), executor.submit(run_decision)]]

    audits = connection.execute("SELECT COUNT(*)::int AS count FROM github_item_decision_audits WHERE request_id=%s", (request_id,)).fetchone()["count"]
    tasks = connection.execute("SELECT COUNT(*)::int AS count FROM project_tasks WHERE source_provider='github-adopted' AND source_key=%s", (f"github-item:{item_id}",)).fetchone()["count"]

    assert first.review_status == "adopted"
    assert second.review_status == "adopted"
    assert first.task_id == second.task_id
    assert audits == 1
    assert tasks == 1
