import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import Settings
from app.schemas.project_plans import ProjectPlanApprove
from app.services import project_plans, projects
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
            schema = f"project_plan_{uuid4().hex}"
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
            for path in sorted((Path(__file__).resolve().parents[2] / "infrastructure/postgres/init").glob("*.sql")):
                connection.execute(path.read_text())

            @contextmanager
            def fake_connect(settings):
                with connection.transaction():
                    yield connection

            monkeypatch.setattr(project_plans, "connect", fake_connect)
            yield connection


def seed_project(connection):
    project_id = connection.execute("INSERT INTO projects(owner_id,title) VALUES('owner','Plan') RETURNING id").fetchone()["id"]
    milestone_id = connection.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,weight) VALUES('owner',%s,'m1','M1',100) RETURNING id",
        (project_id,),
    ).fetchone()["id"]
    return project_id, milestone_id


def approve_payload(plan, **overrides):
    data = {
        "policy": "wbs",
        "reason": "Owner approved current WBS scope.",
        "expected_version": plan.version,
        "expected_context_fingerprint": plan.context_fingerprint,
        "request_id": uuid4(),
    }
    data.update(overrides)
    return ProjectPlanApprove(**data)


def test_context_excludes_legacy_validation_and_status_changes_do_not_stale(database):
    project_id, milestone_id = seed_project(database)
    counted_id = database.execute(
        """
        INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,description,status,source_provider,source_key)
        VALUES('owner',%s,%s,'Counted','Scope text','planned','github','issue:1') RETURNING id
        """,
        (project_id, milestone_id),
    ).fetchone()["id"]
    database.execute(
        """
        INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,status,source_provider,source_key)
        VALUES('owner',%s,%s,'Legacy','planned','derived-github',%s)
        """,
        (project_id, milestone_id, f"milestone-validation:{milestone_id}"),
    )

    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    assert plan.status == "unapproved"
    assert [task.title for task in plan.tasks] == ["Counted"]
    approved = project_plans.approve_project_plan(
        Settings(_env_file=None), "owner", project_id, approve_payload(plan, reviewed_derived=False)
    )
    assert approved.status == "approved" and approved.version == 1

    database.execute("UPDATE project_tasks SET status='done', updated_at=now() WHERE id=%s", (counted_id,))
    assert project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id).status == "approved"
    database.execute("UPDATE project_tasks SET title='Renamed scope' WHERE id=%s", (counted_id,))
    assert project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id).status == "stale"


def test_context_keeps_matching_validation_key_when_source_provider_is_null(database):
    project_id, milestone_id = seed_project(database)
    database.execute(
        """
        INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,source_provider,source_key)
        VALUES('owner',%s,%s,'Manual validation-shaped key',NULL,%s)
        """,
        (project_id, milestone_id, f"milestone-validation:{milestone_id}"),
    )

    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)

    assert [task.title for task in plan.tasks] == ["Manual validation-shaped key"]
    assert plan.total_tasks == 1


def test_approval_policy_gates_exclusions_derived_and_milestone_weights(database):
    project_id, milestone_id = seed_project(database)
    database.execute(
        """
        INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,counts_toward_progress,source_provider,source_key)
        VALUES('owner',%s,%s,'Derived counted',true,'derived-github','commit-milestone:x'),
              ('owner',%s,%s,'Excluded',false,NULL,NULL)
        """,
        (project_id, milestone_id, project_id, milestone_id),
    )
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)

    with pytest.raises(project_plans.ProjectPlanPolicyError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan))
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, reviewed_derived=True))

    approved = project_plans.approve_project_plan(
        Settings(_env_file=None),
        "owner",
        project_id,
        approve_payload(plan, reviewed_derived=True, exclusion_reason="Reference-only task excluded."),
    )
    assert approved.status == "approved" and approved.derived_task_count == 1
    assert [(task.id, task.title) for task in approved.excluded_tasks] == [(approved.excluded_tasks[0].id, "Excluded")]


def test_milestone_policy_requires_full_weighted_scope(database):
    project_id, milestone_id = seed_project(database)
    second_milestone = database.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,weight) VALUES('owner',%s,'m2','M2',1) RETURNING id",
        (project_id,),
    ).fetchone()["id"]
    database.execute("UPDATE project_milestones SET weight=99 WHERE id=%s", (milestone_id,))
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Scoped')", (project_id, milestone_id))
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    assert plan.policy_errors["wbs"] == []
    assert "가중치가 있는 모든 마일스톤" in plan.policy_errors["milestone"][-1]
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, policy="milestone"))
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Scoped 2')", (project_id, second_milestone))
    fresh = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    assert fresh.policy_errors["milestone"] == []


