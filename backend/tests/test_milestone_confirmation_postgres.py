"""Manual acceptance must work without AI, synthetic tasks, or production data."""
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
from app.schemas.milestone_evidence import MilestoneValidationUpdate
from app.schemas.projects import ProjectTaskUpdate
from app.services import milestone_completion as service, milestone_evidence, projects
from test_project_lifecycle_postgres import committed_database


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("WORKTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("WORKTRACE_TEST_DATABASE_URL is not configured")
    with psycopg.connect(url, row_factory=dict_row) as connection:
        if connection.info.dbname != "worktrace_test":
            pytest.fail("Requires disposable worktrace_test database")
        with connection.transaction(force_rollback=True):
            schema = f"confirmation_{uuid4().hex}"
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
            for path in sorted((Path(__file__).resolve().parents[2] / "infrastructure/postgres/init").glob("*.sql")):
                connection.execute(path.read_text())
            project_id = connection.execute("INSERT INTO projects(owner_id,title) VALUES('owner','Acceptance') RETURNING id").fetchone()["id"]
            milestone_id = connection.execute(
                "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,acceptance_criteria,weight) VALUES('owner',%s,'accept','Release','Acceptance tests pass',100) RETURNING id",
                (project_id,),
            ).fetchone()["id"]

            @contextmanager
            def fake_connect(settings):
                with connection.transaction():
                    yield connection

            for module in (service, milestone_evidence, projects):
                monkeypatch.setattr(module, "connect", fake_connect)
            yield connection, project_id, milestone_id


def state(database, owner="owner"):
    connection, project_id, milestone_id = database
    return service.get_milestone_completion_in_connection(connection, owner, project_id, milestone_id)


def payload(database, **overrides):
    current = state(database)
    return MilestoneValidationUpdate(**{
        "status": "done", "expected_version": current.version, "expected_context_fingerprint": current.context_fingerprint,
        "request_id": uuid4(), "reason": "Acceptance confirmed", "evidence_note": "Manually executed acceptance steps; all passed.", **overrides,
    })


def confirm(database, request):
    _, project_id, milestone_id = database
    return milestone_evidence.update_milestone_validation_status(Settings(openai_api_key=None), "owner", project_id, milestone_id, request)


def task(database, status="done", legacy=False):
    connection, project_id, milestone_id = database
    return connection.execute(
        """INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,status,source_provider,source_key)
           VALUES('owner',%s,%s,'Work',%s,%s,%s) RETURNING id""",
        (project_id, milestone_id, status, "derived-github" if legacy else None, f"milestone-validation:{milestone_id}" if legacy else None),
    ).fetchone()["id"]


def test_manual_milestone_confirms_without_ai_or_validation_task(database):
    connection, project_id, milestone_id = database
    task_id = task(database)
    before = projects.get_project(Settings(), "owner", project_id)
    response = confirm(database, payload(database))
    assert response.completion.status == "done" and response.completion.version == 1
    assert not response.completion.is_stale and response.validation_wbs is None
    assert response.completion.history[0].actor_owner_id == "owner"
    assert response.completion.history[0].evidence_note.startswith("Manually")
    assert projects.get_project(Settings(), "owner", project_id) == before
    assert connection.execute("SELECT status_version FROM project_tasks WHERE id=%s", (task_id,)).fetchone()["status_version"] == 1
    stored = connection.execute("SELECT context_snapshot FROM project_milestone_confirmations").fetchone()["context_snapshot"]
    assert stored["milestone"]["acceptance_criteria"] == "Acceptance tests pass"


@pytest.mark.parametrize("missing_criteria,pending", [(True, False), (False, True), (True, True)])
def test_current_gate_blocks_missing_criteria_and_manual_pending_tasks(database, missing_criteria, pending):
    connection, _, milestone_id = database
    if missing_criteria:
        connection.execute("UPDATE project_milestones SET acceptance_criteria='' WHERE id=%s", (milestone_id,))
    if pending:
        task(database, status="planned")
    request = payload(database)
    assert not state(database).can_confirm
    with pytest.raises(service.MilestoneValidationBlockedError):
        confirm(database, request)
    assert state(database).version == 0


def test_legacy_validation_is_not_approval_or_a_required_work_item(database):
    connection, project_id, milestone_id = database
    checkpoint = task(database, status="planned", legacy=True)
    result = confirm(database, payload(database))
    assert result.total_wbs == 0 and result.pending_wbs == []
    assert result.validation_wbs.status == "planned" and result.completion.status == "done"
    with pytest.raises(projects.ProjectTaskValidationProtectedError):
        projects.update_project_task(Settings(), "owner", project_id, checkpoint, ProjectTaskUpdate(status="done", expected_status_version=1))
    with pytest.raises(projects.ProjectTaskValidationProtectedError):
        projects.update_project_task(Settings(), "owner", project_id, checkpoint, ProjectTaskUpdate(counts_toward_progress=False))
    with pytest.raises(projects.ProjectTaskValidationProtectedError):
        projects.delete_project_task(Settings(), "owner", project_id, checkpoint)
    for statement in ("UPDATE project_tasks SET status='done' WHERE id=%s",
                      "UPDATE project_tasks SET source_provider=NULL WHERE id=%s",
                      "DELETE FROM project_tasks WHERE id=%s"):
        with pytest.raises(psycopg.Error, match="read-only"):
            with connection.transaction():
                connection.execute(statement, (checkpoint,))
    connection.execute("DELETE FROM project_milestones WHERE id=%s", (milestone_id,))
    assert connection.execute("SELECT milestone_id FROM project_tasks WHERE id=%s", (checkpoint,)).fetchone()["milestone_id"] is None
    connection.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    assert connection.execute("SELECT id FROM project_tasks WHERE id=%s", (checkpoint,)).fetchone() is None


def test_old_done_checkpoint_does_not_create_confirmation(database):
    task(database, legacy=True)
    assert state(database).status == "planned" and state(database).history == []


def test_exact_retry_is_idempotent_even_after_context_changes(database):
    connection, _, milestone_id = database
    request = payload(database)
    confirm(database, request)
    connection.execute("UPDATE project_milestones SET acceptance_criteria='Revised criterion' WHERE id=%s", (milestone_id,))
    response = confirm(database, request)
    assert response.completion.version == 1 and response.completion.is_stale
    with pytest.raises(service.MilestoneConfirmationConflictError):
        confirm(database, request.model_copy(update={"reason": "Different request content"}))


def test_context_and_history_version_conflicts_do_not_overwrite(database):
    connection, _, milestone_id = database
    request = payload(database)
    connection.execute("UPDATE project_milestones SET acceptance_criteria='Changed' WHERE id=%s", (milestone_id,))
    with pytest.raises(service.MilestoneConfirmationConflictError):
        confirm(database, request)
    current = payload(database)
    confirm(database, current)
    with pytest.raises(service.MilestoneConfirmationConflictError):
        confirm(database, current.model_copy(update={"request_id": uuid4()}))
    assert state(database).version == 1


def test_task_reopen_marks_confirmation_stale_and_preserves_history(database):
    _, project_id, _ = database
    task_id = task(database)
    confirm(database, payload(database))
    projects.update_project_task(Settings(), "owner", project_id, task_id, ProjectTaskUpdate(status="in_progress", expected_status_version=1))
    assert state(database).is_stale and not state(database).can_confirm
    reopened = confirm(database, payload(database, status="planned", evidence_note="", reason="Additional work"))
    assert reopened.completion.status == "planned" and reopened.completion.version == 2
    assert len(reopened.completion.history) == 2
    projects.update_project_task(Settings(), "owner", project_id, task_id, ProjectTaskUpdate(status="done", expected_status_version=2))
    confirmed = confirm(database, payload(database))
    assert confirmed.completion.status == "done" and confirmed.completion.version == 3 and not confirmed.completion.is_stale


def test_confirmation_history_is_immutable_owner_scoped_and_cascades(database):
    connection, project_id, milestone_id = database
    confirm(database, payload(database))
    with pytest.raises(projects.ProjectMilestoneNotFoundError):
        state(database, "other")
    with pytest.raises(projects.ProjectMilestoneNotFoundError):
        service.confirm_milestone(Settings(), "other", project_id, milestone_id, payload(database))
    for statement in ("UPDATE project_milestone_confirmations SET reason='rewrite'", "DELETE FROM project_milestone_confirmations"):
        with pytest.raises(psycopg.Error, match="append-only"):
            with connection.transaction():
                connection.execute(statement)
    connection.execute("DELETE FROM project_milestones WHERE id=%s", (milestone_id,))
    assert connection.execute("SELECT count(*) AS total FROM project_milestone_confirmations").fetchone()["total"] == 0


def test_evidence_changes_invalidate_confirmation_and_preserve_recorded_context(database):
    connection, project_id, milestone_id = database
    repository_id = connection.execute(
        "INSERT INTO repository_sources(owner_id,project_id,provider,repository_id,full_name) VALUES('owner',%s,'github',123,'test/acceptance') RETURNING id",
        (project_id,),
    ).fetchone()["id"]
    commit_id = connection.execute(
        "INSERT INTO github_commits(owner_id,project_id,repository_source_id,sha,message) VALUES('owner',%s,%s,'abc','Initial evidence') RETURNING id",
        (project_id, repository_id),
    ).fetchone()["id"]
    connection.execute("INSERT INTO project_milestone_evidence(owner_id,project_id,milestone_id,github_commit_id) VALUES('owner',%s,%s,%s)", (project_id, milestone_id, commit_id))
    confirm(database, payload(database))
    connection.execute("UPDATE github_commits SET message='Corrected evidence' WHERE id=%s", (commit_id,))
    assert state(database).is_stale
    snapshot = connection.execute("SELECT context_snapshot FROM project_milestone_confirmations").fetchone()["context_snapshot"]
    assert snapshot["commits"][0]["message"] == "Initial evidence"


def test_confirmation_keeps_latest_20_records_and_parent_delete_cascades(database):
    connection, project_id, _ = database
    for index in range(22):
        confirm(database, payload(database, status="done" if index % 2 == 0 else "planned"))
    current = state(database)
    assert len(current.history) == 20 and current.version == 22
    assert current.history[-1].version == 3
    connection.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    assert connection.execute("SELECT count(*) AS total FROM project_milestone_confirmations").fetchone()["total"] == 0


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_confirmation_has_one_winner_or_exact_replay(committed_database, monkeypatch, same_request):
    connection = committed_database
    monkeypatch.setattr(service, "connect", projects.connect)
    project_id = connection.execute("INSERT INTO projects(owner_id,title) VALUES('owner','Concurrent acceptance') RETURNING id").fetchone()["id"]
    milestone_id = connection.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,acceptance_criteria,weight) VALUES('owner',%s,'accept','Release','Checked',100) RETURNING id", (project_id,),
    ).fetchone()["id"]
    connection.commit()
    current = service.get_milestone_completion_in_connection(connection, "owner", project_id, milestone_id)
    connection.commit()
    request = MilestoneValidationUpdate(status="done", expected_version=0, expected_context_fingerprint=current.context_fingerprint,
                                        request_id=uuid4(), reason="Accepted", evidence_note="All checks passed")

    def save(candidate):
        try:
            service.confirm_milestone(Settings(), "owner", project_id, milestone_id, candidate)
            return "ok"
        except service.MilestoneConfirmationConflictError:
            return "conflict"

    other = request if same_request else request.model_copy(update={"request_id": uuid4()})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [request, other]))
    assert sorted(results) == (["ok", "ok"] if same_request else ["conflict", "ok"])
    assert connection.execute("SELECT count(*) AS total FROM project_milestone_confirmations WHERE milestone_id=%s", (milestone_id,)).fetchone()["total"] == 1
