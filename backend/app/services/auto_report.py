from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.report_activity import ReportActivity
from app.schemas.projects import ProjectSummary
from app.schemas.reports import (
    AutoReportRequest,
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
    ProjectRecord,
    _work_log_to_schema,
    build_weekly_report_response,
    fetch_weekly_report_dataset,
)
from app.services.projects import list_projects
from app.services.report_activity import fetch_report_activity

REPORT_TITLES = {
    "daily": "일일 업무 요약",
    "weekly": "주간 업무 리포트",
    "monthly": "월간 성과 후보 리포트",
}


def generate_auto_report(settings: Settings, owner_id: str, request: AutoReportRequest) -> AutoReportResponse:
    # All source rows and current progress share the same PostgreSQL MVCC snapshot.
    with connect(settings) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        as_of = connection.execute("SELECT transaction_timestamp() AS as_of").fetchone()["as_of"].isoformat()
        dataset = fetch_weekly_report_dataset(settings, request.start_date, request.end_date, owner_id, connection=connection)
        summaries = list_projects(settings, owner_id, connection=connection)
        activity = fetch_report_activity(connection, settings, owner_id, request.start_date, request.end_date, as_of, summaries)
    included_ids = {project.id for project in dataset.projects}
    activity_ids = {row.project_id for rows in (activity.transitions, activity.current_tasks, activity.outcomes) for row in rows}
    for summary in summaries:
        if summary.id in activity_ids and summary.id not in included_ids:
            dataset.projects.append(ProjectRecord(summary.id, summary.title, summary.description, summary.status, summary.role, summary.updated_at))
    return build_auto_report_response(dataset, request.report_type, request.start_date, request.end_date, summaries, as_of, activity)


