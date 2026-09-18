"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { ProjectStatus, ProjectSummary, ServiceStatus } from "../types";
import { projectStatusLabels, serviceStatusLabels } from "../types";
import { parseApiErrorMessage } from "../../reports/api-error";
import styles from "./ProjectLifecyclePanel.module.css";

type History = {
  id: string;
  previous_status: ProjectStatus;
  status: ProjectStatus;
  previous_service_status: ServiceStatus;
  service_status: ServiceStatus;
  reason: string;
  incomplete_reason: string | null;
  development_ended_on: string | null;
  confirmed_at: string;
  actor_owner_id: string;
};
export type Lifecycle = {
  status: ProjectStatus;
  service_status: ServiceStatus;
  development_ended_on: string | null;
  lifecycle_version: number;
  lifecycle_confirmed_at: string | null;
  pending_task_count: number;
  history: History[];
};
type Decision = {
  status: ProjectStatus;
  service_status: ServiceStatus;
  development_ended_on: string | null;
  reason: string;
  incomplete_reason: string | null;
  expected_version: number;
  request_id: string;
};

export function ProjectLifecyclePanel({ project, onSaved }: { project: ProjectSummary; onSaved: (value: Lifecycle) => void }) {
  const [snapshot, setSnapshot] = useState<Lifecycle | null>(null);
  const [editing, setEditing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [status, setStatus] = useState<ProjectStatus>(project.status);
  const [service, setService] = useState<ServiceStatus>(project.service_status ?? "unknown");
  const [endedOn, setEndedOn] = useState(project.development_ended_on ?? "");
  const [reason, setReason] = useState("");
  const [incompleteReason, setIncompleteReason] = useState("");
  const [pending, setPending] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const live = useRef(true);
  const busy = useRef(false);
  const sequence = useRef(0);
  const endpoint = `/api/projects/${encodeURIComponent(project.id)}/lifecycle`;

  useEffect(() => {
    live.current = true;
    sequence.current++;
    return () => { live.current = false; };
  }, []);

  async function readSnapshot(initialize = false) {
    const request = ++sequence.current;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "상태 이력을 불러오지 못했습니다."));
      const data = await response.json() as Lifecycle;
      if (!live.current || request !== sequence.current) return;
      setSnapshot(data);
      onSaved(data);
      if (initialize) { setStatus(data.status); setService(data.service_status); setEndedOn(data.development_ended_on ?? ""); }
      setConflict(false);
    } catch (failure) {
      if (live.current && request === sequence.current) setError(failure instanceof Error ? failure.message : "상태 조회 실패");
    } finally {
      if (live.current && request === sequence.current) setLoading(false);
    }
  }

  async function save(event?: FormEvent) {
    event?.preventDefault();
    if (!snapshot || busy.current || conflict) return;
    const body = pending ?? {
      status, service_status: service, development_ended_on: status === "done" && endedOn ? endedOn : null,
      reason: reason.trim(), incomplete_reason: status === "done" ? incompleteReason.trim() || null : null,
      expected_version: snapshot.lifecycle_version, request_id: crypto.randomUUID()
    };
    busy.current = true;
    setSaving(true); setPending(body); setError(""); setNotice("");
    try {
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!live.current) return;
      if (!response.ok) {
        if (response.status === 409) { setPending(null); setConflict(true); }
        else if (response.status >= 400 && response.status < 500 && ![408, 429].includes(response.status)) setPending(null);
        throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "확인 결과를 저장하지 못했습니다."));
      }
      const data = await response.json() as Lifecycle;
      if (!live.current) return;
      setSnapshot(data); setPending(null); setEditing(false); setReason(""); setIncompleteReason("");
      onSaved(data);
      setNotice("개발·운영 상태 확인을 기록했습니다.");
    } catch (failure) {
      if (live.current) setError(failure instanceof Error ? failure.message : "저장 결과를 확인하지 못했습니다.");
    } finally {
      busy.current = false;
      if (live.current) setSaving(false);
    }
  }

  const locked = saving || pending !== null;
  return <section className={styles.panel} aria-label="개발 및 운영 상태 확인">
    <div className={styles.heading}>
      <h2>개발·운영 상태</h2>
      <div className={styles.actions}>
        <button className="secondary-button" type="button" disabled={locked || loading || editing} onClick={() => { setHistoryOpen(!historyOpen); if (!historyOpen) void readSnapshot(); }}>확인 이력</button>
        {!editing ? <button className="secondary-button" type="button" disabled={locked || loading} onClick={() => { setEditing(true); setNotice(""); void readSnapshot(true); }}>상태 확인·변경</button> : null}
      </div>
    </div>
    <dl className={styles.facts}>
      <div><dt>개발 단계</dt><dd>{projectStatusLabels[project.status]}</dd></div>
      <div><dt>서비스 상태</dt><dd>{serviceStatusLabels[project.service_status ?? "unknown"]}</dd></div>
      <div><dt>실제 개발 종료일</dt><dd>{project.development_ended_on ?? "미확인"}</dd></div>
      <div><dt>마지막 사용자 확인</dt><dd>{project.lifecycle_confirmed_at ? new Date(project.lifecycle_confirmed_at).toLocaleString("ko-KR") : "확인 기록 없음"}</dd></div>
    </dl>
    {notice ? <p role="status" className={styles.success}>{notice}</p> : null}
    {loading ? <p role="status">상태 이력 조회 중...</p> : null}
    {error ? <div role="alert" className={styles.error}>{error}</div> : null}
    {error && !pending ? <button className="secondary-button" type="button" disabled={loading} onClick={() => void readSnapshot(conflict || !snapshot)}>최신 상태 다시 확인</button> : null}
    {pending && !saving ? <button className="primary-button" type="button" onClick={() => void save()}>동일 요청 다시 확인</button> : null}
    {editing ? <form onSubmit={(event) => void save(event)}>
      <fieldset disabled={locked || loading || conflict || !snapshot} className={styles.form}>
        <legend>상태 확인</legend>
        <div className={styles.fields}>
          <label>개발 단계<select aria-label="개발 단계" value={status} onChange={(event) => setStatus(event.target.value as ProjectStatus)}>{Object.entries(projectStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>서비스 상태<select aria-label="서비스 상태" value={service} onChange={(event) => setService(event.target.value as ServiceStatus)}>{Object.entries(serviceStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {status === "done" ? <label>실제 개발 종료일 (미확인 시 비움)<input type="date" value={endedOn} onChange={(event) => setEndedOn(event.target.value)} /></label> : null}
        </div>
        {snapshot ? <span className={styles.muted}>미완료 WBS {snapshot.pending_task_count}개</span> : null}
        <label>확인·변경 사유<textarea required maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
        {status === "done" && (snapshot?.pending_task_count ?? 0) > 0 ? <label>미완료 업무 처리 사유<textarea required maxLength={2000} value={incompleteReason} onChange={(event) => setIncompleteReason(event.target.value)} /></label> : null}
        <div className={styles.actions}>
          <button className="primary-button" type="submit" disabled={!reason.trim() || (status === "done" && (snapshot?.pending_task_count ?? 0) > 0 && !incompleteReason.trim())}>{saving ? "저장 중..." : "상태 확인 저장"}</button>
          <button className="secondary-button" type="button" onClick={() => setEditing(false)}>접기</button>
        </div>
      </fieldset>
    </form> : null}
    {historyOpen && snapshot ? <div className={styles.history}>
      <h3>최근 확인 {snapshot.history.length}건</h3>
      {snapshot.history.length === 0 ? <p className={styles.muted}>확인 이력이 없습니다.</p> : null}
      {snapshot.history.map((entry) => <article key={entry.id}>
        <strong>{projectStatusLabels[entry.previous_status]} → {projectStatusLabels[entry.status]} · {serviceStatusLabels[entry.previous_service_status]} → {serviceStatusLabels[entry.service_status]}</strong>
        <small>{new Date(entry.confirmed_at).toLocaleString("ko-KR")} · {entry.actor_owner_id}</small>
        <p>{entry.reason}</p>
        {entry.incomplete_reason ? <p>미완료 업무: {entry.incomplete_reason}</p> : null}
        <small>실제 개발 종료일: {entry.development_ended_on ?? "미확인"}</small>
      </article>)}
    </div> : null}
  </section>;
}
