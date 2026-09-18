from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from app.schemas.projects import ProjectSummary
from app.schemas.reports import (
    AutoReportResponse,
    MonthlyPerformanceCandidate,
    ProjectProgressCandidate,
    ProjectWeeklyReport,
    ReportType,
    TaskAlert,
    WorkLogItem,
)
from app.services.weekly_report import (
    DONE_STATUSES,
    WeeklyReportDataset,
    _work_log_to_schema,
    build_weekly_report_response,
)

REPORT_TITLES = {
    "daily": "일일 업무 요약",
    "weekly": "주간 업무 리포트",
    "monthly": "월간 성과 후보 리포트",
}


def build_auto_report_response(
    dataset: WeeklyReportDataset,
    report_type: ReportType,
    start_date: date,
    end_date: date,
    project_summaries: list[ProjectSummary] | None = None,
    progress_as_of: str | None = None,
) -> AutoReportResponse:
    as_of = progress_as_of or _utc_as_of()
    weekly = build_weekly_report_response(dataset, start_date, end_date)
    work_logs = [_work_log_to_schema(work_log) for work_log in dataset.work_logs]
    remaining_tasks, delayed_tasks = _task_alerts(weekly.projects, end_date)
    progress_candidates = _progress_candidates(weekly.projects, project_summaries, as_of)
    performance_candidates = _monthly_performance_candidates(weekly.projects, work_logs) if report_type == "monthly" else []
    markdown = _render_auto_markdown(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        work_logs=work_logs,
        projects=weekly.projects,
        remaining_tasks=remaining_tasks,
        delayed_tasks=delayed_tasks,
        progress_candidates=progress_candidates,
        performance_candidates=performance_candidates,
        progress_as_of=as_of,
    )
    return AutoReportResponse(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        markdown=markdown,
        work_logs=work_logs,
        projects=weekly.projects,
        remaining_tasks=remaining_tasks,
        delayed_tasks=delayed_tasks,
        progress_candidates=progress_candidates,
        monthly_performance_candidates=performance_candidates,
    )


def _task_alerts(projects: list[ProjectWeeklyReport], end_date: date) -> tuple[list[TaskAlert], list[TaskAlert]]:
    remaining: list[TaskAlert] = []
    delayed: list[TaskAlert] = []
    for project in projects:
        for task in project.tasks:
            if task.status.lower() in DONE_STATUSES:
                continue
            due_date = date.fromisoformat(task.due_date) if task.due_date else None
            is_delayed = bool(due_date and due_date < end_date)
            alert = TaskAlert(
                project_id=project.id,
                project_title=project.title,
                title=task.title,
                status=task.status,
                due_date=task.due_date,
                is_delayed=is_delayed,
            )
            remaining.append(alert)
            if is_delayed:
                delayed.append(alert)
    return remaining, delayed


def _progress_candidates(
    projects: list[ProjectWeeklyReport],
    project_summaries: list[ProjectSummary] | None,
    as_of: str,
) -> list[ProjectProgressCandidate]:
    summaries_by_project = {summary.id: summary for summary in project_summaries or []}
    candidates: list[ProjectProgressCandidate] = []
    for project in projects:
        summary = summaries_by_project.get(project.id)
        if summary is None:
            reason = "현재 프로젝트 WBS 요약 기준을 확인하지 못했습니다."
            candidate = ProjectProgressCandidate(
                project_id=project.id,
                project_title=project.title,
                current_status=project.status,
                progress_basis="unknown",
                provenance="기준 미확인",
                as_of=as_of,
                reason=reason,
            )
            candidates.append(candidate)
            continue

        progress_percent = None if summary.progress_basis == "unscoped" else summary.progress_percent
        provenance = _progress_provenance(summary)
        reason = _progress_reason(summary, provenance)
        candidates.append(
            ProjectProgressCandidate(
                project_id=project.id,
                project_title=project.title,
                current_status=summary.status,
                total_tasks=summary.total_tasks,
                completed_tasks=summary.completed_tasks,
                derived_task_count=summary.derived_task_count,
                progress_basis=summary.progress_basis,
                progress_percent=progress_percent,
                suggested_progress_percent=progress_percent,
                provenance=provenance,
                as_of=as_of,
                reason=reason,
            )
        )
    return candidates


def _utc_as_of() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _progress_provenance(summary: ProjectSummary) -> str:
    if summary.progress_basis == "unscoped":
        return "산정 전"
    label = f"{summary.progress_percent}%"
    return f"참고 {label}" if summary.derived_task_count > 0 else label


def _progress_reason(summary: ProjectSummary, provenance: str) -> str:
    if summary.progress_basis == "unscoped":
        return "산정 대상 WBS가 없어 현재 WBS 진척은 산정 전입니다."
    basis = "마일스톤 가중 WBS" if summary.progress_basis == "milestone" else "등록 WBS 완료 비율"
    derived = f" · 자동 구성 WBS {summary.derived_task_count}개 포함" if summary.derived_task_count > 0 else ""
    return (
        f"{basis}: 완료 {summary.completed_tasks}/{summary.total_tasks}개 기준의 현재 WBS 진척입니다"
        f" ({provenance}{derived})."
    )