def build_auto_report_response(
    dataset: WeeklyReportDataset,
    report_type: ReportType,
    start_date: date,
    end_date: date,
    project_summaries: list[ProjectSummary] | None = None,
    progress_as_of: str | None = None,
    activity: ReportActivity | None = None,
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
    response = AutoReportResponse(
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
        activity=activity,
    )
    if response.activity is not None:
        response.activity.fingerprint = _report_fingerprint(response)
        heading, _, body = response.markdown.partition("\n")
        response.markdown = heading + "\n\n" + _render_activity(response.activity) + "\n" + body
    return response


def _report_fingerprint(report: AutoReportResponse) -> str:
    content = report.model_dump(mode="json", exclude={"markdown"})
    if content["activity"]:
        content["activity"].pop("as_of")
        content["activity"].pop("fingerprint")
    for candidate in content["progress_candidates"]:
        candidate.pop("as_of")
    serialized = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _render_activity(activity: ReportActivity) -> str:
    labels = {"planned": "예정", "in_progress": "진행", "done": "완료", "on_hold": "보류"}
    sources = {"user": "사용자", "system": "시스템", "milestone_validation": "과거 검증"}
    plans = {"approved": "승인됨", "stale": "재승인 필요", "unapproved": "미승인"}
    lines = [
        "## 조회 기준",
        f"- 조회 시각: {activity.as_of} / 시간대: {activity.timezone}",
        f"- 상태 변경·성과 수정: [{activity.start_at}, {activity.end_exclusive})",
        "- 업무 로그·막힘: 기록일 기준 / 업무명·현재 상태·잔여 WBS: 조회 시점 기준",
        f"- 내용 해시 (스키마 {activity.schema_version}): {activity.fingerprint}",
        "", "## 기간 내 상태 변경",
    ]
    for row in activity.transitions:
        previous = labels.get(row.previous_status, "신규")
        lines.append(f"- {row.changed_at} · {row.project_title} / {row.task_title}: {previous} → {labels.get(row.next_status, row.next_status)} / 현재 {labels.get(row.current_status, row.current_status)} / {sources.get(row.source, row.source)} / 이력 {row.id} · 업무 {row.task_id} · v{row.status_version}")
        if row.reason:
            lines.append(f"  - 사유: {row.reason}")
    if not activity.transitions:
        lines.append("- 기록된 상태 변경 없음")
    lines.extend(["", "## 기록된 막힘"])
    for row in activity.issues:
        lines.append(f"- {row.log_date} · {row.project_title or '프로젝트 미연결'} / {row.title}: {row.blockers} / 로그 {row.id}")
    if not activity.issues:
        lines.append("- 기간 내 기록 없음")
    lines.extend(["", "## 기간 내 수정된 확인 성과"])
    for row in activity.outcomes:
        lines.append(f"- {row.updated_at} · {row.project_title} / {row.title} / 성과 {row.id}")
        if row.before_state or row.after_state:
            lines.append(f"  - 이전: {row.before_state or '미기록'} / 이후: {row.after_state or '미기록'}")
        if row.outcome_type == "quantitative" and row.metric_value is not None:
            lines.append(f"  - 사용자 확인 수치: {row.metric_name} {row.metric_value} {row.metric_unit}")
        evidence = [f"로그 {item}" for item in row.evidence_work_log_ids] + [f"문서 {item}" for item in row.evidence_document_ids]
        lines.append(f"  - 연결 근거: {', '.join(evidence) if evidence else '현재 조회 가능한 근거 없음'}")
    if not activity.outcomes:
        lines.append("- 기간 내 수정된 확인 성과 없음")
    lines.extend(["", "## 현재 잔여 WBS", "- 전체 프로젝트의 조회 시점 산정 업무이며 기간 종료일의 잔여량이 아닙니다."])
    for row in activity.current_tasks:
        due = f" / 기한 {row.due_date}" if row.due_date else ""
        lines.append(f"- {row.project_title} / {row.title}: {labels.get(row.status, row.status)}{due} / 계획 {plans[row.progress_plan_status]} v{row.progress_plan_version} / 업무 {row.id}")
    if not activity.current_tasks:
        lines.append("- 현재 잔여 WBS 없음")
    return "\n".join(lines) + "\n"


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

        progress_percent = summary.progress_percent if summary.progress_plan_status == "approved" and summary.progress_basis != "unscoped" else None
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
                progress_plan_status=summary.progress_plan_status,
                progress_plan_version=summary.progress_plan_version,
                provenance=provenance,
                as_of=as_of,
                reason=reason,
            )
        )
    return candidates


def _utc_as_of() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _progress_provenance(summary: ProjectSummary) -> str:
    if summary.progress_plan_status == "unapproved":
        return "계획 미승인"
    if summary.progress_plan_status == "stale":
        return "계획 재승인 필요"
    if summary.progress_basis == "unscoped":
        return "산정 전"
    return f"{summary.progress_percent}%" if summary.progress_percent is not None else "기준 미확인"


def _progress_reason(summary: ProjectSummary, provenance: str) -> str:
    if summary.progress_plan_status != "approved":
        return f"{provenance}: 등록된 산정 WBS {summary.completed_tasks}/{summary.total_tasks}개, 승인 완료율은 표시하지 않습니다."
    if summary.progress_basis == "unscoped":
        return "산정 대상 WBS가 없어 현재 WBS 진척은 산정 전입니다."
    basis = "승인 마일스톤 가중 WBS" if summary.progress_basis == "milestone" else "승인 WBS 완료 비율"
    derived = f" · 자동 구성 WBS {summary.derived_task_count}개 포함" if summary.derived_task_count > 0 else ""
    return (
        f"계획 v{summary.progress_plan_version} · {basis}: 완료 {summary.completed_tasks}/{summary.total_tasks}개 기준의 현재 WBS 진척입니다"
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
        lines.append(f"- {work_log.log_date.isoformat()} · {work_log.title}{project_label}{duration}: {work_log.content or '내용 없음'} / 로그 {work_log.id}")
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
