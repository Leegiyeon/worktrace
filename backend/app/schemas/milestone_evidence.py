from typing import Literal

from pydantic import BaseModel, Field


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


class MilestoneEvidenceSummary(BaseModel):
    milestone_id: str
    acceptance_criteria: str = ""
    total_wbs: int = 0
    completed_wbs: int = 0
    pending_wbs: list[MilestoneWorkItem] = Field(default_factory=list)
    evidence_count: int = 0
    recent_evidence: list[MilestoneEvidenceItem] = Field(default_factory=list)
