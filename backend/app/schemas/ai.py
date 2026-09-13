from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.reports import WorkType


class WorkLogDraftRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, max_length=6000)
    project_id: UUID | None = None


class WorkLogDraftResponse(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    work_type: WorkType
    content: str
    decisions: str
    collaborators: str
    next_actions: str
    blockers: str
    duration_minutes: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)


MilestoneReviewVerdict = Literal["ready_candidate", "not_ready", "needs_review"]


class MilestoneReviewRequest(BaseModel):
    project_id: UUID
    milestone_id: UUID


class MilestoneReviewResponse(BaseModel):
    verdict: MilestoneReviewVerdict
    confidence: float = Field(..., ge=0, le=1)
    reasoning_summary: str = Field(..., min_length=1, max_length=1200)
    missing_checks: list[str] = Field(default_factory=list, max_length=12)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    reviewed_wbs_total: int = Field(default=0, ge=0)
    reviewed_wbs_completed: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)


class StoredMilestoneReview(MilestoneReviewResponse):
    milestone_id: UUID
    reviewed_at: datetime
    model: str = ""


class ProjectAnalystRequest(BaseModel):
    project_id: UUID


class ProjectAnalystAction(BaseModel):
    task_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)


class ProjectAnalystResponse(BaseModel):
    summary: str = Field(..., min_length=1, max_length=1200)
    next_actions: list[ProjectAnalystAction] = Field(default_factory=list, max_length=5)
    blockers: list[str] = Field(default_factory=list, max_length=8)
    needs_attention: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(..., ge=0, le=1)
    remaining_wbs_count: int = Field(default=0, ge=0)
    evidence_commit_count: int = Field(default=0, ge=0)


AiErrorCode = Literal[
    "AI_CONFIG_MISSING",
    "AI_DRAFT_FAILED",
    "AI_MILESTONE_REVIEW_FAILED",
    "AI_PROJECT_ANALYST_FAILED",
    "PROJECT_NOT_FOUND",
    "PROJECT_MILESTONE_NOT_FOUND",
]
