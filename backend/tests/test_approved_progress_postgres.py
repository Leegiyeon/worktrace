"""One approval contract must drive project, report and milestone boundaries."""
from datetime import date
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.project_plans import ProjectPlanApprove
from app.schemas.projects import ProjectTaskUpdate
from app.services import milestone_completion, project_plans, projects
from app.services.auto_report import build_auto_report_response
from app.services.weekly_report import ProjectRecord, WeeklyReportDataset
from test_milestone_confirmation_postgres import database, confirm, payload, state, task


@pytest.fixture
def planning(database, monkeypatch):
    monkeypatch.setattr(project_plans, "connect", projects.connect)
    return database


def approve(planning, **overrides):
    _, project_id, _ = planning
    current = project_plans.get_project_plan(Settings(), "owner", project_id)
    request = ProjectPlanApprove(**{
        "policy": "wbs", "reason": "Reviewed current scope", "expected_version": current.version,
        "expected_context_fingerprint": current.context_fingerprint, "request_id": uuid4(), **overrides,
    })
    return project_plans.approve_project_plan(Settings(), "owner", project_id, request)


def summary(planning):
    return projects.get_project(Settings(), "owner", planning[1])


def seed_weighted_scope(planning):
    connection, project_id, first = planning
    connection.execute("UPDATE project_milestones SET weight=50 WHERE id=%s", (first,))
    second = connection.execute(
        "INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,weight) VALUES('owner',%s,'second','Second',50) RETURNING id",
        (project_id,),
    ).fetchone()["id"]
    task(planning)
    task(planning)
    pending = task(planning, status="planned")
    connection.execute("INSERT INTO project_tasks(owner_id,project_id,milestone_id,title,status) VALUES('owner',%s,%s,'Second work','planned')", (project_id, second))
    return pending


def test_unapproved_plan_is_not_progress_even_when_project_is_done(planning):
    connection, project_id, _ = planning
    task(planning)
    connection.execute("UPDATE projects SET status='done' WHERE id=%s", (project_id,))
    result = summary(planning)
    assert result.total_tasks == result.completed_tasks == 1
    assert result.progress_percent is None and result.progress_plan_status == "unapproved"
    assert result.progress_basis == "unscoped" and result.progress_plan_version == 0


def test_explicit_wbs_and_weighted_policies_share_summary_list_and_report(planning):
    seed_weighted_scope(planning)
    approve(planning)
    wbs = summary(planning)
    assert wbs.progress_basis == "wbs" and wbs.progress_percent == 50
    approve(planning, policy="milestone")
    weighted = summary(planning)
    assert weighted.progress_basis == "milestone" and weighted.progress_percent == 33
    assert weighted.progress_plan_version == 2 and weighted.progress_plan_status == "approved"
    assert weighted == next(p for p in projects.list_projects(Settings(), "owner") if p.id == weighted.id)
    dataset = WeeklyReportDataset(projects=[ProjectRecord(weighted.id, weighted.title, "", "in_progress", "", weighted.updated_at)])
    report = build_auto_report_response(dataset, "weekly", date(2026, 9, 14), date(2026, 9, 18), [weighted])
    candidate = report.progress_candidates[0]
    assert (candidate.progress_percent, candidate.total_tasks, candidate.completed_tasks) == (33, 4, 2)
    assert candidate.progress_plan_version == 2 and "계획 v2" in candidate.reason


def test_status_changes_update_progress_without_reapproving(planning):
    pending = seed_weighted_scope(planning)
    approval = approve(planning)
    projects.update_project_task(Settings(), "owner", planning[1], pending, ProjectTaskUpdate(status="done", expected_status_version=1))
    result = summary(planning)
    assert result.progress_percent == 75 and result.progress_plan_version == approval.version
    assert result.progress_plan_status == "approved"
    projects.update_project_task(Settings(), "owner", planning[1], pending, ProjectTaskUpdate(status="planned", expected_status_version=2))
    assert summary(planning).progress_percent == 50


def test_weighted_policy_never_silently_falls_back_after_unassignment(planning):
    pending = seed_weighted_scope(planning)
    approve(planning, policy="milestone")
    projects.update_project_task(Settings(), "owner", planning[1], pending, ProjectTaskUpdate(milestone_id=None))
    stale = summary(planning)
    assert stale.progress_plan_status == "stale" and stale.progress_percent is None
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        approve(planning, policy="milestone")
    approve(planning, policy="wbs")
    assert summary(planning).progress_percent == 50 and summary(planning).progress_basis == "wbs"


@pytest.mark.parametrize("mutation", ["title", "description", "counts_toward_progress", "delete", "weight"])
def test_scope_mutations_invalidate_approved_progress(planning, mutation):
    connection, _, milestone_id = planning
    task_id = task(planning)
    approve(planning)
    if mutation == "delete":
        projects.delete_project_task(Settings(), "owner", planning[1], task_id)
    elif mutation == "weight":
        connection.execute("UPDATE project_milestones SET weight=90 WHERE id=%s", (milestone_id,))
    else:
        updates = {mutation: False if mutation == "counts_toward_progress" else "Scope changed"}
        projects.update_project_task(Settings(), "owner", planning[1], task_id, ProjectTaskUpdate(**updates))
    result = summary(planning)
    assert result.progress_plan_status == "stale" and result.progress_percent is None
    assert result.progress_plan_version == 1


def test_non_scope_metadata_does_not_reset_approval(planning):
    task_id = task(planning)
    approve(planning)
    projects.update_project_task(Settings(), "owner", planning[1], task_id, ProjectTaskUpdate(priority="high", due_date=date(2026, 10, 1)))
    assert summary(planning).progress_plan_status == "approved"


def test_legacy_checkpoint_excluded_and_derived_requires_explicit_review(planning):
    connection, _, _ = planning
    task(planning, status="planned", legacy=True)
    derived = task(planning)
    connection.execute("UPDATE project_tasks SET source_provider='derived-github',source_key='commit-milestone:test' WHERE id=%s", (derived,))
    result = summary(planning)
    assert (result.total_tasks, result.completed_tasks, result.derived_task_count) == (1, 1, 1)
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        approve(planning)
    approve(planning, reviewed_derived=True)
    assert summary(planning).progress_percent == 100
    milestone = projects.get_project_milestone(Settings(), "owner", planning[1], planning[2])
    assert milestone.total_tasks == milestone.completed_tasks == 1


def test_exclusion_checkbox_cannot_bypass_manual_confirmation(planning):
    task(planning)
    excluded = task(planning, status="planned")
    projects.update_project_task(Settings(), "owner", planning[1], excluded, ProjectTaskUpdate(counts_toward_progress=False))
    assert not state(planning).can_confirm
    with pytest.raises(milestone_completion.MilestoneValidationBlockedError):
        confirm(planning, payload(planning))
    with pytest.raises(project_plans.ProjectPlanPolicyError):
        approve(planning)
    approve(planning, exclusion_reason="Follow-up is explicitly outside this delivery.")
    assert state(planning).can_confirm
    confirm(planning, payload(planning))
    projects.update_project_task(Settings(), "owner", planning[1], excluded, ProjectTaskUpdate(description="Changed exclusion scope"))
    assert state(planning).is_stale and not state(planning).can_confirm
    assert summary(planning).progress_percent is None
