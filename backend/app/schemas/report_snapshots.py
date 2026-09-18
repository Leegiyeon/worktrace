from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.reports import AutoReportRequest, AutoReportResponse, ReportType


class ReportSnapshotCreate(AutoReportRequest):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class ReportSnapshotSummary(AutoReportRequest):
    model_config = ConfigDict(extra="forbid")

    id: str
    request_id: str
    as_of: str
    created_at: str
    fingerprint: str
    schema_version: Literal["1"] = "1"


class ReportSnapshotDetail(ReportSnapshotSummary):
    report: AutoReportResponse


class ReportSnapshotPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReportSnapshotSummary] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


__all__ = [
    "ReportSnapshotCreate",
    "ReportSnapshotDetail",
    "ReportSnapshotPage",
    "ReportSnapshotSummary",
    "ReportType",
]
