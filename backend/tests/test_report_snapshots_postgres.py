"""Report snapshot persistence regressions on disposable worktrace_test."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.report_snapshots import ReportSnapshotCreate
from app.schemas.reports import AutoReportRequest
from app.services import auto_report, projects, report_snapshots


@pytest.fixture
def committed_database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    connection = psycopg.connect(url, row_factory=dict_row)
    schema = f"report_snapshots_{uuid4().hex}"
    try:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("Requires disposable worktrace_test database")
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

        monkeypatch.setattr(report_snapshots, "connect", fake_connect)
        monkeypatch.setattr(auto_report, "connect", fake_connect)
        monkeypatch.setattr(projects, "connect", fake_connect)
        yield connection
    finally:
        connection.rollback()
        connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        connection.commit()
        connection.close()


def snapshot_request(**overrides):
    payload = {
        "request_id": uuid4(),
        "report_type": "daily",
        "start_date": date(2026, 9, 18),
        "end_date": date(2026, 9, 18),
    }
    payload.update(overrides)
    return ReportSnapshotCreate(**payload)


def seed_report_source(connection, *, owner="owner", title="Snapshot project"):
    project_id = connection.execute(
        "INSERT INTO projects(owner_id,title,status,role,updated_at) VALUES(%s,%s,'in_progress','Lead','2026-09-18') RETURNING id",
        (owner, title),
    ).fetchone()["id"]
    task_id = connection.execute(
        "INSERT INTO project_tasks(owner_id,project_id,title,status,due_date) VALUES(%s,%s,'Snapshot task','planned','2026-09-20') RETURNING id",
        (owner, project_id),
    ).fetchone()["id"]
    log_id = connection.execute(
        "INSERT INTO work_logs(owner_id,project_id,log_date,title,content,blockers) VALUES(%s,%s,'2026-09-18','Snapshot log','Original content','Original blocker') RETURNING id",
        (owner, project_id),
    ).fetchone()["id"]
    connection.commit()
    return project_id, task_id, log_id


def test_create_rejects_unexpected_fields_and_does_not_accept_client_report_payload():
    with pytest.raises(ValueError):
        ReportSnapshotCreate(
            request_id=uuid4(),
            report_type="daily",
            start_date=date(2026, 9, 18),
            end_date=date(2026, 9, 18),
            report={"markdown": "trusted client payload"},
        )


def test_owner_isolation_list_get_delete_and_request_scope(committed_database, monkeypatch):
    seed_report_source(committed_database)
    seed_report_source(committed_database, owner="other", title="Other snapshot")
    request_id = uuid4()

    owner_snapshot = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request(request_id=request_id))
    other_snapshot = report_snapshots.create_report_snapshot(Settings(_env_file=None), "other", snapshot_request(request_id=request_id))

    assert owner_snapshot.request_id == other_snapshot.request_id == str(request_id)
    assert owner_snapshot.id != other_snapshot.id
    assert [item.id for item in report_snapshots.list_report_snapshots(Settings(_env_file=None), "owner").items] == [owner_snapshot.id]
    past_end = report_snapshots.list_report_snapshots(Settings(_env_file=None), "owner", limit=20, offset=10)
    assert past_end.items == [] and past_end.total == 1
    with pytest.raises(report_snapshots.ReportSnapshotNotFoundError):
        report_snapshots.get_report_snapshot(Settings(_env_file=None), "other", UUID(owner_snapshot.id))
    report_snapshots.delete_report_snapshot(Settings(_env_file=None), "owner", UUID(owner_snapshot.id))
    with pytest.raises(report_snapshots.ReportSnapshotNotFoundError):
        report_snapshots.get_report_snapshot(Settings(_env_file=None), "owner", UUID(owner_snapshot.id))
    assert report_snapshots.get_report_snapshot(Settings(_env_file=None), "other", UUID(other_snapshot.id)).id == other_snapshot.id


def test_same_request_id_replays_without_regeneration_and_changed_period_conflicts(committed_database, monkeypatch):
    seed_report_source(committed_database)
    calls = 0
    original = report_snapshots.generate_auto_report

    def counted(settings, owner_id, request):
        nonlocal calls
        calls += 1
        return original(settings, owner_id, request)

    monkeypatch.setattr(report_snapshots, "generate_auto_report", counted)
    request_id = uuid4()
    request = snapshot_request(request_id=request_id)

    first = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", request)
    second = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", request)

    assert first.id == second.id
    assert calls == 1
    with pytest.raises(report_snapshots.ReportSnapshotConflictError):
        report_snapshots.create_report_snapshot(
            Settings(_env_file=None),
            "owner",
            snapshot_request(request_id=request_id, report_type="weekly", start_date=date(2026, 9, 15)),
        )


def test_concurrent_same_request_has_one_row_and_one_generation(committed_database, monkeypatch):
    seed_report_source(committed_database)
    calls = 0
    original = report_snapshots.generate_auto_report

    request = snapshot_request()

    def counted(settings, owner_id, payload):
        nonlocal calls
        calls += 1
        return original(settings, owner_id, payload)

    monkeypatch.setattr(report_snapshots, "generate_auto_report", counted)

    def create():
        return report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", request).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert results[0] == results[1]
    assert calls == 1
    assert committed_database.execute("SELECT count(*) AS total FROM report_snapshots").fetchone()["total"] == 1


def test_new_request_id_creates_intentional_version_even_when_content_identical(committed_database, monkeypatch):
    seed_report_source(committed_database)
    same_report = report_snapshots.generate_auto_report(
        Settings(_env_file=None),
        "owner",
        AutoReportRequest(report_type="daily", start_date=date(2026, 9, 18), end_date=date(2026, 9, 18)),
    )
    monkeypatch.setattr(report_snapshots, "generate_auto_report", lambda settings, owner, request: same_report)
    first = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request())
    second = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request())

    assert first.id != second.id
    assert first.report.markdown == second.report.markdown
    assert committed_database.execute("SELECT count(*) AS total FROM report_snapshots").fetchone()["total"] == 2


def test_source_deletion_keeps_exact_original_report(committed_database, monkeypatch):
    project_id, _task_id, _log_id = seed_report_source(committed_database)
    snapshot = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request())
    original_payload = snapshot.report.model_dump(mode="json")

    committed_database.execute("DELETE FROM projects WHERE owner_id='owner' AND id=%s", (project_id,))
    committed_database.commit()

    reread = report_snapshots.get_report_snapshot(Settings(_env_file=None), "owner", UUID(snapshot.id))
    assert reread.report.model_dump(mode="json") == original_payload
    assert "Snapshot project" in reread.report.markdown


def test_migration_rejects_update_but_allows_delete(committed_database, monkeypatch):
    seed_report_source(committed_database)
    snapshot = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request())

    with pytest.raises(psycopg.errors.RaiseException):
        committed_database.execute("UPDATE report_snapshots SET fingerprint=repeat('0', 64) WHERE id=%s", (snapshot.id,))
    committed_database.rollback()
    committed_database.execute("DELETE FROM report_snapshots WHERE id=%s", (snapshot.id,))
    committed_database.commit()
    assert committed_database.execute("SELECT count(*) AS total FROM report_snapshots").fetchone()["total"] == 0


def test_integrity_corruption_detected(committed_database, monkeypatch):
    seed_report_source(committed_database)
    snapshot = report_snapshots.create_report_snapshot(Settings(_env_file=None), "owner", snapshot_request())

    committed_database.execute("ALTER TABLE report_snapshots DISABLE TRIGGER trg_report_snapshots_immutable_update")
    committed_database.execute(
        "UPDATE report_snapshots SET report_payload = jsonb_set(report_payload, '{markdown}', to_jsonb('corrupted'::text)) WHERE id=%s",
        (snapshot.id,),
    )
    committed_database.execute("ALTER TABLE report_snapshots ENABLE TRIGGER trg_report_snapshots_immutable_update")
    committed_database.commit()

    with pytest.raises(report_snapshots.ReportSnapshotIntegrityError):
        report_snapshots.get_report_snapshot(Settings(_env_file=None), "owner", UUID(snapshot.id))
