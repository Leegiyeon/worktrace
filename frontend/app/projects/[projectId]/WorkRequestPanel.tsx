"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { parseApiErrorMessage } from "../../reports/api-error";
import styles from "./WorkRequestPanel.module.css";

type WorkRequest = {
  id: string;
  title: string;
  body: string;
  desired_outcome: string;
  constraints: string;
  source: "chat" | "manual";
  created_at: string;
};
type RequestPage = { items: WorkRequest[]; total: number };
type Draft = { title: string; body: string; desired_outcome: string; constraints: string };
type Pending = Draft & { request_id: string; source: "manual" };

const emptyDraft: Draft = { title: "", body: "", desired_outcome: "", constraints: "" };

export function WorkRequestPanel({ projectId, active }: { projectId: string; active: boolean }) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [pending, setPending] = useState<Pending | null>(null);
  const [data, setData] = useState<RequestPage | null>(null);
  const [readError, setReadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const sequence = useRef(0);
  const mounted = useRef(true);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/requests`;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; sequence.current += 1; };
  }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    const current = ++sequence.current;
    setLoading(true);
    setReadError("");
    try {
      const response = await fetch(`${endpoint}?limit=20`, { cache: "no-store", signal });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "요청을 불러오지 못했습니다."));
      const next = await response.json() as RequestPage;
      if (mounted.current && current === sequence.current) setData(next);
    } catch (error) {
      if (mounted.current && current === sequence.current && !signal?.aborted)
        setReadError(error instanceof Error ? error.message : "요청을 불러오지 못했습니다.");
    } finally {
      if (mounted.current && current === sequence.current) setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => void load(controller.signal), 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [active, load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || !draft.title.trim()) return;
    const payload: Pending = pending ?? { ...draft, title: draft.title.trim(), request_id: crypto.randomUUID(), source: "manual" };
    busy.current = true;
    setSaving(true);
    setPending(payload);
    setSaveError("");
    setNotice("");
    try {
      const response = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
      });
      if (!mounted.current) return;
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429)
          setPending(null);
        throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "접수 결과를 확인하지 못했습니다. 다시 시도하세요."));
      }
      setPending(null);
      setDraft(emptyDraft);
      setNotice("요청을 접수했습니다. WBS 진척에는 자동 반영되지 않습니다.");
      void load();
    } catch (error) {
      if (mounted.current) setSaveError(error instanceof Error ? error.message : "접수 결과를 확인하지 못했습니다. 다시 시도하세요.");
    } finally {
      busy.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  const locked = saving || pending !== null;
  return (
    <div className={styles.workspace}>
      <section className="panel">
        <div className="panel-title-row"><h2>요청 접수</h2></div>
        <form className="stacked-form compact-form" onSubmit={(event) => void submit(event)}>
          <label>요청 제목<input required maxLength={180} value={draft.title} disabled={locked}
            onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label>상황과 요청<textarea maxLength={10000} value={draft.body} disabled={locked}
            onChange={(event) => setDraft({ ...draft, body: event.target.value })} /></label>
          <div className="form-grid two-columns">
            <label>기대 결과<textarea maxLength={2000} value={draft.desired_outcome} disabled={locked}
              onChange={(event) => setDraft({ ...draft, desired_outcome: event.target.value })} /></label>
            <label>제약 조건<textarea maxLength={2000} value={draft.constraints} disabled={locked}
              onChange={(event) => setDraft({ ...draft, constraints: event.target.value })} /></label>
          </div>
          <div className="form-actions"><button disabled={saving || !draft.title.trim()} type="submit">
            {saving ? "접수 중" : pending ? "같은 요청 재확인" : "요청 접수"}
          </button></div>
        </form>
        {saveError ? <p role="alert" className={styles.error}>{saveError}</p> : null}
        {notice ? <p role="status" className={styles.notice}>{notice}</p> : null}
      </section>
      <section className="panel">
        <div className="panel-title-row"><h2>최근 요청</h2><span className="count-badge">{data?.total ?? "-"}</span></div>
        {loading ? <p role="status">요청을 불러오는 중...</p> : null}
        {readError ? <div role="alert" className={styles.error}>{readError} <button className="secondary-button" type="button" onClick={() => void load()}>다시 조회</button></div> : null}
        {!loading && !readError && data?.total === 0 ? <div className="empty-state">접수된 요청이 없습니다.</div> : null}
        <ul className={styles.list}>
          {data?.items.map((item) => (
            <li key={item.id}>
              <div><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString("ko-KR")} · 접수</small></div>
              {item.body ? <p>{item.body}</p> : null}
              {item.desired_outcome ? <p><b>기대 결과</b> {item.desired_outcome}</p> : null}
              {item.constraints ? <p><b>제약</b> {item.constraints}</p> : null}
            </li>
          ))}
        </ul>
        {data && data.total > data.items.length ? <p className={styles.notice}>최근 20건을 표시합니다.</p> : null}
      </section>
    </div>
  );
}
