from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.schemas.projects import ProjectSummary
from app.schemas.report_activity import (
    CurrentReportTask,
    ReportActivity,
    ReportIssue,
    ReportOutcome,
    TaskTransition,
)
from app.services.weekly_report import _report_timezone


def fetch_report_activity(
    connection: Any,
    settings: Settings,
    owner_id: str,
    start_date: date,
    end_date: date,
    as_of: str,
    project_summaries: list[ProjectSummary],
) -> ReportActivity:
    report_timezone = _report_timezone(settings.report_timezone)
    start_local = datetime.combine(start_date, time.min, tzinfo=report_timezone)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=report_timezone)
    start_at = start_local.astimezone(timezone.utc)
    end_exclusive = end_local.astimezone(timezone.utc)
    summary_by_project = {summary.id: summary for summary in project_summaries}

    transitions = [
        _transition_from_row(row)
        for row in connection.execute(
            """
            SELECT h.id::text,
                   h.project_id::text,
                   p.title AS project_title,
                   h.task_id::text,
                   t.title AS task_title,
                   t.status AS current_status,
                   h.previous_status,
                   h.next_status,
                   h.source,
                   h.reason,
                   h.changed_at::text,
                   h.status_version::bigint
            FROM project_task_status_history h
            JOIN projects p
              ON p.owner_id = h.owner_id
             AND p.id = h.project_id
            JOIN project_tasks t
              ON t.owner_id = h.owner_id
             AND t.project_id = h.project_id
             AND t.id = h.task_id
            WHERE h.owner_id = %(owner_id)s
              AND h.changed_at >= %(start_at)s
              AND h.changed_at < %(end_exclusive)s
              AND NOT (
                  COALESCE(t.source_provider, '') = 'derived-github'
                  AND COALESCE(t.source_key, '') LIKE 'milestone-validation:%%'
              )
            ORDER BY h.changed_at ASC, h.status_version ASC, h.id ASC
            """,
            {"owner_id": owner_id, "start_at": start_at, "end_exclusive": end_exclusive},
        ).fetchall()
    ]

    current_tasks = [
        _current_task_from_row(row, summary_by_project)
        for row in connection.execute(
            """
            SELECT t.id::text,
                   t.project_id::text,
                   p.title AS project_title,
                   t.title,
                   t.status,
                   t.due_date::text,
                   t.source_provider
            FROM project_tasks t
            JOIN projects p
              ON p.owner_id = t.owner_id
             AND p.id = t.project_id
            WHERE t.owner_id = %(owner_id)s
              AND t.status <> 'done'
              AND t.counts_toward_progress
              AND NOT (
                  COALESCE(t.source_provider, '') = 'derived-github'
                  AND COALESCE(t.source_key, '') LIKE 'milestone-validation:%%'
              )
            ORDER BY p.title ASC, t.due_date ASC NULLS LAST, t.updated_at DESC, t.title ASC, t.id ASC
            """,
            {"owner_id": owner_id},
        ).fetchall()
    ]

    issues = [
        _issue_from_row(row)
        for row in connection.execute(
            """
            SELECT wl.id::text,
                   p.id::text AS project_id,
                   COALESCE(p.title, '') AS project_title,
                   wl.title,
                   btrim(wl.blockers) AS blockers,
                   wl.log_date::text,
                   wl.updated_at::text
            FROM work_logs wl
            LEFT JOIN projects p
              ON p.owner_id = wl.owner_id
             AND p.id = wl.project_id
            WHERE wl.owner_id = %(owner_id)s
              AND wl.log_date >= %(start_date)s
              AND wl.log_date <= %(end_date)s
              AND btrim(wl.blockers) <> ''
            ORDER BY wl.log_date ASC, wl.updated_at ASC, wl.id ASC
            """,
            {"owner_id": owner_id, "start_date": start_date, "end_date": end_date},
        ).fetchall()
    ]

    outcomes = [
        _outcome_from_row(row)
        for row in connection.execute(
            """
            SELECT o.id::text,
                   o.project_id::text,
                   p.title AS project_title,
                   o.title,
                   o.outcome_type,
                   o.before_state,
                   o.after_state,
                   o.metric_name,
                   o.metric_value::text,
                   o.metric_unit,
                   o.updated_at::text,
                   COALESCE(live_work_logs.ids, ARRAY[]::text[]) AS evidence_work_log_ids,
                   COALESCE(live_documents.ids, ARRAY[]::text[]) AS evidence_document_ids
            FROM project_outcomes o
            JOIN projects p
              ON p.owner_id = o.owner_id
             AND p.id = o.project_id
            LEFT JOIN LATERAL (
                SELECT array_agg(wl.id::text ORDER BY evidence.ordinality) AS ids
                FROM unnest(o.evidence_work_log_ids) WITH ORDINALITY AS evidence(id, ordinality)
                JOIN work_logs wl
                  ON wl.id = evidence.id
                 AND wl.owner_id = o.owner_id
                 AND wl.project_id = o.project_id
            ) live_work_logs ON true
            LEFT JOIN LATERAL (
                SELECT array_agg(d.id::text ORDER BY evidence.ordinality) AS ids
                FROM unnest(o.evidence_document_ids) WITH ORDINALITY AS evidence(id, ordinality)
                JOIN documents d
                  ON d.id = evidence.id
                 AND d.owner_id = o.owner_id
                 AND d.project_id = o.project_id
            ) live_documents ON true
            WHERE o.owner_id = %(owner_id)s
              AND o.resume_ready IS TRUE
              AND o.updated_at >= %(start_at)s
              AND o.updated_at < %(end_exclusive)s
            ORDER BY o.updated_at ASC, o.title ASC, o.id ASC
            """,
            {"owner_id": owner_id, "start_at": start_at, "end_exclusive": end_exclusive},
        ).fetchall()
    ]

    return ReportActivity(
        as_of=as_of,
        timezone=settings.report_timezone,
        start_at=start_local.isoformat(),
        end_exclusive=end_local.isoformat(),
        transitions=transitions,
        current_tasks=current_tasks,
        issues=issues,
        outcomes=outcomes,
    )


