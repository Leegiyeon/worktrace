from typing import Literal

from pydantic import BaseModel


CareerTargetRole = Literal["IT기획", "PM", "AI서비스기획", "Backend", "DevOps"]


class CareerAssetGenerateRequest(BaseModel):
    target_role: CareerTargetRole = "PM"


class CareerAssetUpdateRequest(BaseModel):
    work_summary: str | None = None
    outcome_summary: str | None = None
    resume_bullets: str | None = None
    career_description: str | None = None
    portfolio_description: str | None = None
    star_answer: str | None = None
    markdown: str | None = None


class CareerAsset(BaseModel):
    id: str
    project_id: str
    source_summary: str = ""
    work_summary: str = ""
    outcome_summary: str = ""
    resume_bullets: str = ""
    career_description: str = ""
    portfolio_description: str = ""
    star_answer: str = ""
    markdown: str = ""
    generation_method: str = "template"
    created_at: str
    updated_at: str
