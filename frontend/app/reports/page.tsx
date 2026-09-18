"use client";

import { useMemo, useRef, useState } from "react";

import { parseApiErrorMessage } from "./api-error";
import ReportActivity from "./ReportActivity";
import type { AutoReportResponse, ReportType, TaskAlert } from "./types";

const reportTypeLabels: Record<ReportType, string> = {
  daily: "일일",
  weekly: "주간",
  monthly: "월간"
};

type ReportRequestState = {
  sequence: number;
  filterKey: string;
};

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDefaultStartDate() {
  const today = new Date();
  const day = today.getDay();
  const daysFromMonday = day === 0 ? 6 : day - 1;
  today.setDate(today.getDate() - daysFromMonday);
  return formatDate(today);
}

function getDefaultEndDate() {
  return formatDate(new Date());
}

function daysBetween(startDate: string, endDate: string) {
  const [startYear, startMonth, startDay] = startDate.split("-").map(Number);
  const [endYear, endMonth, endDay] = endDate.split("-").map(Number);
  const start = Date.UTC(startYear, startMonth - 1, startDay);
  const end = Date.UTC(endYear, endMonth - 1, endDay);
  return Math.round((end - start) / 86_400_000);
}

function validateReportPeriod(reportType: ReportType, startDate: string, endDate: string) {
  if (!startDate || !endDate) return "리포트 기간을 선택하세요.";
  if (startDate > endDate) return "시작일은 종료일보다 늦을 수 없습니다.";

  const days = daysBetween(startDate, endDate);
  if (reportType === "daily" && days > 0) return "일일 리포트는 하루만 선택하세요.";
  if (reportType === "weekly" && days > 6) return "주간 리포트 기간은 7일을 넘을 수 없습니다.";
  if (reportType === "monthly" && days > 31) return "월간 리포트 기간은 32일을 넘을 수 없습니다.";
  return "";
}

function renderTaskAlert(alert: TaskAlert) {
  const due = alert.due_date ? ` · ${alert.due_date}` : "";
  const delayed = alert.is_delayed ? " · 지연" : "";
  return `${alert.project_title}: ${alert.title}${due}${delayed}`;
}

