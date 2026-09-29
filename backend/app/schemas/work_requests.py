from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID
    title: str = Field(min_length=1, max_length=180)
    body: str = Field(default="", max_length=10000)
    desired_outcome: str = Field(default="", max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    source: Literal["chat", "manual"] = "manual"

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class WorkRequest(WorkRequestCreate):
    id: str
    project_id: str
    created_at: str


class WorkRequestPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WorkRequest] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
