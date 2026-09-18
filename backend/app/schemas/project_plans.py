from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProjectPlanPolicy = Literal["wbs", "milestone"]
ProjectPlanStatus = Literal["unapproved", "approved", "stale"]


class ProjectPlanBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ProjectPlanTask(ProjectPlanBaseModel):
    id: str
    title: str
    description: str = ""
    milestone_id: str | None = None
    counts_toward_progress: bool = True
    source_provider: str | None = None
    source_key: str | None = None


class ProjectPlanMilestone(ProjectPlanBaseModel):
    id: str
    title: str
    weight: int


class ProjectPlanExcludedTask(ProjectPlanBaseModel):
    id: str
    title: str


class ProjectPlanApprovalHistoryItem(ProjectPlanBaseModel):
    id: str
    version: int
    policy: ProjectPlanPolicy
    reason: str
    exclusion_reason: str = ""
    reviewed_derived: bool = False
    approved_at: datetime
    actor_owner_id: str


class ProjectPlan(ProjectPlanBaseModel):
    version: int = 0
    status: ProjectPlanStatus
    policy: ProjectPlanPolicy = "wbs"
    context_fingerprint: str
    total_tasks: int = 0
    derived_task_count: int = 0
    tasks: list[ProjectPlanTask] = Field(default_factory=list)
    milestones: list[ProjectPlanMilestone] = Field(default_factory=list)
    excluded_tasks: list[ProjectPlanExcludedTask] = Field(default_factory=list)
    policy_errors: dict[ProjectPlanPolicy, list[str]]
    history: list[ProjectPlanApprovalHistoryItem] = Field(default_factory=list)


class ProjectPlanApprove(ProjectPlanBaseModel):
    policy: ProjectPlanPolicy
    reason: str = Field(..., min_length=1, max_length=2000)
    exclusion_reason: str = Field(default="", max_length=2000)
    reviewed_derived: bool = False
    expected_version: int = Field(..., ge=0)
    expected_context_fingerprint: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    request_id: UUID

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value
