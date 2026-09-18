from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, cast, get_args
from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.reports import (
    DocumentReportItem,
    ExtractedReportItem,
    ItemType,
    ProjectStatus,
    ProjectWeeklyReport,
    WeeklyReportResponse,
    WorkLogItem,
)

STATUS_LABELS = {
    "idea": "아이디어",
    "review": "검토",
    "in_progress": "진행",
    "on_hold": "보류",
    "done": "완료",
}

DONE_STATUSES = {"done", "completed", "closed", "완료"}

PROJECT_STATUSES = set(get_args(ProjectStatus))
ITEM_TYPES = set(get_args(ItemType))


class ReportConfigurationError(ValueError):
    """Raised when report configuration would produce misleading output."""


class ReportDataContractError(ValueError):
    """Raised when stored report data violates the expected schema contract."""


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    title: str
    description: str
    status: str
    role: str
    updated_at: str


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    project_id: str
    filename: str
    summary: str
    document_type: str
    analysis_status: str
    updated_at: str


@dataclass(frozen=True)
class ExtractedRecord:
    id: str
    project_id: str
    item_type: str
    title: str
    content: str
    status: str
    due_date: str | None
    updated_at: str


@dataclass(frozen=True)
class WorkLogRecord:
    id: str
    log_date: date
    work_type: str
    title: str
    content: str
    decisions: str
    collaborators: str
    next_actions: str
    duration_minutes: int
    blockers: str
    project_id: str | None
    project_title: str
    updated_at: str


@dataclass
class WeeklyReportDataset:
    projects: list[ProjectRecord] = field(default_factory=list)
    documents: list[DocumentRecord] = field(default_factory=list)
    extracted_items: list[ExtractedRecord] = field(default_factory=list)
    work_logs: list[WorkLogRecord] = field(default_factory=list)


def fetch_weekly_report_dataset(settings: Settings, start_date: date, end_date: date, owner_id: str, *, connection=None) -> WeeklyReportDataset:
    """Fetch projects and period activity that can support a grounded weekly report."""

    report_timezone = _report_timezone(settings.report_timezone)

    start_at = datetime.combine(start_date, time.min, tzinfo=report_timezone).astimezone(timezone.utc)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=report_timezone).astimezone(timezone.utc)

    with (nullcontext(connection) if connection is not None else connect(settings)) as connection:
        project_rows = connection.execute(
            """
            WITH active_project_ids AS (
                SELECT id AS project_id FROM projects
                WHERE owner_id = %(owner_id)s
                  AND updated_at >= %(start_at)s AND updated_at < %(end_exclusive)s
                UNION
                SELECT project_id FROM documents
                WHERE owner_id = %(owner_id)s
                  AND updated_at >= %(start_at)s AND updated_at < %(end_exclusive)s
                UNION
                SELECT project_id FROM extracted_items
                WHERE owner_id = %(owner_id)s
                  AND updated_at >= %(start_at)s AND updated_at < %(end_exclusive)s
                UNION
                SELECT project_id FROM work_logs
                WHERE owner_id = %(owner_id)s
                  AND project_id IS NOT NULL
                  AND log_date >= %(start_date)s AND log_date <= %(end_date)s
            )
            SELECT p.id::text, p.title, p.description, p.status, p.role, p.updated_at::text
            FROM projects p
            JOIN active_project_ids active ON active.project_id = p.id
            WHERE p.owner_id = %(owner_id)s
            ORDER BY p.updated_at DESC, p.title ASC, p.id ASC
            """,
            {"start_at": start_at, "end_exclusive": end_exclusive, "start_date": start_date, "end_date": end_date, "owner_id": owner_id},
        ).fetchall()

        work_logs = connection.execute(
            """
            SELECT wl.id::text, wl.log_date, wl.work_type, wl.title, wl.content, wl.decisions,
                   wl.collaborators, wl.next_actions, wl.duration_minutes, wl.blockers,
                   p.id::text AS project_id, COALESCE(p.title, '') AS project_title, wl.updated_at::text
            FROM work_logs wl
            LEFT JOIN projects p ON p.id = wl.project_id AND p.owner_id = %(owner_id)s
            WHERE wl.owner_id = %(owner_id)s
              AND wl.log_date >= %(start_date)s AND wl.log_date <= %(end_date)s
            ORDER BY wl.log_date DESC, wl.updated_at DESC, wl.id ASC
            """,
            {"start_date": start_date, "end_date": end_date, "owner_id": owner_id},
        ).fetchall()

        if not project_rows:
            return WeeklyReportDataset(work_logs=[_work_log_from_row(row) for row in work_logs])

        project_ids = [UUID(row["id"]) for row in project_rows]
        documents = connection.execute(
            """
            SELECT id::text, project_id::text, filename, summary, document_type,
                   analysis_status, updated_at::text
            FROM documents
            WHERE project_id = ANY(%(project_ids)s::uuid[])
              AND owner_id = %(owner_id)s
              AND updated_at >= %(start_at)s
              AND updated_at < %(end_exclusive)s
            ORDER BY updated_at DESC, filename ASC, id ASC
            """,
            {"project_ids": project_ids, "start_at": start_at, "end_exclusive": end_exclusive, "owner_id": owner_id},
        ).fetchall()

        extracted_items = connection.execute(
            """
            SELECT id::text, project_id::text, item_type, title, content, status,
                   due_date::text, updated_at::text
            FROM extracted_items
            WHERE project_id = ANY(%(project_ids)s::uuid[])
              AND owner_id = %(owner_id)s
              AND updated_at >= %(start_at)s
              AND updated_at < %(end_exclusive)s
            ORDER BY updated_at DESC, item_type ASC, title ASC, id ASC
            """,
            {"project_ids": project_ids, "start_at": start_at, "end_exclusive": end_exclusive, "owner_id": owner_id},
        ).fetchall()

    return WeeklyReportDataset(
        projects=[_project_from_row(row) for row in project_rows],
        documents=[_document_from_row(row) for row in documents],
        extracted_items=[_extracted_from_row(row) for row in extracted_items],
        work_logs=[_work_log_from_row(row) for row in work_logs],
    )


