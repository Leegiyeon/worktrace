from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class MilestoneWorkItem(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    url: str = ""
    source_provider: str = ""
    source_key: str = ""
    is_validation_task: bool = False


class MilestoneEvidenceItem(BaseModel):
    kind: Literal["commit", "pull_request"]
    id: str
    title: str
    url: str
    occurred_at: str | None = None
    status: str = "evidence"


class MilestoneValidationUpdate(BaseModel):
    status: Literal["done", "planned"]
    expected_version: int = Field(ge=0)
    expected_context_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    evidence_note: str = Field(default="", max_length=8000)

    @field_validator("reason", "evidence_note")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_confirmation_context(self):
        if not self.reason or (self.status == "done" and not self.evidence_note):
            raise ValueError("A reason and evidence note for completion are required")
        return self


class MilestoneConfirmationRecord(BaseModel):
    id: str
    status: Literal["done", "planned"]
    version: int
    actor_owner_id: str
    reason: str
    evidence_note: str
    confirmed_at: str
    context_fingerprint: str


class MilestoneCompletion(BaseModel):
    status: Literal["done", "planned"] = "planned"
    version: int = 0
    context_fingerprint: str
    is_stale: bool = False
    can_confirm: bool
    block_reasons: list[str] = Field(default_factory=list)
    history: list[MilestoneConfirmationRecord] = Field(default_factory=list)


class MilestoneEvidenceSummary(BaseModel):
    milestone_id: str
    acceptance_criteria: str = ""
    total_wbs: int = 0
    completed_wbs: int = 0
    pending_wbs: list[MilestoneWorkItem] = Field(default_factory=list)
    validation_wbs: MilestoneWorkItem | None = None
    evidence_count: int = 0
    recent_evidence: list[MilestoneEvidenceItem] = Field(default_factory=list)
    completion: MilestoneCompletion | None = None
