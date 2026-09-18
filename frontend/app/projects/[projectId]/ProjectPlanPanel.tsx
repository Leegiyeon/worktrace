"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parseApiErrorMessage } from "../../reports/api-error";
import type { ProgressPlanPolicy, ProjectPlanSnapshot } from "../types";
import styles from "./ProjectPlanPanel.module.css";

type ApprovalPayload = {
  policy: ProgressPlanPolicy;
  reason: string;
  exclusion_reason: string;
  reviewed_derived: boolean;
  expected_version: number;
  expected_context_fingerprint: string;
  request_id: string;
};

const policyLabels: Record<ProgressPlanPolicy, string> = {
  wbs: "WBS 완료 비율",
  milestone: "마일스톤 가중치"
};

const statusLabels: Record<ProjectPlanSnapshot["status"], string> = {
  unapproved: "미승인",
  approved: "승인됨",
  stale: "재승인 필요"
};

function makeRequestId() {
  const browserCrypto = globalThis.crypto;
  if (browserCrypto.randomUUID) return browserCrypto.randomUUID();
  const bytes = new Uint8Array(16);
  browserCrypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

function sourceLabel(provider: string | null, key: string | null) {
  if (!provider) return "수동 WBS";
  if (provider === "github") return key ? `GitHub 근거 ${key}` : "GitHub 근거";
  if (provider === "derived-github") return "자동 구성 WBS";
  return key ? `${provider} 근거` : provider;
}

export function ProjectPlanPanel({ projectId, onApproved }: { projectId: string; onApproved: () => void | Promise<void> }) {
  const [snapshot, setSnapshot] = useState<ProjectPlanSnapshot | null>(null);
  const [policy, setPolicy] = useState<ProgressPlanPolicy>("wbs");
  const [reason, setReason] = useState("");
  const [exclusionReason, setExclusionReason] = useState("");
  const [reviewedDerived, setReviewedDerived] = useState(false);
  const [pending, setPending] = useState<ApprovalPayload | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const live = useRef(true);
  const busy = useRef(false);
  const sequence = useRef(0);
  const fingerprintRef = useRef<string | null>(null);
  const onApprovedRef = useRef(onApproved);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/plan`;
  const reasonId = `plan-reason-${projectId}`;
  const exclusionReasonId = `plan-exclusion-reason-${projectId}`;

  const countedTasks = useMemo(() => snapshot?.tasks.filter((task) => task.counts_toward_progress) ?? [], [snapshot]);
  const excludedTasks = snapshot?.excluded_tasks ?? [];
  const serverPolicyErrors = snapshot?.policy_errors[policy] ?? [];
  const locked = saving || pending !== null;
  const milestoneTitleById = useMemo(() => new Map((snapshot?.milestones ?? []).map((milestone) => [milestone.id, milestone.title])), [snapshot]);

  useEffect(() => {
    onApprovedRef.current = onApproved;
  }, [onApproved]);

  const readPlan = useCallback(async (preserveDraft = true, clearFrozenOnSuccess = false) => {
    if (busy.current) return;
    busy.current = true;
    const request = ++sequence.current;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "진행 계획을 불러오지 못했습니다."));
      const data = await response.json() as ProjectPlanSnapshot;
      if (!live.current || request !== sequence.current) return;
      const scopeChanged = fingerprintRef.current !== null && fingerprintRef.current !== data.context_fingerprint;
      fingerprintRef.current = data.context_fingerprint;
      setSnapshot(data);
      setPolicy((current) => preserveDraft ? current : data.status === "approved" ? data.policy : "wbs");
      if (!preserveDraft) { setReason(""); setExclusionReason(""); setReviewedDerived(false); }
      else if (scopeChanged) setReviewedDerived(false);
      if (clearFrozenOnSuccess) setPending(null);
      setConflict(false);
      setNotice("");
      if (clearFrozenOnSuccess) {
        try {
          await onApprovedRef.current();
        } catch {
          if (live.current && request === sequence.current) setNotice("진행 계획은 다시 불러왔지만 WBS 현황을 갱신하지 못했습니다.");
        }
      }
    } catch (failure) {
      if (live.current && request === sequence.current) setError(failure instanceof Error ? failure.message : "진행 계획 조회 실패");
    } finally {
      if (request === sequence.current) busy.current = false;
      if (live.current && request === sequence.current) setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    live.current = true;
    sequence.current += 1;
    const timer = window.setTimeout(() => { void readPlan(false); }, 0);
    return () => { live.current = false; window.clearTimeout(timer); };
  }, [readPlan]);

  async function save(event?: FormEvent) {
    event?.preventDefault();
    if (!snapshot || busy.current || conflict) return;
    if (!reason.trim() && !pending) { setError("승인 사유를 입력하세요."); return; }
    if (excludedTasks.length > 0 && !exclusionReason.trim() && !pending) { setError("제외 업무가 있으면 제외 사유를 입력하세요."); return; }
    if (snapshot.derived_task_count > 0 && !reviewedDerived && !pending) { setError("자동 구성 WBS 확인을 체크하세요."); return; }

    const body = pending ?? {
      policy,
      reason: reason.trim(),
      exclusion_reason: excludedTasks.length > 0 ? exclusionReason.trim() : "",
      reviewed_derived: reviewedDerived,
      expected_version: snapshot.version,
      expected_context_fingerprint: snapshot.context_fingerprint,
      request_id: makeRequestId()
    };

    busy.current = true;
    sequence.current += 1;
    setSaving(true); setPending(body); setError(""); setNotice("");
    try {
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!live.current) return;
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        if (response.status === 409) setConflict(true);
        else if (response.status >= 400 && response.status < 500 && ![408, 429].includes(response.status)) setPending(null);
        throw new Error(parseApiErrorMessage(detail, response.status === 409 ? "진행 계획이 변경되었습니다. 최신 계획을 다시 확인하세요." : "진행 계획 승인을 저장하지 못했습니다."));
      }
      const data = await response.json().catch(() => null) as ProjectPlanSnapshot | null;
      if (!data) throw new Error("저장 응답을 확인하지 못했습니다. 동일 요청으로 다시 확인하세요.");
      if (!live.current) return;
      fingerprintRef.current = data.context_fingerprint;
      setSnapshot(data); setPending(null); setConflict(false); setReason(""); setExclusionReason(""); setReviewedDerived(false);
      try {
        await onApprovedRef.current();
        if (live.current) setNotice("진행 계획을 승인했습니다.");
      } catch {
        if (live.current) setNotice("승인은 저장됐지만 WBS 현황을 갱신하지 못했습니다. 새로고침으로 최신 수치를 확인하세요.");
      }
    } catch (failure) {
      if (live.current) setError(failure instanceof Error ? failure.message : "저장 결과를 확인하지 못했습니다.");
    } finally {
      busy.current = false;
      if (live.current) setSaving(false);
    }
  }

  return <section className={`panel ${styles.panel}`} aria-label="진행 계획 승인">
    <div className={styles.heading}>
      <h2>진행 계획</h2>
      <div className={styles.actions}>
        <span className="count-badge">{snapshot ? statusLabels[snapshot.status] : "조회 중"}</span>
        <button className="secondary-button" type="button" disabled={locked || loading} onClick={() => { setHistoryOpen(!historyOpen); if (!historyOpen && !snapshot) void readPlan(); }}>승인 이력</button>
      </div>
    </div>
    {loading ? <p role="status" className={styles.muted}>진행 계획 조회 중...</p> : null}
    {error ? <div role="alert" className={styles.error}>{error}</div> : null}
    {notice ? <p role="status" className={styles.success}>{notice}</p> : null}
    {pending && !saving ? <p className={styles.warning}>저장 결과가 확정되지 않았습니다. 같은 요청으로 재시도하거나 최신 계획을 다시 불러오세요.</p> : null}
    <div className={styles.actions}>
      {pending && !saving && !conflict ? <button className="primary-button" type="button" onClick={() => void save()}>동일 요청 다시 확인</button> : null}
      <button className="secondary-button" type="button" disabled={loading || saving} onClick={() => void readPlan(true, true)}>최신 계획 다시 불러오기</button>
    </div>
    {snapshot ? <>
      <dl className={styles.facts}>
        <div><dt>버전</dt><dd>v{snapshot.version}</dd></div>
        <div><dt>산정 정책</dt><dd>{policyLabels[snapshot.policy]}</dd></div>
        <div><dt>WBS</dt><dd>산정 {snapshot.total_tasks} / 전체 {snapshot.tasks.length}</dd></div>
      </dl>
      {serverPolicyErrors.length > 0 ? <div role="alert" className={styles.error}>{serverPolicyErrors.map((item) => <div key={item}>{item}</div>)}</div> : null}
      <details className={styles.reviewDetails}>
        <summary>계획 검토·승인</summary>
        <div className={styles.reviewBody}>
          <div className={styles.previewGrid}>
            <div className="panel-title-row"><h3>승인 미리보기</h3><span className="count-badge">제외 {excludedTasks.length}개</span></div>
            <div className={styles.previewList} aria-label="산정 WBS 미리보기">
              {countedTasks.length === 0 ? <p className={styles.muted}>산정 WBS가 없습니다.</p> : null}
              {countedTasks.map((task) => <article key={task.id}>
                <strong>{task.title}</strong>
                <small>{task.milestone_id ? (task.milestone_title ?? milestoneTitleById.get(task.milestone_id) ?? "마일스톤 제목 미확인") : "마일스톤 미배정"} · {sourceLabel(task.source_provider, task.source_key)}</small>
              </article>)}
            </div>
            {excludedTasks.length > 0 ? <div className={styles.previewList} aria-label="제외 업무 미리보기">
              {excludedTasks.map((task) => <article key={task.id}><strong>{task.title}</strong><small>진척 산정 제외</small></article>)}
            </div> : null}
            <dl className={styles.milestoneList} aria-label="마일스톤 가중치">
              {snapshot.milestones.length === 0 ? <div><dt>마일스톤</dt><dd>등록 없음</dd></div> : null}
              {snapshot.milestones.map((milestone) => <div key={milestone.id}><dt>{milestone.title}</dt><dd>{milestone.weight}%</dd></div>)}
            </dl>
          </div>
          <form onSubmit={(event) => void save(event)}>
            <fieldset className={styles.form} disabled={locked || loading || conflict}>
              <legend>계획 승인</legend>
              <label>산정 정책<select aria-label="산정 정책" value={policy} onChange={(event) => setPolicy(event.target.value as ProgressPlanPolicy)}><option value="wbs">WBS 완료 비율</option><option value="milestone">마일스톤 가중치</option></select></label>
              <div className={styles.field}><label htmlFor={reasonId}>승인 사유</label><textarea id={reasonId} required maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
              {excludedTasks.length > 0 ? <div className={styles.field}><label htmlFor={exclusionReasonId}>제외 사유</label><textarea id={exclusionReasonId} required maxLength={2000} value={exclusionReason} onChange={(event) => setExclusionReason(event.target.value)} /></div> : null}
              {snapshot.derived_task_count > 0 ? <label className={styles.check}><input type="checkbox" checked={reviewedDerived} onChange={(event) => setReviewedDerived(event.target.checked)} /><span>자동 구성 WBS {snapshot.derived_task_count}개를 검토했습니다.</span></label> : null}
              <div className={styles.actions}>
                <button className="primary-button" type="submit" disabled={!reason.trim() || (excludedTasks.length > 0 && !exclusionReason.trim()) || (snapshot.derived_task_count > 0 && !reviewedDerived) || serverPolicyErrors.length > 0}>{saving ? "저장 중..." : "진행 계획 승인"}</button>
              </div>
            </fieldset>
          </form>
        </div>
      </details>
      {historyOpen ? <div className={styles.history}>
        <div className={styles.historyHeader}><h3>최근 승인 이력</h3><span className="count-badge">{snapshot.history.slice(0, 20).length}건</span></div>
        {snapshot.history.length === 0 ? <p className={styles.muted}>승인 이력이 없습니다.</p> : null}
        {snapshot.history.slice(0, 20).map((entry) => <article key={entry.id}>
          <strong>v{entry.version} · {policyLabels[entry.policy]}</strong>
          <small>{formatDateTime(entry.approved_at)} · {entry.actor_owner_id} · 자동 구성 {entry.reviewed_derived ? "확인" : "없음"}</small>
          <p>{entry.reason}</p>
          {entry.exclusion_reason ? <p>제외 사유: {entry.exclusion_reason}</p> : null}
        </article>)}
      </div> : null}
    </> : null}
  </section>;
}