def _transition_from_row(row: dict[str, Any]) -> TaskTransition:
    return TaskTransition(
        id=row["id"],
        project_id=row["project_id"],
        project_title=row["project_title"],
        task_id=row["task_id"],
        task_title=row["task_title"],
        current_status=row["current_status"],
        previous_status=row.get("previous_status"),
        next_status=row["next_status"],
        source=row["source"],
        reason=row.get("reason"),
        changed_at=row["changed_at"],
        status_version=int(row["status_version"]),
    )


def _current_task_from_row(row: dict[str, Any], summary_by_project: dict[str, ProjectSummary]) -> CurrentReportTask:
    summary = summary_by_project.get(row["project_id"])
    return CurrentReportTask(
        id=row["id"],
        project_id=row["project_id"],
        project_title=row["project_title"],
        title=row["title"],
        status=row["status"],
        due_date=row.get("due_date"),
        source_provider=row.get("source_provider"),
        progress_plan_status=summary.progress_plan_status if summary else "unapproved",
        progress_plan_version=summary.progress_plan_version if summary else 0,
    )


def _issue_from_row(row: dict[str, Any]) -> ReportIssue:
    return ReportIssue(
        id=row["id"],
        project_id=row.get("project_id"),
        project_title=row.get("project_title") or "",
        title=row["title"],
        blockers=row["blockers"],
        log_date=row["log_date"],
        updated_at=row["updated_at"],
    )


def _outcome_from_row(row: dict[str, Any]) -> ReportOutcome:
    return ReportOutcome(
        id=row["id"],
        project_id=row["project_id"],
        project_title=row["project_title"],
        title=row["title"],
        outcome_type=row["outcome_type"],
        before_state=row.get("before_state") or "",
        after_state=row.get("after_state") or "",
        metric_name=row.get("metric_name") or "",
        metric_value=row.get("metric_value"),
        metric_unit=row.get("metric_unit") or "",
        updated_at=row["updated_at"],
        evidence_work_log_ids=[str(value) for value in row.get("evidence_work_log_ids") or []],
        evidence_document_ids=[str(value) for value in row.get("evidence_document_ids") or []],
    )
