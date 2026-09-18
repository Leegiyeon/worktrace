from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProjectStatus = Literal["idea", "review", "in_progress", "on_hold", "done"]
ProjectServiceStatus = Literal["unknown", "not_released", "operating", "retired"]
TaskStatus = Literal["planned", "in_progress", "done", "on_hold"]
TaskPriority = Literal["low", "medium", "high"]
ProgressBasis = Literal["milestone", "wbs", "unscoped"]


class ProjectBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("title", check_fields=False)
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value


class ProjectCreate(ProjectBaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = ""
    objective: str = ""
    success_criteria: str = ""
    status: ProjectStatus = "idea"
    role: str = ""

    @field_validator("status")
    @classmethod
    def initial_status_must_not_be_done(cls, value: ProjectStatus) -> ProjectStatus:
        if value == "done":
            raise ValueError("initial done status requires explicit lifecycle confirmation")
        return value


class ProjectUpdate(ProjectBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    objective: str | None = None
    success_criteria: str | None = None
    status: ProjectStatus | None = None
    role: str | None = None


class ProjectSummary(ProjectBaseModel):
    id: str
    title: str
    description: str = ""
    objective: str = ""
    success_criteria: str = ""
    status: ProjectStatus
    service_status: ProjectServiceStatus = "unknown"
    development_ended_on: date | None = None
    lifecycle_version: int = 0
    lifecycle_confirmed_at: datetime | None = None
    role: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    remaining_tasks: int = 0
    derived_task_count: int = 0
    milestone_count: int = 0
    progress_basis: ProgressBasis = "unscoped"
    progress_percent: int | None = None
    progress_plan_status: Literal["unapproved", "approved", "stale"] = "unapproved"
    progress_plan_version: int = 0
    updated_at: str


class ProjectLifecycleConfirm(ProjectBaseModel):
    status: ProjectStatus
    service_status: ProjectServiceStatus
    reason: str = Field(..., min_length=1, max_length=2000)
    incomplete_reason: str | None = Field(default=None, max_length=2000)
    development_ended_on: date | None = None
    expected_version: int = Field(..., ge=0)
    request_id: UUID

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value

    @field_validator("incomplete_reason", mode="before")
    @classmethod
    def blank_incomplete_reason_is_unknown(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProjectLifecycleHistoryItem(ProjectBaseModel):
    id: str
    actor_owner_id: str
    previous_status: ProjectStatus
    status: ProjectStatus
    previous_service_status: ProjectServiceStatus
    service_status: ProjectServiceStatus
    reason: str
    incomplete_reason: str = ""
    development_ended_on: date | None = None
    confirmed_at: datetime


class ProjectLifecycle(ProjectBaseModel):
    status: ProjectStatus
    service_status: ProjectServiceStatus
    development_ended_on: date | None = None
    lifecycle_version: int
    lifecycle_confirmed_at: datetime | None = None
    pending_task_count: int
    history: list[ProjectLifecycleHistoryItem] = Field(default_factory=list)


class ProjectMilestoneCreate(ProjectBaseModel):
    milestone_key: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    acceptance_criteria: str = ""
    weight: int = Field(..., ge=1, le=100)
    sort_order: int = Field(default=0, ge=0)


class ProjectMilestoneUpdate(ProjectBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    acceptance_criteria: str | None = None
    weight: int | None = Field(default=None, ge=1, le=100)
    sort_order: int | None = Field(default=None, ge=0)


class ProjectMilestone(ProjectBaseModel):
    id: str
    project_id: str
    milestone_key: str
    title: str
    description: str = ""
    acceptance_criteria: str = ""
    weight: int
    sort_order: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    derived_task_count: int = 0
    progress_percent: int = 0
    updated_at: str


class ProjectTaskCreate(ProjectBaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    status: TaskStatus = "planned"
    status_reason: str | None = Field(default=None, max_length=2000)
    priority: TaskPriority = "medium"
    due_date: date | None = None
    milestone_id: UUID | None = None
    counts_toward_progress: bool = True


class ProjectTaskUpdate(ProjectBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    status: TaskStatus | None = None
    status_reason: str | None = Field(default=None, max_length=2000)
    expected_status_version: int | None = Field(default=None, ge=0)
    priority: TaskPriority | None = None
    due_date: date | None = None
    milestone_id: UUID | None = None
    counts_toward_progress: bool | None = None

    @model_validator(mode="after")
    def status_updates_require_expected_version(self) -> "ProjectTaskUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status must not be null")
        if self.status is not None and self.expected_status_version is None:
            raise ValueError("expected_status_version is required when status is supplied")
        return self


class ProjectTask(ProjectBaseModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    status: TaskStatus
    completed_at: str | None = None
    status_version: int = 0
    priority: TaskPriority = "medium"
    due_date: str | None = None
    milestone_id: str | None = None
    counts_toward_progress: bool = True
    source_provider: str | None = None
    source_key: str | None = None
    created_at: str
    updated_at: str


TaskStatusHistorySource = Literal["user", "milestone_validation", "system"]


class ProjectTaskStatusHistoryItem(ProjectBaseModel):
    id: str
    previous_status: TaskStatus | None = None
    status: TaskStatus
    actor_owner_id: str | None = None
    source: TaskStatusHistorySource
    reason: str | None = None
    changed_at: str
    status_version: int


class ProjectTaskStatusHistory(ProjectBaseModel):
    items: list[ProjectTaskStatusHistoryItem] = Field(default_factory=list)
    total: int = 0


class RepositorySourceCreate(BaseModel):
    repository_id: int = Field(..., gt=0)
    full_name: str = Field(..., min_length=3, max_length=255, pattern=r"^[^/\s]+/[^/\s]+$")
    default_branch: str = Field(default="main", min_length=1, max_length=255)


class RepositorySource(BaseModel):
    id: str
    project_id: str
    repository_id: int
    full_name: str
    default_branch: str
    updated_at: str


class GitHubCommit(BaseModel):
    id: str
    sha: str
    message: str
    author_name: str
    committed_at: str | None = None
    url: str


class BranchActivityPoint(BaseModel):
    date: str
    commits: int = 0


class GitHubBranchCommitNode(BaseModel):
    sha: str
    parents: list[str] = Field(default_factory=list)
    message: str = ""
    committed_at: str | None = None
    url: str = ""


class GitHubBranchActivity(BaseModel):
    name: str
    is_default: bool = False
    ahead_by: int = 0
    behind_by: int = 0
    status: str = "unknown"
    latest_commit_at: str | None = None
    activity: list[BranchActivityPoint] = Field(default_factory=list)
    head_sha: str | None = None
    commits: list[GitHubBranchCommitNode] = Field(default_factory=list)
    history_truncated: bool = False
    branch_list_truncated: bool = False


class GitHubDelivery(BaseModel):
    id: str
    delivery_id: str
    event_name: str
    ref: str
    status: Literal["processed", "ignored", "failed"]
    reason: str
    processing_attempts: int
    received_at: str
    last_processed_at: str


class ProjectGitHubStatus(BaseModel):
    repository: RepositorySource | None = None
    stored_commit_count: int = 0
    last_success_at: str | None = None
    deliveries: list[GitHubDelivery] = Field(default_factory=list)
