from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


GitHubItemReviewStatus = Literal["pending", "adopted", "ignored"]
GitHubItemReviewFilter = Literal["pending", "adopted", "ignored", "all"]
GitHubItemKind = Literal["issue", "pr"]
GitHubItemDecisionAction = Literal["create", "link", "ignore", "restore"]


class GitHubItem(BaseModel):
    id: str
    number: int
    kind: GitHubItemKind
    title: str
    body: str
    body_truncated: bool = False
    url: str
    external_state: str
    source_updated_at: str
    collected_at: str
    review_status: GitHubItemReviewStatus
    version: int = 0
    task_id: str | None = None
    task_title: str | None = None
    reviewed_at: str | None = None
    source_changed: bool = False


class GitHubItemCounts(BaseModel):
    pending: int = 0
    adopted: int = 0
    ignored: int = 0


class GitHubItemListResponse(BaseModel):
    items: list[GitHubItem]
    total: int = 0
    counts: GitHubItemCounts = Field(default_factory=GitHubItemCounts)


class GitHubItemDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action: GitHubItemDecisionAction
    expected_version: int = Field(..., ge=0)
    expected_source_updated_at: datetime
    request_id: UUID
    title: str | None = Field(default=None, max_length=240)
    task_id: UUID | None = None
    counts_toward_progress: bool = True

    @field_validator("title")
    @classmethod
    def title_not_blank_when_present(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value
