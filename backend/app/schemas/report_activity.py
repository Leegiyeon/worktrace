from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ProgressPlanStatus = Literal["unapproved", "approved", "stale"]
TaskHistorySource = Literal["user", "milestone_validation", "system"]


class TaskTransition(BaseModel):
    id: str
    project_id: str
    project_title: str
    task_id: str
    task_title: str
    current_status: str
    previous_status: str | None = None
    next_status: str
    source: TaskHistorySource
    reason: str | None = None
    changed_at: str
    status_version: int


class CurrentReportTask(BaseModel):
    id: str
    project_id: str
    project_title: str
    title: str
    status: str
    due_date: str | None = None
    source_provider: str | None = None
    progress_plan_status: ProgressPlanStatus = "unapproved"
    progress_plan_version: int = 0


class ReportIssue(BaseModel):
    id: str
    project_id: str | None = None
    project_title: str
    title: str
    blockers: str
    log_date: str
    updated_at: str


class ReportOutcome(BaseModel):
    id: str
    project_id: str
    project_title: str
    title: str
    outcome_type: str
    before_state: str
    after_state: str
    metric_name: str
    metric_value: str | None = None
    metric_unit: str
    updated_at: str
    evidence_work_log_ids: list[str] = Field(default_factory=list)
    evidence_document_ids: list[str] = Field(default_factory=list)


class ReportActivity(BaseModel):
    schema_version: Literal["1"] = "1"
    as_of: str
    timezone: str
    start_at: str
    end_exclusive: str
    fingerprint: str = ""
    transitions: list[TaskTransition] = Field(default_factory=list)
    current_tasks: list[CurrentReportTask] = Field(default_factory=list)
    issues: list[ReportIssue] = Field(default_factory=list)
    outcomes: list[ReportOutcome] = Field(default_factory=list)