def _monthly_performance_candidates(
    projects: list[ProjectWeeklyReport],
    work_logs: list[WorkLogItem],
) -> list[MonthlyPerformanceCandidate]:
    logs_by_project: dict[str, list[WorkLogItem]] = defaultdict(list)
    for work_log in work_logs:
        if work_log.project_id:
            logs_by_project[work_log.project_id].append(work_log)

    candidates: list[MonthlyPerformanceCandidate] = []
    for project in projects:
        evidence = []
        evidence.extend([f"문서: {document.filename}" for document in project.documents[:3]])
        evidence.extend([f"결정사항: {decision.title}" for decision in project.decisions[:3]])
        evidence.extend([f"업무 로그: {work_log.title}" for work_log in logs_by_project[project.id][:3]])
        if not evidence:
            continue
        qualitative = f"{project.title}: 저장된 업무 기록을 기반으로 개선 활동을 정리할 수 있습니다."
        candidates.append(
            MonthlyPerformanceCandidate(
                project_id=project.id,
                project_title=project.title,
                qualitative_improvement=qualitative,
                evidence=evidence,
                requires_user_metric_confirmation=True,
                resume_ready=False,
            )
        )
    return candidates


def _render_auto_markdown(
    report_type: ReportType,
    start_date: date,
    end_date: date,
    work_logs: list[WorkLogItem],
    projects: list[ProjectWeeklyReport],
    remaining_tasks: list[TaskAlert],
    delayed_tasks: list[TaskAlert],
    progress_candidates: list[ProjectProgressCandidate],
    performance_candidates: list[MonthlyPerformanceCandidate],
    progress_as_of: str,
) -> str:
    lines = [f"# {REPORT_TITLES[report_type]} ({start_date.isoformat()} ~ {end_date.isoformat()})", ""]
    lines.extend(_render_work_logs(work_logs))
    lines.extend(["", "## 프로젝트별 자동 요약"])
    if projects:
        for project in projects:
            lines.extend(
                [
                    f"### {project.title}",
                    f"- 상태: {project.status}",
                    f"- 문서 {len(project.documents)}건 / 할 일 {len(project.tasks)}건 / 결정사항 {len(project.decisions)}건 / 리스크 {len(project.risks)}건",
                    "- 기록 후보: 저장된 업무·문서 근거를 사용해 후속 성과 정리에 활용할 수 있습니다.",
                    "",
                ]
            )
    else:
        lines.append("- 선택 기간에 연결된 프로젝트 기록이 없습니다.")

    lines.extend(["", "## 현재 WBS 진척", f"- 기준 시각: {progress_as_of}"])
    if progress_candidates:
        for candidate in progress_candidates:
            lines.append(f"- {candidate.project_title}: {candidate.provenance} / {candidate.reason}")
    else:
        lines.append("- 현재 WBS 진척을 표시할 프로젝트 기록이 없습니다.")

    lines.extend(["", "## 기간 내 문서 추출 잔여 항목"])
    lines.append("- 기간 내 문서에서 추출한 항목 기준이며, 전체 WBS 잔여량과 다릅니다.")
    lines.extend(_render_task_alerts(remaining_tasks, empty="잔여 업무가 없습니다."))
    lines.extend(["", "## 기간 내 문서 추출 지연 항목"])
    lines.extend(_render_task_alerts(delayed_tasks, empty="지연 업무가 없습니다."))

    if report_type == "monthly":
        lines.extend(["", "## 월간 성과 후보"])
        if performance_candidates:
            for candidate in performance_candidates:
                lines.append(f"- {candidate.project_title}: {candidate.qualitative_improvement}")
                lines.append("  - 수치 확정: 사용자 확인 필요")
                lines.append(f"  - 이력서 반영 가능: {'가능' if candidate.resume_ready else '근거/수치 보강 필요'}")
                for evidence in candidate.evidence:
                    lines.append(f"  - 근거: {evidence}")
        else:
            lines.append("- 성과 후보를 만들 저장 근거가 없습니다.")

    lines.extend(["", "_메일 발송과 외부 서비스 연동 없이 앱 내부 저장 데이터만 사용했습니다._"])
    return "\n".join(lines).strip() + "\n"


def _render_work_logs(work_logs: list[WorkLogItem]) -> list[str]:
    lines = ["## 업무 로그 기반 일일 요약"]
    if not work_logs:
        lines.append("- 선택 기간에 등록된 업무 로그가 없습니다.")
        return lines
    for work_log in work_logs:
        project_label = f" ({work_log.project_title})" if work_log.project_title else ""
        duration = f" · {work_log.duration_minutes}분" if work_log.duration_minutes else ""
        lines.append(f"- {work_log.log_date.isoformat()} · {work_log.title}{project_label}{duration}: {work_log.content or '내용 없음'}")
        if work_log.decisions:
            lines.append(f"  - 판단/결정: {work_log.decisions}")
        if work_log.collaborators:
            lines.append(f"  - 협의 대상: {work_log.collaborators}")
        if work_log.next_actions:
            lines.append(f"  - 다음 액션: {work_log.next_actions}")
        if work_log.blockers:
            lines.append(f"  - 이슈/막힘: {work_log.blockers}")
    return lines


def _render_task_alerts(alerts: list[TaskAlert], *, empty: str) -> list[str]:
    if not alerts:
        return [f"- {empty}"]
    lines = []
    for alert in alerts:
        due = f" / 기한: {alert.due_date}" if alert.due_date else ""
        delayed = " / 지연" if alert.is_delayed else ""
        lines.append(f"- {alert.project_title}: [{alert.status}] {alert.title}{due}{delayed}")
    return lines
