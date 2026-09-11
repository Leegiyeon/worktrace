"use client";

import { useMemo, useState } from "react";

import { parseApiErrorMessage } from "./api-error";
import type { AutoReportResponse, ReportType, TaskAlert } from "./types";

const reportTypeLabels: Record<ReportType, string> = {
  daily: "일일",
  weekly: "주간",
  monthly: "월간"
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
  const [errorMessage, setErrorMessage] = useState("");
  const [copyMessage, setCopyMessage] = useState("");

  const periodLabel = useMemo(() => `${reportTypeLabels[reportType]} · ${startDate} ~ ${endDate}`, [endDate, reportType, startDate]);
  const reportPeriodLabel = useMemo(() => {
    if (!report) return periodLabel;
    return `${reportTypeLabels[report.report_type]} · ${report.start_date} ~ ${report.end_date}`;
  }, [periodLabel, report]);
  const reportMetrics = useMemo(() => {
    if (!report) return { projects: 0, workLogs: 0, remaining: 0, delayed: 0 };
    return {
      projects: report.projects.length,
      workLogs: report.work_logs.length,
      remaining: report.remaining_tasks.length,
      delayed: report.delayed_tasks.length
    };
  }, [report]);

  function clearGeneratedReport() {
    setReport(null);
    setCopyMessage("");
  }

  function updateReportType(value: ReportType) {
    setReportType(value);
    clearGeneratedReport();
  }

  function updateStartDate(value: string) {
    setStartDate(value);
    clearGeneratedReport();
  }

  function updateEndDate(value: string) {
    setEndDate(value);
    clearGeneratedReport();
  }

  async function handleGenerateReport() {
    setErrorMessage("");
    setCopyMessage("");
    const validationMessage = validateReportPeriod(reportType, startDate, endDate);
    if (validationMessage) {
      setErrorMessage(validationMessage);
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch("/api/reports/automatic", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ report_type: reportType, start_date: startDate, end_date: endDate })
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }

      const data = (await response.json()) as AutoReportResponse;
      setReport(data);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
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
        <button type="button" onClick={handleGenerateReport} disabled={isLoading}>{isLoading ? "생성 중" : "리포트 생성"}</button>
      </section>

      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}

      {report ? (
        <>
          <section className="summary-grid dashboard-metrics" aria-label="리포트 지표">
            <div className="metric-card"><span>프로젝트</span><strong>{reportMetrics.projects}</strong></div>
            <div className="metric-card"><span>업무 로그</span><strong>{reportMetrics.workLogs}</strong></div>
            <div className="metric-card"><span>잔여 업무</span><strong>{reportMetrics.remaining}</strong></div>
            <div className="metric-card"><span>지연 업무</span><strong>{reportMetrics.delayed}</strong></div>
          </section>
          <section className="report-evidence-grid" aria-label="자동 리포트 근거">
            <section className="panel dashboard-main-panel">
              <div className="panel-title-row"><h2>업무 로그</h2><span className="count-badge">{report.work_logs.length}개</span></div>
              {report.work_logs.length === 0 ? <div className="empty-state">로그 없음</div> : null}
              {report.work_logs.length > 0 ? (
                <div className="data-table-wrap">
                  <table className="data-table dense-task-table">
                    <thead><tr><th>일자</th><th>업무</th><th>프로젝트</th><th>소요</th><th>다음 액션</th></tr></thead>
                    <tbody>{report.work_logs.slice(0, 10).map((workLog) => (
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
              <div className="panel-title-row"><h2>진행률 후보</h2><span className="count-badge">{report.progress_candidates.length}개</span></div>
              {report.progress_candidates.length === 0 ? <div className="empty-state">후보 없음</div> : null}
              <div className="dense-list">
                {report.progress_candidates.slice(0, 6).map((candidate) => (
                  <div className="dense-list-row" key={candidate.project_id}>
                    <span>{candidate.project_title}</span>
                    <small>{candidate.reason}</small>
                    <b>{candidate.suggested_progress_percent}%</b>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel delayed-panel">
              <div className="panel-title-row"><h2>지연 업무</h2><span className="count-badge danger-count">{report.delayed_tasks.length}개</span></div>
              {report.delayed_tasks.length === 0 ? <div className="empty-state">지연 없음</div> : null}
              <div className="dense-list">
                {report.delayed_tasks.slice(0, 6).map((task) => (
                  <div className="dense-list-row" key={`${task.project_id}-${task.title}`}>
                    <span>{task.title}</span>
                    <small>{task.project_title}</small>
                    <b>{task.due_date ?? "-"}</b>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel completed-panel">
              <div className="panel-title-row"><h2>{report.report_type === "monthly" ? "월간 성과 후보" : "잔여 업무"}</h2><span className="count-badge">{report.report_type === "monthly" ? report.monthly_performance_candidates.length : report.remaining_tasks.length}개</span></div>
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
                  {report.remaining_tasks.slice(0, 8).map((task) => (
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
