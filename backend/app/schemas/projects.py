from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProjectStatus = Literal["idea", "review", "in_progress", "on_hold", "done"]
TaskStatus = Literal["planned", "in_progress", "done", "on_hold"]
TaskPriority = Literal["low", "medium", "high"]


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
    status: ProjectStatus = "idea"
    role: str = ""


class ProjectUpdate(ProjectBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: ProjectStatus | None = None
    role: str | None = None


class ProjectSummary(ProjectBaseModel):
    id: str
    title: str
    description: str = ""
    status: ProjectStatus
    role: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    remaining_tasks: int = 0
    progress_percent: int = 0
    updated_at: str


class ProjectTaskCreate(ProjectBaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    status: TaskStatus = "planned"
    priority: TaskPriority = "medium"
    due_date: date | None = None


class ProjectTaskUpdate(ProjectBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None


class ProjectTask(ProjectBaseModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    status: TaskStatus
    priority: TaskPriority = "medium"
    due_date: str | None = None
    created_at: str
    updated_at: str


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