export default function WeeklyReportPage() {
  const [reportType, setReportType] = useState<ReportType>("weekly");
  const [startDate, setStartDate] = useState(getDefaultStartDate);
  const [endDate, setEndDate] = useState(getDefaultEndDate);
  const [report, setReport] = useState<AutoReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingFilterKey, setLoadingFilterKey] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const reportTypeRef = useRef(reportType);
  const startDateRef = useRef(startDate);
  const endDateRef = useRef(endDate);
  const latestRequestRef = useRef<ReportRequestState>({ sequence: 0, filterKey: "" });
  const busyRequestRef = useRef<ReportRequestState | null>(null);

  const currentFilterKey = `${reportType}:${startDate}:${endDate}`;
  const isCurrentFilterLoading = isLoading && loadingFilterKey === currentFilterKey;
  const periodLabel = useMemo(() => `${reportTypeLabels[reportType]} · ${startDate} ~ ${endDate}`, [endDate, reportType, startDate]);
  const reportPeriodLabel = useMemo(() => {
    if (!report) return periodLabel;
    return `${reportTypeLabels[report.report_type]} · ${report.start_date} ~ ${report.end_date}`;
  }, [periodLabel, report]);
  const reportMetrics = useMemo(() => {
    if (!report) return { transitions: "기준 미확인", issues: "기준 미확인", currentTasks: "기준 미확인", outcomes: "기준 미확인" };
    if (!report.activity) return { transitions: "기준 미확인", issues: "기준 미확인", currentTasks: "기준 미확인", outcomes: "기준 미확인" };
    return {
      transitions: report.activity.transitions.length,
      issues: report.activity.issues.length,
      currentTasks: report.activity.current_tasks.length,
      outcomes: report.activity.outcomes.length
    };
  }, [report]);

  function reportFilterKey(nextReportType = reportTypeRef.current, nextStartDate = startDateRef.current, nextEndDate = endDateRef.current) {
    return `${nextReportType}:${nextStartDate}:${nextEndDate}`;
  }

  function clearGeneratedReport() {
    latestRequestRef.current = { sequence: latestRequestRef.current.sequence + 1, filterKey: reportFilterKey() };
    setReport(null);
    setIsLoading(false);
    setLoadingFilterKey("");
    setCopyMessage("");
  }

  function updateReportType(value: ReportType) {
    reportTypeRef.current = value;
    setReportType(value);
    clearGeneratedReport();
  }

  function updateStartDate(value: string) {
    startDateRef.current = value;
    setStartDate(value);
    clearGeneratedReport();
  }

  function updateEndDate(value: string) {
    endDateRef.current = value;
    setEndDate(value);
    clearGeneratedReport();
  }

  async function handleGenerateReport() {
    setErrorMessage("");
    setCopyMessage("");
    const requestReportType = reportTypeRef.current;
    const requestStartDate = startDateRef.current;
    const requestEndDate = endDateRef.current;
    const requestFilterKey = reportFilterKey(requestReportType, requestStartDate, requestEndDate);
    if (busyRequestRef.current?.filterKey === requestFilterKey && busyRequestRef.current.sequence === latestRequestRef.current.sequence) return;

    const validationMessage = validateReportPeriod(requestReportType, requestStartDate, requestEndDate);
    if (validationMessage) {
      setErrorMessage(validationMessage);
      return;
    }

    const requestSequence = latestRequestRef.current.sequence + 1;
    const requestState = { sequence: requestSequence, filterKey: requestFilterKey };
    latestRequestRef.current = requestState;
    busyRequestRef.current = requestState;
    setReport(null);
    setIsLoading(true);
    setLoadingFilterKey(requestFilterKey);

    try {
      const response = await fetch("/api/reports/automatic", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ report_type: requestReportType, start_date: requestStartDate, end_date: requestEndDate })
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }

      const data = (await response.json()) as AutoReportResponse;
      if (latestRequestRef.current.sequence !== requestSequence || latestRequestRef.current.filterKey !== requestFilterKey) return;
      setReport(data);
    } catch (error) {
      if (latestRequestRef.current.sequence !== requestSequence || latestRequestRef.current.filterKey !== requestFilterKey) return;
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      if (latestRequestRef.current.sequence === requestSequence && latestRequestRef.current.filterKey === requestFilterKey) {
        setIsLoading(false);
        setLoadingFilterKey("");
      }
      if (busyRequestRef.current?.sequence === requestSequence) {
        busyRequestRef.current = null;
      }
    }
  }

  async function handleCopy() {
    if (!report?.markdown) return;

    try {
      await navigator.clipboard.writeText(report.markdown);
      setCopyMessage("Markdown 리포트를 클립보드에 복사했습니다.");
    } catch {
      setCopyMessage("브라우저 권한 문제로 복사하지 못했습니다. 아래 내용을 직접 선택해 복사하세요.");
    }
  }

  return (
    <main className="page-shell report-page">
      <header className="dashboard-topbar compact-topbar">
        <div>
          <h1>자동 리포트</h1>
        </div>
        <div className="task-meta"><span className="meta-pill status-navy">{periodLabel}</span></div>
      </header>

      <section className="panel report-controls" aria-label="리포트 기간 선택">
        <label>유형
          <select value={reportType} onChange={(event) => updateReportType(event.target.value as ReportType)}>
            {Object.entries(reportTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>시작일<input required type="date" value={startDate} onChange={(event) => updateStartDate(event.target.value)} /></label>
        <label>종료일<input required type="date" value={endDate} onChange={(event) => updateEndDate(event.target.value)} /></label>
        <button type="button" onClick={handleGenerateReport} disabled={isCurrentFilterLoading}>{isCurrentFilterLoading ? "생성 중" : "리포트 생성"}</button>
      </section>

      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}

      {report ? (
        <>
          <section className="summary-grid dashboard-metrics" aria-label="리포트 지표">
            <div className="metric-card"><span>기간 내 상태 변경</span><strong>{reportMetrics.transitions}</strong></div>
            <div className="metric-card"><span>기록된 막힘</span><strong>{reportMetrics.issues}</strong></div>
            <div className="metric-card"><span>현재 잔여 WBS</span><strong>{reportMetrics.currentTasks}</strong></div>
            <div className="metric-card"><span>기간 내 수정된 확인 성과</span><strong>{reportMetrics.outcomes}</strong></div>
          </section>
          {report.activity ? <ReportActivity activity={report.activity} /> : null}
          <section className="report-evidence-grid" aria-label="자동 리포트 근거">
            <section className="panel dashboard-main-panel">
              <div className="panel-title-row"><h2>업무 로그</h2><span className="count-badge">{report.work_logs.length}개</span></div>
              {report.work_logs.length === 0 ? <div className="empty-state">로그 없음</div> : null}
              {report.work_logs.length > 0 ? (
                <div className="data-table-wrap">
                  <table className="data-table dense-task-table">
                    <thead><tr><th>일자</th><th>업무</th><th>프로젝트</th><th>소요</th><th>다음 액션</th></tr></thead>
                    <tbody>{report.work_logs.map((workLog) => (
                      <tr key={workLog.id}>
                        <td>{workLog.log_date}</td>
                        <td>{workLog.title}</td>
                        <td>{workLog.project_title || "-"}</td>
                        <td>{workLog.duration_minutes}분</td>
                        <td className="truncate-cell">{workLog.next_actions || "-"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : null}
            </section>
            <section className="panel status-graph-panel">
              <div className="panel-title-row"><h2>현재 WBS 진척</h2><span className="count-badge">{report.progress_candidates.length}개</span></div>
              {report.progress_candidates.length === 0 ? <div className="empty-state">해당 기간의 프로젝트 없음</div> : null}
              <div className="dense-list">
                {report.progress_candidates.map((candidate) => (
                  <div className="dense-list-row" key={candidate.project_id}>
                    <span>{candidate.project_title}</span>
                    <small>{candidate.reason}<br />기준 시각: {candidate.as_of ? new Date(candidate.as_of).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "미확인"} (한국 시간)</small>
                    <b>{candidate.provenance || "기준 미확인"}</b>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel delayed-panel">
              <div className="panel-title-row"><h2>기간 내 문서 추출 지연 항목</h2><span className="count-badge danger-count">{report.delayed_tasks.length}개</span></div>
              {report.delayed_tasks.length === 0 ? <div className="empty-state">지연 없음</div> : null}
              <div className="dense-list">
                {report.delayed_tasks.map((task) => (
                  <div className="dense-list-row" key={`${task.project_id}-${task.title}`}>
                    <span>{task.title}</span>
                    <small>{task.project_title}</small>
                    <b>{task.due_date ?? "-"}</b>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel completed-panel">
              <div className="panel-title-row"><h2>{report.report_type === "monthly" ? "월간 성과 후보" : "기간 내 문서 추출 잔여 항목"}</h2><span className="count-badge">{report.report_type === "monthly" ? report.monthly_performance_candidates.length : report.remaining_tasks.length}개</span></div>
              {report.report_type === "monthly" ? (
                <div className="dense-list">
                  {report.monthly_performance_candidates.length === 0 ? <div className="empty-state">성과 후보 없음</div> : null}
                  {report.monthly_performance_candidates.map((candidate) => (
                    <div className="dense-list-row" key={candidate.project_id}>
                      <span>{candidate.project_title}</span>
                      <small>{candidate.qualitative_improvement}</small>
                      <b>{candidate.resume_ready ? "가능" : "보강"}</b>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="dense-list">
                  {report.remaining_tasks.length === 0 ? <div className="empty-state">잔여 업무 없음</div> : null}
                  {report.remaining_tasks.map((task) => (
                    <div className="dense-list-row" key={`${task.project_id}-${task.title}`}>
                      <span>{renderTaskAlert(task)}</span>
                      <small>{task.status}</small>
                      <b>{task.due_date ?? "-"}</b>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </section>
          <section className="panel report-result" aria-label={`${reportPeriodLabel} 자동 리포트 결과`}>
            <div className="report-result-header"><h2>{reportPeriodLabel}</h2><button type="button" className="secondary-button" onClick={handleCopy}>Markdown 복사</button></div>
            {copyMessage ? <div aria-live="polite" className="alert success" role="status">{copyMessage}</div> : null}
            <pre className="markdown-output">{report.markdown}</pre>
          </section>
        </>
      ) : null}
    </main>
  );
}
