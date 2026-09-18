"use client";

import { useEffect, useRef, useState } from "react";
import type { ProjectTask, TaskStatus } from "../types";
import { taskStatusLabels } from "../types";
import { completionDateLabel } from "../task-completion";
import { parseApiErrorMessage } from "../../reports/api-error";
import styles from "./TaskHistoryPanel.module.css";

type HistoryEntry = {
  id: string;
  previous_status: TaskStatus | null;
  status: TaskStatus;
  actor_owner_id: string | null;
  source: "user" | "milestone_validation" | "system";
  reason: string | null;
  changed_at: string;
  status_version: number;
};
type TaskHistory = { items: HistoryEntry[]; total: number };
const sourceLabels = { user: "사용자 변경", milestone_validation: "마일스톤 확인", system: "시스템 변경" };

export function TaskHistoryPanel({ task }: { task: ProjectTask }) {
  const [data, setData] = useState<TaskHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const live = useRef(true);
  const busy = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  async function load() {
    if (busy.current) return;
    busy.current = true; setLoading(true); setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(task.project_id)}/tasks/${encodeURIComponent(task.id)}/history`, { cache: "no-store" });
      if (!response.ok) throw new Error(parseApiErrorMessage(await response.json().catch(() => null), "업무 이력을 불러오지 못했습니다."));
      const next = await response.json() as TaskHistory;
      if (live.current) setData(next);
    } catch (failure) {
      if (live.current) setError(failure instanceof Error ? failure.message : "업무 이력 조회 실패");
    } finally {
      busy.current = false;
      if (live.current) setLoading(false);
    }
  }

  return <details className={styles.history} onToggle={(event) => { if (event.currentTarget.open && !data && !loading) void load(); }}>
    <summary>상태 변경 이력 · 완료 처리일 {task.status === "done" ? completionDateLabel(task.completed_at) : "해당 없음"}</summary>
    {loading ? <p role="status">업무 이력 조회 중...</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    <div className={styles.heading}><span>{data ? `최근 ${data.items.length}건 / 전체 ${data.total}건` : ""}</span><button type="button" className="secondary-button" disabled={loading} onClick={() => void load()}>{error ? "이력 다시 조회" : "이력 새로고침"}</button></div>
    {data?.items.length === 0 ? <p>기록된 상태 변경 없음</p> : null}
    {data?.items.map((entry) => <article key={entry.id}>
      <strong>{entry.previous_status === null ? "등록" : taskStatusLabels[entry.previous_status]} → {taskStatusLabels[entry.status]}</strong>
      <time dateTime={entry.changed_at}>{new Date(entry.changed_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)</time>
      <span>{sourceLabels[entry.source]} · {entry.actor_owner_id ?? "변경 주체 미확인"}</span>
      <p>{entry.reason || "사유 미기록"}</p>
    </article>)}
  </details>;
}
