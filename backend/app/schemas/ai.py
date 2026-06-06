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


AiErrorCode = Literal["AI_CONFIG_MISSING", "AI_DRAFT_FAILED", "PROJECT_NOT_FOUND"]