def test_replay_conflict_append_only_and_parent_cascade(database):
    project_id, milestone_id = seed_project(database)
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Scoped')", (project_id, milestone_id))
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    request = approve_payload(plan)
    first = project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, request)
    replay = project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, request)
    assert replay.version == first.version == 1
    with pytest.raises(project_plans.ProjectPlanRequestConflictError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, request.model_copy(update={"reason": "Changed"}))
    for statement in ("UPDATE project_plan_approvals SET reason='rewrite'", "DELETE FROM project_plan_approvals"):
        with pytest.raises(psycopg.Error, match="append-only"):
            with database.transaction():
                database.execute(statement)
    database.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    assert database.execute("SELECT count(*) AS total FROM project_plan_approvals").fetchone()["total"] == 0


def test_empty_counted_scope_cannot_be_approved(database):
    project_id, milestone_id = seed_project(database)
    database.execute(
        "INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,counts_toward_progress) VALUES('owner',%s,%s,'Reference only',false)",
        (project_id, milestone_id),
    )
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    assert plan.total_tasks == 0 and plan.excluded_tasks[0].title == "Reference only"
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, exclusion_reason="Reference only."))


def test_version_and_fingerprint_conflicts_do_not_approve(database):
    project_id, milestone_id = seed_project(database)
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Scoped')", (project_id, milestone_id))
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)

    with pytest.raises(project_plans.ProjectPlanConflictError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, expected_version=99))
    with pytest.raises(project_plans.ProjectPlanConflictError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, expected_context_fingerprint="0" * 64))

    approved = project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan))
    with pytest.raises(project_plans.ProjectPlanConflictError):
        project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(plan, expected_version=approved.version - 1))
    assert database.execute("SELECT count(*) AS total FROM project_plan_approvals WHERE project_id=%s", (project_id,)).fetchone()["total"] == 1


def test_owner_isolation_and_request_id_scope(database):
    request_id = uuid4()
    project_id, milestone_id = seed_project(database)
    other_project = database.execute("INSERT INTO projects(owner_id,title) VALUES('other','Other Plan') RETURNING id").fetchone()["id"]
    other_milestone = database.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,weight) VALUES('other',%s,'m1','M1',100) RETURNING id",
        (other_project,),
    ).fetchone()["id"]
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Owner scoped')", (project_id, milestone_id))
    database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('other',%s,%s,'Other scoped')", (other_project, other_milestone))

    owner_plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    other_plan = project_plans.get_project_plan(Settings(_env_file=None), "other", other_project)
    owner_approval = project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, approve_payload(owner_plan, request_id=request_id))
    other_approval = project_plans.approve_project_plan(Settings(_env_file=None), "other", other_project, approve_payload(other_plan, request_id=request_id))

    assert owner_approval.version == other_approval.version == 1
    assert [task.title for task in owner_approval.tasks] == ["Owner scoped"]
    with pytest.raises(project_plans.ProjectPlanNotFoundError):
        project_plans.get_project_plan(Settings(_env_file=None), "other", project_id)
    assert database.execute("SELECT count(*) AS total FROM project_plan_approvals WHERE request_id=%s", (request_id,)).fetchone()["total"] == 2


def test_plan_history_returns_latest_20_records(database):
    project_id, milestone_id = seed_project(database)
    task_id = database.execute(
        "INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Scoped 00') RETURNING id",
        (project_id, milestone_id),
    ).fetchone()["id"]

    for index in range(22):
        plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
        project_plans.approve_project_plan(
            Settings(_env_file=None),
            "owner",
            project_id,
            approve_payload(plan, reason=f"Approved scope version {index}.", request_id=uuid4()),
        )
        database.execute("UPDATE project_tasks SET title=%s WHERE id=%s", (f"Scoped {index + 1:02d}", task_id))

    current = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)

    assert current.version == 22
    assert len(current.history) == 20
    assert current.history[0].version == 22
    assert current.history[-1].version == 3


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_approval_has_one_winner_or_exact_replay(committed_database, monkeypatch, same_request):
    monkeypatch.setattr(project_plans, "connect", projects.connect)
    project_id, milestone_id = seed_project(committed_database)
    committed_database.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title) VALUES('owner',%s,%s,'Concurrent scope')", (project_id, milestone_id))
    committed_database.commit()
    plan = project_plans.get_project_plan(Settings(_env_file=None), "owner", project_id)
    request = approve_payload(plan)
    other = request if same_request else approve_payload(plan)

    def save(payload):
        try:
            project_plans.approve_project_plan(Settings(_env_file=None), "owner", project_id, payload)
            return "ok"
        except project_plans.ProjectPlanConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(save, [request, other]))

    assert results == (["ok", "ok"] if same_request else ["conflict", "ok"])
    assert committed_database.execute("SELECT count(*) AS total FROM project_plan_approvals WHERE project_id=%s", (project_id,)).fetchone()["total"] == 1
