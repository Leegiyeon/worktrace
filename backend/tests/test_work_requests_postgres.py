"""Request idempotency, owner isolation and WBS separation on disposable worktrace_test."""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.work_requests import WorkRequestCreate
from app.services import work_requests
from app.services.projects import ProjectNotFoundError


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    connection = psycopg.connect(url, row_factory=dict_row)
    if connection.info.dbname != "worktrace_test":
        connection.close()
        pytest.fail("Requires disposable worktrace_test database")
    schema = f"requests_{uuid4().hex}"
    try:
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

        monkeypatch.setattr(work_requests, "connect", fake_connect)
        yield connection
    finally:
        connection.rollback()
        connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        connection.commit()
        connection.close()


def test_request_replay_scope_and_progress_separation(database):
    project_id = database.execute(
        "INSERT INTO projects(owner_id,title) VALUES('owner','결틈') RETURNING id"
    ).fetchone()["id"]
    other_id = database.execute(
        "INSERT INTO projects(owner_id,title) VALUES('other','별도') RETURNING id"
    ).fetchone()["id"]
    database.commit()
    settings = Settings(_env_file=None)
    request_id = uuid4()
    payload = WorkRequestCreate(
        request_id=request_id, title="공유 개선", body="모바일 퍼널",
        desired_outcome="클릭률 증가", constraints="신규 이미지 없음", source="chat",
    )
    first = work_requests.create_work_request(settings, "owner", project_id, payload)
    replay = work_requests.create_work_request(settings, "owner", project_id, payload)
    assert first.id == replay.id
    assert first.source == "chat"
    assert work_requests.list_work_requests(settings, "owner", project_id).total == 1
    assert work_requests.list_work_requests(settings, "other", other_id).total == 0
    assert database.execute("SELECT COUNT(*) AS count FROM project_tasks").fetchone()["count"] == 0
    with pytest.raises(work_requests.WorkRequestConflictError):
        work_requests.create_work_request(
            settings, "owner", project_id, payload.model_copy(update={"body": "changed"})
        )
    with pytest.raises(work_requests.WorkRequestConflictError):
        other_project = database.execute(
            "INSERT INTO projects(owner_id,title) VALUES('owner','다른 프로젝트') RETURNING id"
        ).fetchone()["id"]
        database.commit()
        work_requests.create_work_request(settings, "owner", other_project, payload)
    with pytest.raises(ProjectNotFoundError):
        work_requests.list_work_requests(settings, "other", project_id)
    assert work_requests.create_work_request(settings, "other", other_id, payload).id != first.id


def test_concurrent_replay_creates_one_request(database):
    project_id = database.execute(
        "INSERT INTO projects(owner_id,title) VALUES('owner','결틈') RETURNING id"
    ).fetchone()["id"]
    database.commit()
    payload = WorkRequestCreate(request_id=uuid4(), title="재시도")

    def create(_):
        return work_requests.create_work_request(Settings(_env_file=None), "owner", project_id, payload).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(create, range(2))
    assert first == second
    assert work_requests.list_work_requests(Settings(_env_file=None), "owner", project_id).total == 1
