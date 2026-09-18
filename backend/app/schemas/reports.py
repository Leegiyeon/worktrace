from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from app.schemas.report_activity import ReportActivity

ProjectStatus = Literal["idea", "review", "in_progress", "on_hold", "done"]
ReportProgressBasis = Literal["milestone", "wbs", "unscoped", "unknown"]
ItemType = Literal["task", "decision", "risk", "career_candidate", "next_check"]
ReportType = Literal["daily", "weekly", "monthly"]
WorkType = Literal[
    "planning",
    "meeting",
    "research",
    "deliverable",
    "development",
    "testing",
    "reporting",
    "coordination",
    "problem_solving",
    "other",
]


class WeeklyReportRequest(BaseModel):
    start_date: date = Field(..., description="Report period start date, inclusive")
    end_date: date = Field(..., description="Report period end date, inclusive")

    @model_validator(mode="after")
    def validate_period(self) -> "WeeklyReportRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 6:
            raise ValueError("weekly report range cannot exceed 7 days")
        return self


class AutoReportRequest(BaseModel):
    report_type: ReportType
    start_date: date = Field(..., description="Report period start date, inclusive")
    end_date: date = Field(..., description="Report period end date, inclusive")

    @model_validator(mode="after")
    def validate_period(self) -> "AutoReportRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        days = (self.end_date - self.start_date).days
        if self.report_type == "daily" and days > 0:
            raise ValueError("daily report range must be one day")
        if self.report_type == "weekly" and days > 6:
            raise ValueError("weekly report range cannot exceed 7 days")
        if self.report_type == "monthly" and days > 31:
            raise ValueError("monthly report range cannot exceed 32 days")
        return self


class WorkLogCreate(BaseModel):
    log_date: date
    work_type: WorkType = "other"
    title: str = Field(..., min_length=1, max_length=160)
    content: str = ""
    decisions: str = ""
    collaborators: str = ""
    next_actions: str = ""
    duration_minutes: int = Field(default=0, ge=0)
    blockers: str = ""
    project_id: UUID | None = None


class WorkLogUpdate(BaseModel):
    log_date: date | None = None
    work_type: WorkType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = None
    decisions: str | None = None
    collaborators: str | None = None
    next_actions: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    blockers: str | None = None
    project_id: UUID | None = None


class WorkLogItem(BaseModel):
    id: str
    log_date: date
    work_type: WorkType = "other"
    title: str
    content: str = ""
    decisions: str = ""
    collaborators: str = ""
    next_actions: str = ""
    duration_minutes: int = 0
    blockers: str = ""
    project_id: str | None = None
    project_title: str = ""
    updated_at: str


class DocumentReportItem(BaseModel):
    id: str
    filename: str
    summary: str = ""
    document_type: str = ""
    analysis_status: str = "pending"
    updated_at: str


class ExtractedReportItem(BaseModel):
    id: str
    item_type: ItemType
    title: str
    content: str = ""
    status: str = "open"
    due_date: str | None = None
    updated_at: str


class TaskAlert(BaseModel):
    project_id: str
    project_title: str
    title: str
    status: str
    due_date: str | None = None
    is_delayed: bool


class ProjectProgressCandidate(BaseModel):
    project_id: str
    project_title: str
    current_status: ProjectStatus
    total_tasks: int | None = None
    completed_tasks: int | None = None
    derived_task_count: int | None = None
    progress_basis: ReportProgressBasis = "unknown"
    progress_percent: int | None = None
    suggested_progress_percent: int | None = None
    progress_plan_status: str | None = None
    progress_plan_version: int | None = None
    provenance: str
    as_of: str
    reason: str


class MonthlyPerformanceCandidate(BaseModel):
    project_id: str
    project_title: str
    qualitative_improvement: str
    evidence: list[str]
    requires_user_metric_confirmation: bool = True
    resume_ready: bool = False


class ProjectWeeklyReport(BaseModel):
    id: str
    title: str
    description: str = ""
    status: ProjectStatus
    role: str = ""
    updated_at: str
    documents: list[DocumentReportItem]
    tasks: list[ExtractedReportItem]
    decisions: list[ExtractedReportItem]
    risks: list[ExtractedReportItem]
    next_checks: list[str]
    career_summary: str = ""


class WeeklyReportResponse(BaseModel):
    start_date: date
    end_date: date
    markdown: str
    projects: list[ProjectWeeklyReport]


class AutoReportResponse(BaseModel):
    report_type: ReportType
    start_date: date
    end_date: date
    markdown: str
    work_logs: list[WorkLogItem]
    projects: list[ProjectWeeklyReport]
    remaining_tasks: list[TaskAlert]
    delayed_tasks: list[TaskAlert]
    progress_candidates: list[ProjectProgressCandidate]
    monthly_performance_candidates: list[MonthlyPerformanceCandidate]
    activity: ReportActivity | None = None
