"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { parseApiErrorMessage } from "./api-error";
import styles from "./ReportArchive.module.css";
import ReportActivity from "./ReportActivity";
import type { AutoReportResponse, ReportSnapshotDetail, ReportSnapshotListResponse, ReportSnapshotSummary, ReportType, TaskAlert } from "./types";

const reportTypeLabels: Record<ReportType, string> = {
  daily: "일일",
  weekly: "주간",
  monthly: "월간"
};

const archivePageSize = 20;

type ReportRequestState = { sequence: number; filterKey: string };
type SnapshotRequestPayload = { request_id: string; report_type: ReportType; start_date: string; end_date: string };

function makeRequestId() {
  const browserCrypto = globalThis.crypto;
  if (browserCrypto?.randomUUID) return browserCrypto.randomUUID();
  const bytes = new Uint8Array(16);
  browserCrypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
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

function sameSnapshotPayload(payload: SnapshotRequestPayload, reportType: ReportType, startDate: string, endDate: string) {
  return payload.report_type === reportType && payload.start_date === startDate && payload.end_date === endDate;
}

function shortId(value: string) {
  return value.length > 8 ? value.substring(0, 8) : value;
}

function safeMarkdownFilename(snapshot: ReportSnapshotDetail) {
  const id = snapshot.id.replace(/[^a-zA-Z0-9-]/g, "").slice(0, 12) || "snapshot";
  return `worktrace-report-${snapshot.report_type}-${snapshot.start_date}-${snapshot.end_date}-${id}.md`;
}

function SnapshotActions({ snapshot, onDelete, deleting }: { snapshot: ReportSnapshotDetail; onDelete?: () => void; deleting?: boolean }) {
  const [copyMessage, setCopyMessage] = useState("");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(snapshot.report.markdown);
      setCopyMessage("Markdown 리포트를 클립보드에 복사했습니다.");
    } catch {
      setCopyMessage("브라우저 권한 문제로 복사하지 못했습니다. 아래 내용을 직접 선택해 복사하세요.");
    }
  }

  function handleDownload() {
    const blob = new Blob([snapshot.report.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = safeMarkdownFilename(snapshot);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={styles.snapshotActions}>
      {copyMessage ? <div aria-live="polite" className="alert success" role="status">{copyMessage}</div> : null}
      <button type="button" className="secondary-button" onClick={() => void handleCopy()}>Markdown 복사</button>
      <button type="button" className={styles.iconButton} onClick={handleDownload} aria-label="Markdown 다운로드" title="Markdown 다운로드">↓</button>
      {onDelete ? <button type="button" className={`${styles.iconButton} ${styles.deleteButton}`} onClick={onDelete} disabled={deleting} aria-label="보관 리포트 삭제" title="보관 리포트 삭제">×</button> : null}
    </div>
  );
}

function ReportContent({ report, snapshot, onDelete, deleting }: { report: AutoReportResponse; snapshot: ReportSnapshotDetail; onDelete?: () => void; deleting?: boolean }) {
  const reportPeriodLabel = `${reportTypeLabels[report.report_type]} · ${report.start_date} ~ ${report.end_date}`;
  const reportMetrics = !report.activity ? { transitions: "기준 미확인", issues: "기준 미확인", currentTasks: "기준 미확인", outcomes: "기준 미확인" } : {
    transitions: report.activity.transitions.length,
    issues: report.activity.issues.length,
    currentTasks: report.activity.current_tasks.length,
    outcomes: report.activity.outcomes.length
  };

  return (
    <>
      <section className="summary-grid dashboard-metrics" aria-label="리포트 지표">
        <div className="metric-card"><span>기간 내 상태 변경</span><strong>{reportMetrics.transitions}</strong></div>
        <div className="metric-card"><span>기록된 막힘</span><strong>{reportMetrics.issues}</strong></div>
        <div className="metric-card"><span>보관 당시 잔여 WBS</span><strong>{reportMetrics.currentTasks}</strong></div>
        <div className="metric-card"><span>기간 내 수정된 확인 성과</span><strong>{reportMetrics.outcomes}</strong></div>
      </section>
      {report.activity ? <ReportActivity activity={report.activity} snapshotView /> : null}
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
                    <td>{workLog.log_date}</td><td>{workLog.title}</td><td>{workLog.project_title || "-"}</td><td>{workLog.duration_minutes}분</td><td className="truncate-cell">{workLog.next_actions || "-"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : null}
        </section>
        <section className="panel status-graph-panel">
          <div className="panel-title-row"><h2>보관 당시 WBS 진척</h2><span className="count-badge">{report.progress_candidates.length}개</span></div>
          {report.progress_candidates.length === 0 ? <div className="empty-state">해당 기간의 프로젝트 없음</div> : null}
          <div className="dense-list">
            {report.progress_candidates.map((candidate) => (
              <div className="dense-list-row" key={candidate.project_id}>
                <span>{candidate.project_title}</span>
                <small>{candidate.reason}<br />기준 시각: {candidate.as_of ? formatDateTime(candidate.as_of) : "미확인"} (한국 시간)</small>
                <b>{candidate.provenance || "기준 미확인"}</b>
              </div>
            ))}
          </div>
        </section>
        <section className="panel delayed-panel">
          <div className="panel-title-row"><h2>기간 내 문서 추출 지연 항목</h2><span className="count-badge danger-count">{report.delayed_tasks.length}개</span></div>
          {report.delayed_tasks.length === 0 ? <div className="empty-state">지연 없음</div> : null}
          <div className="dense-list">{report.delayed_tasks.map((task) => <div className="dense-list-row" key={`${task.project_id}-${task.title}`}><span>{task.title}</span><small>{task.project_title}</small><b>{task.due_date ?? "-"}</b></div>)}</div>
        </section>
        <section className="panel completed-panel">
          <div className="panel-title-row"><h2>{report.report_type === "monthly" ? "월간 성과 후보" : "기간 내 문서 추출 잔여 항목"}</h2><span className="count-badge">{report.report_type === "monthly" ? report.monthly_performance_candidates.length : report.remaining_tasks.length}개</span></div>
          {report.report_type === "monthly" ? (
            <div className="dense-list">
              {report.monthly_performance_candidates.length === 0 ? <div className="empty-state">성과 후보 없음</div> : null}
              {report.monthly_performance_candidates.map((candidate) => <div className="dense-list-row" key={candidate.project_id}><span>{candidate.project_title}</span><small>{candidate.qualitative_improvement}</small><b>{candidate.resume_ready ? "가능" : "보강"}</b></div>)}
            </div>
          ) : (
            <div className="dense-list">
              {report.remaining_tasks.length === 0 ? <div className="empty-state">잔여 업무 없음</div> : null}
              {report.remaining_tasks.map((task) => <div className="dense-list-row" key={`${task.project_id}-${task.title}`}><span>{renderTaskAlert(task)}</span><small>{task.status}</small><b>{task.due_date ?? "-"}</b></div>)}
            </div>
          )}
        </section>
      </section>
      <section className="panel report-result" aria-label={`${reportPeriodLabel} 보관 리포트 결과`}>
        <div className="report-result-header">
          <div>
            <h2>{reportPeriodLabel}</h2>
            <div className={styles.snapshotBanner}><span className="meta-pill status-navy">조회 기준 {formatDateTime(snapshot.as_of)}</span><span className="meta-pill">저장 시각 {formatDateTime(snapshot.created_at)}</span><span className="meta-pill">ID {shortId(snapshot.id)}</span></div>
          </div>
          <SnapshotActions key={snapshot.id} snapshot={snapshot} onDelete={onDelete} deleting={deleting} />
        </div>
        <pre className="markdown-output">{report.markdown}</pre>
      </section>
    </>
  );
}

export default function WeeklyReportPage() {
  const [activeTab, setActiveTab] = useState<"new" | "archive">("new");
  const [reportType, setReportType] = useState<ReportType>("weekly");
  const [startDate, setStartDate] = useState(getDefaultStartDate);
  const [endDate, setEndDate] = useState(getDefaultEndDate);
  const [generatedSnapshot, setGeneratedSnapshot] = useState<ReportSnapshotDetail | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<ReportSnapshotDetail | null>(null);
  const [archive, setArchive] = useState<ReportSnapshotListResponse | null>(null);
  const [archiveOffset, setArchiveOffset] = useState(0);
  const [archiveError, setArchiveError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [deleteError, setDeleteError] = useState<{ snapshotId: string; message: string } | null>(null);
  const [detailRetrySnapshot, setDetailRetrySnapshot] = useState<ReportSnapshotSummary | null>(null);
  const [isArchiveLoading, setIsArchiveLoading] = useState(false);
  const [loadingSnapshotId, setLoadingSnapshotId] = useState("");
  const [deletingSnapshotId, setDeletingSnapshotId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingFilterKey, setLoadingFilterKey] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const reportTypeRef = useRef(reportType);
  const startDateRef = useRef(startDate);
  const endDateRef = useRef(endDate);
  const latestRequestRef = useRef<ReportRequestState>({ sequence: 0, filterKey: "" });
  const busyRequestRef = useRef<ReportRequestState | null>(null);
  const failedSnapshotRequestsRef = useRef(new Map<string, SnapshotRequestPayload>());
  const archiveSequenceRef = useRef(0);
  const detailSequenceRef = useRef(0);
  const activeTabRef = useRef(activeTab);
  const archiveLoadedOnceRef = useRef(false);
  const deleteBusyRef = useRef(false);
  const deletedSnapshotIdsRef = useRef(new Set<string>());

  const currentFilterKey = `${reportType}:${startDate}:${endDate}`;
  const isCurrentFilterLoading = isLoading && loadingFilterKey === currentFilterKey;
  const periodLabel = useMemo(() => `${reportTypeLabels[reportType]} · ${startDate} ~ ${endDate}`, [endDate, reportType, startDate]);
  const headerPeriodLabel = activeTab === "archive"
    ? selectedSnapshot ? `${reportTypeLabels[selectedSnapshot.report_type]} · ${selectedSnapshot.start_date} ~ ${selectedSnapshot.end_date}` : "보관함"
    : periodLabel;

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  function reportFilterKey(nextReportType = reportTypeRef.current, nextStartDate = startDateRef.current, nextEndDate = endDateRef.current) {
    return `${nextReportType}:${nextStartDate}:${nextEndDate}`;
  }

  function clearGeneratedReport() {
    latestRequestRef.current = { sequence: latestRequestRef.current.sequence + 1, filterKey: reportFilterKey() };
    setGeneratedSnapshot(null);
    setIsLoading(false);
    setLoadingFilterKey("");
  }

  function updateReportType(value: ReportType) { reportTypeRef.current = value; setReportType(value); clearGeneratedReport(); }
  function updateStartDate(value: string) { startDateRef.current = value; setStartDate(value); clearGeneratedReport(); }
  function updateEndDate(value: string) { endDateRef.current = value; setEndDate(value); clearGeneratedReport(); }

  const loadArchive = useCallback(async (offset = archiveOffset) => {
    const request = ++archiveSequenceRef.current;
    setIsArchiveLoading(true);
    setArchiveError("");
    setArchive(null);
    try {
      let response = await fetch(`/api/reports/snapshots?limit=${archivePageSize}&offset=${offset}`, { cache: "no-store" });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "보관함을 불러오지 못했습니다."));
      let data = (await response.json()) as ReportSnapshotListResponse;
      if (request !== archiveSequenceRef.current) return;
      if (data.total > 0 && data.offset >= data.total) {
        const clampedOffset = Math.max(0, Math.floor((data.total - 1) / data.limit) * data.limit);
        if (clampedOffset !== data.offset) {
          response = await fetch(`/api/reports/snapshots?limit=${archivePageSize}&offset=${clampedOffset}`, { cache: "no-store" });
          if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "보관함을 불러오지 못했습니다."));
          data = (await response.json()) as ReportSnapshotListResponse;
          if (request !== archiveSequenceRef.current) return;
        }
      }
      setArchive(data);
      setArchiveOffset(data.offset);
      archiveLoadedOnceRef.current = true;
    } catch (error) {
      if (request !== archiveSequenceRef.current) return;
      setArchiveError(error instanceof Error ? error.message : "보관함을 불러오지 못했습니다.");
    } finally {
      if (request === archiveSequenceRef.current) setIsArchiveLoading(false);
    }
  }, [archiveOffset]);

  useEffect(() => {
    if (activeTab === "archive" && !archiveLoadedOnceRef.current && !archiveError && !isArchiveLoading) void loadArchive(0);
  }, [activeTab, archiveError, isArchiveLoading, loadArchive]);

  async function handleGenerateReport() {
    setErrorMessage("");
    setDetailError("");
    const requestReportType = reportTypeRef.current;
    const requestStartDate = startDateRef.current;
    const requestEndDate = endDateRef.current;
    const requestFilterKey = reportFilterKey(requestReportType, requestStartDate, requestEndDate);
    if (busyRequestRef.current?.filterKey === requestFilterKey && busyRequestRef.current.sequence === latestRequestRef.current.sequence) return;
    const validationMessage = validateReportPeriod(requestReportType, requestStartDate, requestEndDate);
    if (validationMessage) { setErrorMessage(validationMessage); return; }

    const failedPayload = failedSnapshotRequestsRef.current.get(requestFilterKey);
    const payload = failedPayload && sameSnapshotPayload(failedPayload, requestReportType, requestStartDate, requestEndDate)
      ? failedPayload
      : { request_id: makeRequestId(), report_type: requestReportType, start_date: requestStartDate, end_date: requestEndDate };
    failedSnapshotRequestsRef.current.set(requestFilterKey, payload);

    const requestSequence = latestRequestRef.current.sequence + 1;
    const requestState = { sequence: requestSequence, filterKey: requestFilterKey };
    latestRequestRef.current = requestState;
    busyRequestRef.current = requestState;
    setGeneratedSnapshot(null);
    setIsLoading(true);
    setLoadingFilterKey(requestFilterKey);

    try {
      const response = await fetch("/api/reports/snapshots", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null)));
      const data = (await response.json()) as ReportSnapshotDetail;
      if (failedSnapshotRequestsRef.current.get(requestFilterKey)?.request_id === payload.request_id) failedSnapshotRequestsRef.current.delete(requestFilterKey);
      archiveLoadedOnceRef.current = false;
      if (latestRequestRef.current.sequence !== requestSequence || latestRequestRef.current.filterKey !== requestFilterKey) return;
      setGeneratedSnapshot(data);
      if (activeTabRef.current === "new") setArchive(null);
    } catch (error) {
      if (latestRequestRef.current.sequence !== requestSequence || latestRequestRef.current.filterKey !== requestFilterKey) return;
      if (activeTabRef.current === "new") setErrorMessage(error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      if (latestRequestRef.current.sequence === requestSequence && latestRequestRef.current.filterKey === requestFilterKey) { setIsLoading(false); setLoadingFilterKey(""); }
      if (busyRequestRef.current?.sequence === requestSequence) busyRequestRef.current = null;
    }
  }

  async function loadSnapshot(snapshot: ReportSnapshotSummary) {
    if (deleteBusyRef.current) return;
    const request = ++detailSequenceRef.current;
    setLoadingSnapshotId(snapshot.id);
    setSelectedSnapshot(null);
    setDetailError("");
    setDetailRetrySnapshot(null);
    try {
      const response = await fetch(`/api/reports/snapshots/${encodeURIComponent(snapshot.id)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "보관 리포트를 불러오지 못했습니다."));
      const data = (await response.json()) as ReportSnapshotDetail;
      if (request !== detailSequenceRef.current || deletedSnapshotIdsRef.current.has(snapshot.id)) return;
      setSelectedSnapshot(data);
    } catch (error) {
      if (request !== detailSequenceRef.current) return;
      setDetailRetrySnapshot(snapshot);
      setDetailError(error instanceof Error ? error.message : "보관 리포트를 불러오지 못했습니다.");
    } finally {
      if (request === detailSequenceRef.current) setLoadingSnapshotId("");
    }
  }

  async function deleteSnapshot(snapshot: ReportSnapshotDetail) {
    if (deleteBusyRef.current) return;
    if (!window.confirm("보관본만 영구 삭제할까요? 원본 업무 기록과 프로젝트 데이터는 삭제되지 않습니다.")) return;
    deleteBusyRef.current = true;
    detailSequenceRef.current += 1;
    setLoadingSnapshotId("");
    setDetailRetrySnapshot(null);
    setDeletingSnapshotId(snapshot.id);
    setDeleteError(null);
    try {
      const response = await fetch(`/api/reports/snapshots/${encodeURIComponent(snapshot.id)}`, { method: "DELETE" });
      if (!response.ok && response.status !== 404) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "보관 리포트를 삭제하지 못했습니다."));
      deletedSnapshotIdsRef.current.add(snapshot.id);
      setSelectedSnapshot((current) => current?.id === snapshot.id ? null : current);
      setGeneratedSnapshot((current) => current?.id === snapshot.id ? null : current);
      const remainingOnPage = archive?.items.filter((item) => item.id !== snapshot.id).length ?? 0;
      const nextOffset = remainingOnPage === 0 && archiveOffset > 0 ? Math.max(0, archiveOffset - archivePageSize) : archiveOffset;
      await loadArchive(nextOffset);
    } catch (error) {
      setDeleteError({ snapshotId: snapshot.id, message: error instanceof Error ? error.message : "보관 리포트를 삭제하지 못했습니다." });
    } finally {
      deleteBusyRef.current = false;
      setDeletingSnapshotId("");
    }
  }

  return (
    <main className="page-shell report-page">
      <header className="dashboard-topbar compact-topbar"><div><h1>자동 리포트</h1></div><div className="task-meta"><span className="meta-pill status-navy">{headerPeriodLabel}</span></div></header>
      <nav className={styles.modeTabs} aria-label="리포트 보기">
        <button type="button" aria-pressed={activeTab === "new"} onClick={() => setActiveTab("new")}>새 리포트</button>
        <button type="button" aria-pressed={activeTab === "archive"} onClick={() => { setActiveTab("archive"); void loadArchive(0); }}>보관함</button>
      </nav>

      {activeTab === "new" ? (
        <section className="panel report-controls" aria-label="리포트 기간 선택">
          <label>유형<select value={reportType} onChange={(event) => updateReportType(event.target.value as ReportType)}>{Object.entries(reportTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>시작일<input required type="date" value={startDate} onChange={(event) => updateStartDate(event.target.value)} /></label>
          <label>종료일<input required type="date" value={endDate} onChange={(event) => updateEndDate(event.target.value)} /></label>
          <button type="button" onClick={() => void handleGenerateReport()} disabled={isCurrentFilterLoading}>{isCurrentFilterLoading ? "생성 중" : "생성·보관"}</button>
        </section>
      ) : (
        <section className={styles.archiveLayout} aria-label="보관 리포트 목록">
          <aside className={`panel ${styles.archivePanel}`}>
            <div className="panel-title-row"><h2>보관함</h2><span className="count-badge">{archive ? `${archive.items.length} / ${archive.total}개` : "-"}</span></div>
            {archiveError ? <div className="alert error" role="alert">{archiveError} <button type="button" className="secondary-button" onClick={() => void loadArchive(archiveOffset)}>다시 시도</button></div> : null}
            {!archiveError && isArchiveLoading ? <div className="empty-state" role="status">보관함 불러오는 중</div> : null}
            {!archiveError && archive && archive.items.length === 0 ? <div className="empty-state">보관 항목 없음</div> : null}
            {archive && archive.items.length > 0 ? <div className={styles.archiveList} role="list">{archive.items.map((item) => <div role="listitem" key={item.id}><button type="button" className={styles.archiveItem} aria-current={selectedSnapshot?.id === item.id} onClick={() => void loadSnapshot(item)} disabled={loadingSnapshotId === item.id}><strong>{reportTypeLabels[item.report_type]} · {item.start_date} ~ {item.end_date}</strong><span className={styles.archiveMeta}><span className="meta-pill">조회 기준 {formatDateTime(item.as_of)}</span><span className="meta-pill">저장 시각 {formatDateTime(item.created_at)}</span><span className="meta-pill">스키마 {item.schema_version}</span></span><small>요청 {shortId(item.request_id)} · 해시 {shortId(item.fingerprint)}</small></button></div>)}</div> : null}
            {archive ? <div className={styles.pager}><button type="button" className="secondary-button" disabled={isArchiveLoading || archive.offset === 0} onClick={() => void loadArchive(Math.max(0, archive.offset - archive.limit))}>이전</button><span className="meta-pill">{archive.total === 0 ? 0 : archive.offset + 1}-{Math.min(archive.offset + archive.items.length, archive.total)} / {archive.total}</span><button type="button" className="secondary-button" disabled={isArchiveLoading || archive.offset + archive.limit >= archive.total} onClick={() => void loadArchive(archive.offset + archive.limit)}>다음</button></div> : null}
          </aside>
          <div className={styles.detailColumn}>
            {deleteError && deleteError.snapshotId === selectedSnapshot?.id ? <div className="alert error" role="alert">{deleteError.message}</div> : null}
            {detailError ? <div className="alert error" role="alert">{detailError} {detailRetrySnapshot ? <button type="button" className="secondary-button" onClick={() => void loadSnapshot(detailRetrySnapshot)}>다시 시도</button> : null}</div> : null}
            {loadingSnapshotId ? <section className="panel"><div className="empty-state" role="status">보관 리포트 불러오는 중</div></section> : null}
            {!selectedSnapshot && !detailError && !loadingSnapshotId ? <section className="panel"><div className="empty-state">보관 리포트를 선택하세요.</div></section> : null}
            {selectedSnapshot ? <ReportContent report={selectedSnapshot.report} snapshot={selectedSnapshot} onDelete={() => void deleteSnapshot(selectedSnapshot)} deleting={deletingSnapshotId === selectedSnapshot.id} /> : null}
          </div>
        </section>
      )}

      {activeTab === "new" && errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
      {activeTab === "new" && deleteError && deleteError.snapshotId === generatedSnapshot?.id ? <div className="alert error" role="alert">{deleteError.message}</div> : null}
      {activeTab === "new" && generatedSnapshot ? <ReportContent report={generatedSnapshot.report} snapshot={generatedSnapshot} onDelete={() => void deleteSnapshot(generatedSnapshot)} deleting={deletingSnapshotId === generatedSnapshot.id} /> : null}
    </main>
  );
}
