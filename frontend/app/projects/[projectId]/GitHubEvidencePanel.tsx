"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { ProjectTask } from "../types";
import { taskStatusLabels } from "../types";
import { parseApiErrorMessage } from "../../reports/api-error";
import styles from "./GitHubEvidencePanel.module.css";

type ReviewStatus = "pending" | "adopted" | "ignored";
type Filter = ReviewStatus | "all";
type GitHubItem = {
  id: string;
  number: number;
  kind: "issue" | "pr";
  title: string;
  body: string;
  body_truncated?: boolean;
  url: string;
  external_state: string;
  source_updated_at: string;
  collected_at: string;
  review_status: ReviewStatus;
  version: number;
  task_id: string | null;
  task_title: string | null;
  reviewed_at: string | null;
  source_changed: boolean;
};
type ItemPage = { items: GitHubItem[]; total: number; counts: Record<ReviewStatus, number> };
type Decision = {
  action: "create" | "link" | "ignore" | "restore";
  expected_version: number;
  expected_source_updated_at: string;
  request_id: string;
  title?: string;
  task_id?: string;
  counts_toward_progress?: boolean;
};
type Props = {
  projectId: string;
  active: boolean;
  tasks: ProjectTask[];
  onPlanningChanged: () => Promise<void>;
  onOpenTask: (task: ProjectTask) => void;
};

const labels: Record<Filter, string> = { pending: "검토 대기", adopted: "업무 연결", ignored: "제외", all: "전체" };
const filters: Filter[] = ["pending", "adopted", "ignored", "all"];
const pageSize = 20;

function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "미확인" : date.toLocaleString("ko-KR");
}

function safeSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "github.com" && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function GitHubEvidencePanel({ projectId, active, tasks, onPlanningChanged, onOpenTask }: Props) {
  const [filter, setFilter] = useState<Filter>("pending");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ItemPage | null>(null);
  const [selected, setSelected] = useState<GitHubItem | null>(null);
  const [mode, setMode] = useState<"create" | "link">("create");
  const [title, setTitle] = useState("");
  const [taskId, setTaskId] = useState("");
  const [counted, setCounted] = useState(true);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [readError, setReadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState<Decision | null>(null);
  const [planningStale, setPlanningStale] = useState(false);
  const busy = useRef(false);
  const mounted = useRef(true);
  const readSequence = useRef(0);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/github-items`;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; readSequence.current += 1; };
  }, []);

  const readItems = useCallback(async (signal?: AbortSignal) => {
    const sequence = ++readSequence.current;
    setLoading(true);
    setReadError("");
    try {
      const response = await fetch(`${endpoint}?review_status=${filter}&limit=${pageSize}&offset=${offset}`, { cache: "no-store", signal });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "GitHub 근거를 불러오지 못했습니다."));
      const next = await response.json() as ItemPage;
      if (!mounted.current || sequence !== readSequence.current) return null;
      setData(next);
      if (offset > 0 && offset >= next.total) setOffset(Math.max(0, Math.floor((next.total - 1) / pageSize) * pageSize));
      return next;
    } catch (error) {
      if (mounted.current && sequence === readSequence.current && !signal?.aborted) {
        setReadError(error instanceof Error ? error.message : "GitHub 근거를 불러오지 못했습니다.");
      }
      return null;
    } finally {
      if (mounted.current && sequence === readSequence.current) setLoading(false);
    }
  }, [endpoint, filter, offset]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => void readItems(controller.signal), 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [active, readItems]);

  async function reloadSource() {
    const next = await readItems();
    if (!next) return;
    if (selected && !pending) {
      setSelected(next.items.find((item) => item.id === selected.id) ?? null);
    }
    setConflict(false);
    setSaveError("");
  }

  function selectItem(item: GitHubItem) {
    setSelected(item);
    setTitle(item.title.slice(0, 240));
    setTaskId("");
    setCounted(true);
    setMode(item.review_status === "adopted" ? "link" : "create");
    setSaveError("");
    setConflict(false);
  }

  async function refreshPlanning() {
    try {
      await onPlanningChanged();
      if (mounted.current) setPlanningStale(false);
    } catch {
      if (mounted.current) setPlanningStale(true);
    }
  }

  async function submit(action: Decision["action"]) {
    if (!selected || busy.current || conflict || readError) return;
    const decision: Decision = pending ?? {
      action,
      expected_version: selected.version,
      expected_source_updated_at: selected.source_updated_at,
      request_id: crypto.randomUUID(),
      ...(action === "create" ? { title: title.trim(), counts_toward_progress: counted } : {}),
      ...(action === "link" ? { task_id: taskId } : {})
    };
    busy.current = true;
    setSaving(true);
    setPending(decision);
    setSaveError("");
    setNotice("");
    try {
      const response = await fetch(`${endpoint}/${encodeURIComponent(selected.id)}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(decision)
      });
      if (!mounted.current) return;
      if (!response.ok) {
        if (response.status === 409) { setConflict(true); setPending(null); }
        else if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) setPending(null);
        throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "저장 결과를 확인하지 못했습니다. 다시 시도하세요."));
      }
      // A successful status resolves the write even if the subsequent list refresh fails.
      setPending(null);
      setSelected(null);
      setNotice(decision.action === "ignore" ? "검토 대상에서 제외했습니다." : decision.action === "restore" ? "검토 대기로 복원했습니다." : "업무에 근거를 연결했습니다.");
      await refreshPlanning();
      if (mounted.current) await readItems();
    } catch (error) {
      if (mounted.current) setSaveError(error instanceof Error ? error.message : "저장 결과를 확인하지 못했습니다. 다시 시도하세요.");
    } finally {
      busy.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  function saveForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit(mode);
  }

  const locked = saving || pending !== null;
  const blocked = locked || loading || conflict || !!readError;
  const sourceUrl = selected ? safeSourceUrl(selected.url) : null;
  const linkedTask = tasks.find((task) => task.id === selected?.task_id);
  const canAdopt = selected?.review_status === "pending" || (selected?.review_status === "adopted" && !selected.task_id);
  // Keep an unresolved write reachable if a later read no longer includes its row.
  const visibleItems = pending && selected && !data?.items.some((item) => item.id === selected.id)
    ? [selected, ...(data?.items ?? [])] : data?.items ?? [];

  return (
    <div className={styles.workspace}>
      <div className={styles.toolbar}>
        <div className={styles.filters} role="group" aria-label="근거 검토 상태">
          {filters.map((value) => <button type="button" key={value} aria-pressed={filter === value} disabled={locked || loading}
            onClick={() => { setFilter(value); setOffset(0); setData(null); setSelected(null); setConflict(false); setSaveError(""); }}>
            {labels[value]} <span>{data ? value === "all" ? Object.values(data.counts).reduce((a, b) => a + b, 0) : data.counts[value] : "-"}</span>
          </button>)}
        </div>
        <button type="button" className="secondary-button" disabled={saving || loading} onClick={() => void reloadSource()}>저장된 근거 새로고침</button>
      </div>
      {notice ? <p role="status" className={styles.success}>{notice}</p> : null}
      {readError ? <p role="alert" className={styles.error}>{readError}</p> : null}
      {planningStale ? <div role="alert" className={styles.warning}>저장은 완료했지만 WBS 현황을 갱신하지 못했습니다. <button type="button" className="secondary-button" onClick={() => void refreshPlanning()}>현황 다시 조회</button></div> : null}
      {loading ? <p role="status">저장된 근거를 불러오는 중...</p> : null}
      {data?.total === 0 && !loading && !readError ? <p className={styles.empty}>{filter === "pending" ? "검토 대기 중인 Issue·PR이 없습니다." : "해당 상태의 Issue·PR이 없습니다."}</p> : null}
      <ul className={styles.list} aria-label="GitHub Issue 및 PR">
        {visibleItems.map((item) => <li key={item.id} className={styles.row}>
          <button type="button" className={styles.itemButton} disabled={locked || loading} aria-expanded={selected?.id === item.id}
            aria-controls={`evidence-${item.id}`} onClick={() => selected?.id === item.id ? setSelected(null) : selectItem(item)}>
            <span className={styles.identity}>{item.kind === "pr" ? "PR" : "Issue"} #{item.number}</span>
            <span className={styles.title}>{item.title || "제목 없음"}</span>
            <span className={styles.state}>{labels[item.review_status]}{item.source_changed ? " · 원본 변경" : ""}</span>
          </button>
          {selected?.id === item.id ? <div id={`evidence-${item.id}`} className={styles.detail}>
            <dl className={styles.metadata}>
              <div><dt>GitHub 상태</dt><dd>{selected.external_state || "미확인"}</dd></div>
              <div><dt>원본 수정</dt><dd>{dateLabel(selected.source_updated_at)}</dd></div>
              <div><dt>마지막 수집</dt><dd>{dateLabel(selected.collected_at)}</dd></div>
              {selected.reviewed_at ? <div><dt>검토 일시</dt><dd>{dateLabel(selected.reviewed_at)}</dd></div> : null}
            </dl>
            {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">GitHub 원본 보기</a> : null}
            <details className={styles.body}><summary>수집된 본문</summary><p>{selected.body || "본문 없음"}</p>{selected.body_truncated ? <p>본문 일부만 표시됨</p> : null}</details>
            {selected.source_changed ? <p className={styles.warning}>검토 이후 GitHub 원본이 변경되었습니다.</p> : null}
            {selected.task_id ? <div className={styles.linked}><span>연결 업무: {selected.task_title || "제목 미확인"}</span>{linkedTask ? <button type="button" className="secondary-button" onClick={() => onOpenTask(linkedTask)}>WBS 열기</button> : <span>WBS 현황에서 연결 업무를 다시 확인하세요.</span>}</div> : null}
            {selected.review_status === "adopted" && !selected.task_id ? <p className={styles.warning}>연결했던 업무가 없습니다. 기존 업무에 다시 연결할 수 있습니다.</p> : null}
            {saveError ? <p role="alert" className={styles.error}>{saveError}</p> : null}
            {conflict ? <button type="button" className="secondary-button" disabled={loading} onClick={() => void reloadSource()}>최신 원본 다시 확인</button> : null}
            {pending && !saving ? <button type="button" className="primary-button" disabled={loading || !!readError} onClick={() => void submit(pending.action)}>동일 요청 다시 확인</button> : null}
            {canAdopt ? <form className={styles.editor} onSubmit={saveForm}>
              <fieldset disabled={blocked}>
                <legend>업무 연결</legend>
                {selected.review_status === "pending" ? <div className={styles.modes}>
                  <label><input type="radio" name={`adoption-${item.id}`} value="create" checked={mode === "create"} onChange={() => setMode("create")} />새 업무</label>
                  <label><input type="radio" name={`adoption-${item.id}`} value="link" checked={mode === "link"} onChange={() => setMode("link")} />기존 업무</label>
                </div> : null}
                {mode === "create" ? <>
                  <label className={styles.field}>업무 제목<input required maxLength={240} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
                  <label className={styles.checkbox}><input type="checkbox" checked={counted} onChange={(event) => setCounted(event.target.checked)} />진척도 산정에 포함</label>
                  <span className={styles.muted}>업무 상태: 예정</span>
                </> : <label className={styles.field}>연결할 업무<select required value={taskId} onChange={(event) => setTaskId(event.target.value)}>
                  <option value="">{tasks.length ? "업무 선택" : "등록된 업무 없음"}</option>
                  {tasks.map((task) => <option value={task.id} key={task.id}>{task.title} · {taskStatusLabels[task.status]}</option>)}
                </select></label>}
                <div className={styles.actions}>
                  <button type="submit" className="primary-button" disabled={mode === "create" ? !title.trim() : !taskId}>{saving ? "저장 중..." : mode === "create" ? "예정 업무로 채택" : "선택 업무에 연결"}</button>
                  {selected.review_status === "pending" ? <button type="button" className="secondary-button" onClick={() => void submit("ignore")}>검토 대상에서 제외</button> : null}
                </div>
              </fieldset>
            </form> : null}
            {selected.review_status === "ignored" ? <button type="button" className="secondary-button" disabled={blocked} onClick={() => void submit("restore")}>검토 대기로 복원</button> : null}
          </div> : null}
        </li>)}
      </ul>
      {data && data.total > 0 ? <nav className={styles.pagination} aria-label="근거 목록 페이지">
        <span>{offset + 1}-{Math.min(offset + pageSize, data.total)} / {data.total}</span>
        <div className={styles.actions}>
          <button type="button" className="secondary-button" disabled={locked || loading || offset === 0} onClick={() => { setOffset(offset - pageSize); setSelected(null); }}>이전</button>
          <button type="button" className="secondary-button" disabled={locked || loading || offset + pageSize >= data.total} onClick={() => { setOffset(offset + pageSize); setSelected(null); }}>다음</button>
        </div>
      </nav> : null}
    </div>
  );
}