def build_weekly_report_response(dataset: WeeklyReportDataset, start_date: date, end_date: date) -> WeeklyReportResponse:
    documents_by_project: dict[str, list[DocumentRecord]] = defaultdict(list)
    items_by_project: dict[str, list[ExtractedRecord]] = defaultdict(list)

    for document in dataset.documents:
        documents_by_project[document.project_id].append(document)
    for item in dataset.extracted_items:
        items_by_project[item.project_id].append(item)

    project_reports = [
        _build_project_report(
            project=project,
            documents=documents_by_project.get(project.id, []),
            items=items_by_project.get(project.id, []),
        )
        for project in dataset.projects
    ]

    markdown = build_weekly_report_markdown(start_date=start_date, end_date=end_date, projects=project_reports)
    return WeeklyReportResponse(start_date=start_date, end_date=end_date, markdown=markdown, projects=project_reports)


def build_weekly_report_markdown(start_date: date, end_date: date, projects: list[ProjectWeeklyReport]) -> str:
    lines = [
        f"# 주간 업무 리포트 ({start_date.isoformat()} ~ {end_date.isoformat()})",
        "",
        "## 전체 요약",
    ]

    if not projects:
        lines.extend(
            [
                "- 해당 기간에 업데이트된 프로젝트 기록이 없습니다.",
                "- 다음 주 확인 필요 사항도 저장된 근거가 없어 생성하지 않았습니다.",
                "",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    total_documents = sum(len(project.documents) for project in projects)
    total_tasks = sum(len(project.tasks) for project in projects)
    total_decisions = sum(len(project.decisions) for project in projects)
    total_risks = sum(len(project.risks) for project in projects)

    lines.extend(
        [
            f"- 업데이트된 프로젝트: {len(projects)}개",
            f"- 관련 문서: {total_documents}개",
            f"- 할 일: {total_tasks}개 / 결정사항: {total_decisions}개 / 리스크: {total_risks}개",
            "- 아래 내용은 저장된 프로젝트·문서·추출 항목만 기반으로 작성했습니다.",
            "",
            "## 프로젝트별 진행 현황",
        ]
    )

    for project in projects:
        lines.extend(_render_project(project))

    next_checks = [check for project in projects for check in project.next_checks]
    lines.extend(["", "## 다음 주 확인 필요 사항"])
    if next_checks:
        lines.extend([f"- {check}" for check in next_checks])
    else:
        lines.append("- 저장된 미완료 할 일 또는 열린 리스크가 없습니다.")

    return "\n".join(lines).strip() + "\n"


def _build_project_report(
    project: ProjectRecord,
    documents: list[DocumentRecord],
    items: list[ExtractedRecord],
) -> ProjectWeeklyReport:
    tasks = [_item_to_schema(item) for item in items if item.item_type == "task"]
    decisions = [_item_to_schema(item) for item in items if item.item_type == "decision"]
    risks = [_item_to_schema(item) for item in items if item.item_type == "risk"]
    explicit_next_checks = [item for item in items if item.item_type == "next_check"]

    next_checks = _derive_next_checks(project, tasks, risks, explicit_next_checks)

    return ProjectWeeklyReport(
        id=project.id,
        title=project.title,
        description=project.description,
        status=cast(ProjectStatus, project.status),
        role=project.role,
        updated_at=project.updated_at,
        documents=[_document_to_schema(document) for document in documents],
        tasks=tasks,
        decisions=decisions,
        risks=risks,
        next_checks=next_checks,
    )


def _derive_next_checks(
    project: ProjectRecord,
    tasks: list[ExtractedReportItem],
    risks: list[ExtractedReportItem],
    explicit_next_checks: list[ExtractedRecord],
) -> list[str]:
    checks = [f"{project.title}: {item.title}" for item in explicit_next_checks]

    for task in tasks:
        if task.status.lower() not in DONE_STATUSES:
            due = f" (기한: {task.due_date})" if task.due_date else ""
            checks.append(f"{project.title}: 미완료 할 일 확인 — {task.title}{due}")

    for risk in risks:
        if risk.status.lower() not in DONE_STATUSES:
            checks.append(f"{project.title}: 열린 리스크 대응 확인 — {risk.title}")

    return checks[:8]


def _render_project(project: ProjectWeeklyReport) -> list[str]:
    status_label = STATUS_LABELS.get(project.status, project.status)
    lines = [
        "",
        f"### {project.title}",
        f"- 상태: {status_label}",
        f"- 최근 업데이트: {project.updated_at}",
    ]
    if project.role:
        lines.append(f"- 내 역할: {project.role}")
    if project.description:
        lines.append(f"- 개요: {project.description}")

    lines.extend(["", "#### 관련 문서"])
    lines.extend(_render_documents(project.documents))
    lines.extend(["", "#### 할 일"])
    lines.extend(_render_items(project.tasks, empty="저장된 할 일이 없습니다."))
    lines.extend(["", "#### 결정사항"])
    lines.extend(_render_items(project.decisions, empty="저장된 결정사항이 없습니다."))
    lines.extend(["", "#### 리스크"])
    lines.extend(_render_items(project.risks, empty="저장된 리스크가 없습니다."))
    return lines


def _render_documents(documents: list[DocumentReportItem]) -> list[str]:
    if not documents:
        return ["- 해당 기간에 업데이트된 문서가 없습니다."]

    rendered = []
    for document in documents:
        type_label = f" · {document.document_type}" if document.document_type else ""
        summary = f" — {document.summary}" if document.summary else ""
        rendered.append(f"- {document.filename}{type_label} ({document.analysis_status}){summary}")
    return rendered


def _render_items(items: list[ExtractedReportItem], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    rendered = []
    for item in items:
        due = f" / 기한: {item.due_date}" if item.due_date else ""
        content = f" — {item.content}" if item.content else ""
        rendered.append(f"- [{item.status}] {item.title}{due}{content}")
    return rendered


def _report_timezone(value: str):
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ReportConfigurationError(f"Invalid REPORT_TIMEZONE: {value}") from exc


def _project_status(value: Any) -> str:
    if isinstance(value, str) and value in PROJECT_STATUSES:
        return value
    raise ReportDataContractError(f"Invalid project status: {value!r}")


def _item_type(value: Any) -> str:
    if isinstance(value, str) and value in ITEM_TYPES:
        return value
    raise ReportDataContractError(f"Invalid extracted item type: {value!r}")


def _project_from_row(row: dict[str, Any]) -> ProjectRecord:
    return ProjectRecord(
        id=row["id"],
        title=row["title"],
        description=row.get("description") or "",
        status=_project_status(row.get("status")),
        role=row.get("role") or "",
        updated_at=row["updated_at"],
    )


def _document_from_row(row: dict[str, Any]) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        project_id=row["project_id"],
        filename=row["filename"],
        summary=row.get("summary") or "",
        document_type=row.get("document_type") or "",
        analysis_status=row.get("analysis_status") or "pending",
        updated_at=row["updated_at"],
    )


def _extracted_from_row(row: dict[str, Any]) -> ExtractedRecord:
    return ExtractedRecord(
        id=row["id"],
        project_id=row["project_id"],
        item_type=_item_type(row.get("item_type")),
        title=row["title"],
        content=row.get("content") or "",
        status=row.get("status") or "open",
        due_date=row.get("due_date"),
        updated_at=row["updated_at"],
    )


def _work_log_from_row(row: dict[str, Any]) -> WorkLogRecord:
    return WorkLogRecord(
        id=row["id"],
        log_date=row["log_date"],
        work_type=row.get("work_type") or "other",
        title=row["title"],
        content=row.get("content") or "",
        decisions=row.get("decisions") or "",
        collaborators=row.get("collaborators") or "",
        next_actions=row.get("next_actions") or "",
        duration_minutes=row.get("duration_minutes") or 0,
        blockers=row.get("blockers") or "",
        project_id=row.get("project_id"),
        project_title=row.get("project_title") or "",
        updated_at=row["updated_at"],
    )


def _work_log_to_schema(work_log: WorkLogRecord) -> WorkLogItem:
    return WorkLogItem(
        id=work_log.id,
        log_date=work_log.log_date,
        work_type=work_log.work_type,
        title=work_log.title,
        content=work_log.content,
        decisions=work_log.decisions,
        collaborators=work_log.collaborators,
        next_actions=work_log.next_actions,
        duration_minutes=work_log.duration_minutes,
        blockers=work_log.blockers,
        project_id=work_log.project_id,
        project_title=work_log.project_title,
        updated_at=work_log.updated_at,
    )


def _document_to_schema(document: DocumentRecord) -> DocumentReportItem:
    return DocumentReportItem(
        id=document.id,
        filename=document.filename,
        summary=document.summary,
        document_type=document.document_type,
        analysis_status=document.analysis_status,
        updated_at=document.updated_at,
    )


def _item_to_schema(item: ExtractedRecord) -> ExtractedReportItem:
    return ExtractedReportItem(
        id=item.id,
        item_type=cast(ItemType, item.item_type),
        title=item.title,
        content=item.content,
        status=item.status,
        due_date=item.due_date,
        updated_at=item.updated_at,
    )
