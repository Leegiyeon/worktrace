import Link from "next/link";

import { outcomeTypeLabels, taskStatusLabels } from "../projects/types";
import type {
  ReportActivity as ReportActivityPayload,
  ReportActivityCurrentTask,
  ReportActivityIssue,
  ReportActivityOutcome,
  ReportActivityTransition
} from "./types";
import styles from "./ReportActivity.module.css";

const planStatusLabels: Record<ReportActivityCurrentTask["progress_plan_status"], string> = {
  unapproved: "계획 미승인",
  approved: "계획 승인",
  stale: "재승인 필요"
};

const sourceLabels: Record<ReportActivityTransition["source"], string> = {
  user: "사용자",
  system: "시스템",
  milestone_validation: "과거 자동 검증"
};

function shortId(value: string) {
  return value.length > 8 ? value.substring(0, 8) : value;
}

function EvidenceRef({ label, value }: { label: string; value: string }) {
  return <span title={value}>{label} {shortId(value)}</span>;
}

function EvidenceRefList({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return <span>{label} -</span>;
  return <span title={values.join(", ")}>{label} {values.map(shortId).join(", ")}</span>;
}

function taskStatusLabel(status: string) {
  return status in taskStatusLabels ? taskStatusLabels[status as keyof typeof taskStatusLabels] : status;
}

function outcomeTypeLabel(type: string) {
  return type in outcomeTypeLabels ? outcomeTypeLabels[type as keyof typeof outcomeTypeLabels] : type;
}

function isQuantitativeOutcome(outcome: ReportActivityOutcome) {
  return outcome.outcome_type === "quantitative";
}

function formatDateTime(value: string, timezone: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short", timeZone: timezone });
}

function ProjectLink({ projectId, tab }: { projectId: string | null; tab: "tasks" | "logs" | "outcomes" }) {
  if (!projectId) return null;
  return <Link className={styles.projectLink} href={`/projects/${projectId}?tab=${tab}`}>프로젝트 열기</Link>;
}

function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}

function ActivityMetadata({ activity }: { activity: ReportActivityPayload }) {
  return (
    <section className={`${styles.activityPanel} ${styles.fullSpan}`} aria-label="리포트 활동 메타데이터">
      <div className="panel-title-row">
        <h2>기간 활동 기준</h2>
        <span className="count-badge">스키마 {activity.schema_version}</span>
      </div>
      <div className={styles.metadata}>
        <span className="meta-pill">조회 {formatDateTime(activity.as_of, activity.timezone)}</span>
        <span className="meta-pill">시간대 {activity.timezone}</span>
        <span className="meta-pill">이벤트 기간 {formatDateTime(activity.start_at, activity.timezone)} - 종료 미포함 {formatDateTime(activity.end_exclusive, activity.timezone)}</span>
        <details className={styles.fingerprint} title={activity.fingerprint}>
          <summary>내용해시 <code>{shortId(activity.fingerprint)}</code></summary>
          <code>{activity.fingerprint}</code>
        </details>
      </div>
    </section>
  );
}

function TransitionList({ transitions, timezone }: { transitions: ReportActivityTransition[]; timezone: string }) {
  return (
    <section className={styles.activityPanel}>
      <div className="panel-title-row">
        <h2>기간 내 상태 변경</h2>
        <span className="count-badge">{transitions.length}개</span>
      </div>
      {transitions.length === 0 ? <EmptyState label="상태 변경 없음" /> : null}
      <div className={styles.scrollList}>
        {transitions.map((item) => (
          <article className={styles.record} key={item.id}>
            <div className={styles.recordHeader}>
              <div className={styles.recordTitle}>
                <strong>{item.task_title}</strong>
                <span className={styles.metaLine}>{item.project_title} · {formatDateTime(item.changed_at, timezone)}</span>
              </div>
              <ProjectLink projectId={item.project_id} tab="tasks" />
            </div>
            <div className={styles.pillRow}>
              <span className="meta-pill">{item.previous_status ? taskStatusLabel(item.previous_status) : "이전 없음"} -&gt; <span className={styles.statusLabel}>{taskStatusLabel(item.next_status)}</span></span>
              <span className="meta-pill">현재 {taskStatusLabel(item.current_status)}</span>
              <span className="meta-pill">{sourceLabels[item.source]}</span>
              <span className="meta-pill">v{item.status_version}</span>
            </div>
            {item.reason ? <span className={styles.metaLine}>사유: {item.reason}</span> : null}
            <div className={styles.refs}>
              <EvidenceRef label="상태근거" value={item.id} />
              <EvidenceRef label="WBS" value={item.task_id} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function CurrentTaskList({ tasks }: { tasks: ReportActivityCurrentTask[] }) {
  return (
    <section className={styles.activityPanel}>
      <div className="panel-title-row">
        <h2>현재 잔여 WBS</h2>
        <span className="count-badge">{tasks.length}개</span>
      </div>
      {tasks.length === 0 ? <EmptyState label="잔여 WBS 없음" /> : null}
      <div className={styles.scrollList}>
        {tasks.map((task) => (
          <article className={styles.record} key={task.id}>
            <div className={styles.recordHeader}>
              <div className={styles.recordTitle}>
                <strong>{task.title}</strong>
                <span className={styles.metaLine}>{task.project_title}</span>
              </div>
              <ProjectLink projectId={task.project_id} tab="tasks" />
            </div>
            <div className={styles.pillRow}>
              <span className="meta-pill">{taskStatusLabel(task.status)}</span>
              <span className="meta-pill">{planStatusLabels[task.progress_plan_status]} v{task.progress_plan_version}</span>
              <span className="meta-pill">마감 {task.due_date ?? "미정"}</span>
              {task.source_provider ? <span className="meta-pill">출처 {task.source_provider}</span> : null}
            </div>
            <div className={styles.refs}><EvidenceRef label="WBS" value={task.id} /></div>
          </article>
        ))}
      </div>
    </section>
  );
}

function IssueList({ issues, timezone }: { issues: ReportActivityIssue[]; timezone: string }) {
  return (
    <section className={styles.activityPanel}>
      <div className="panel-title-row">
        <h2>기록된 막힘</h2>
        <span className="count-badge danger-count">{issues.length}개</span>
      </div>
      {issues.length === 0 ? <EmptyState label="기록된 막힘 없음" /> : null}
      <div className={styles.scrollList}>
        {issues.map((issue) => (
          <article className={styles.record} key={issue.id}>
            <div className={styles.recordHeader}>
              <div className={styles.recordTitle}>
                <strong>{issue.title}</strong>
                <span className={styles.metaLine}>{issue.project_title || "프로젝트 미연결"} · 수행일 {issue.log_date}</span>
              </div>
              <ProjectLink projectId={issue.project_id} tab="logs" />
            </div>
            <span>{issue.blockers}</span>
            <div className={styles.refs}>
              <EvidenceRef label="업무로그" value={issue.id} />
              <span>수정 {formatDateTime(issue.updated_at, timezone)}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function OutcomeList({ outcomes, timezone }: { outcomes: ReportActivityOutcome[]; timezone: string }) {
  return (
    <section className={styles.activityPanel}>
      <div className="panel-title-row">
        <h2>기간 내 수정된 확인 성과</h2>
        <span className="count-badge">{outcomes.length}개</span>
      </div>
      {outcomes.length === 0 ? <EmptyState label="수정된 확인 성과 없음" /> : null}
      <div className={styles.scrollList}>
        {outcomes.map((outcome) => (
          <article className={styles.record} key={outcome.id}>
            <div className={styles.recordHeader}>
              <div className={styles.recordTitle}>
                <strong>{outcome.title}</strong>
                <span className={styles.metaLine}>{outcome.project_title} · 수정 {formatDateTime(outcome.updated_at, timezone)}</span>
              </div>
              <ProjectLink projectId={outcome.project_id} tab="outcomes" />
            </div>
            <div className={styles.pillRow}>
              <span className="meta-pill">{outcomeTypeLabel(outcome.outcome_type)}</span>
              {isQuantitativeOutcome(outcome) ? <span className="meta-pill">{outcome.metric_name || "지표 없음"} {outcome.metric_value ?? "-"} {outcome.metric_unit}</span> : null}
            </div>
            <details className={styles.details}>
              <summary>상태와 근거</summary>
              <p className={styles.metaLine}>이전: {outcome.before_state || "-"}</p>
              <p className={styles.metaLine}>이후: {outcome.after_state || "-"}</p>
              <div className={styles.refs}>
                <EvidenceRef label="성과근거" value={outcome.id} />
                <EvidenceRefList label="로그근거" values={outcome.evidence_work_log_ids} />
                <EvidenceRefList label="문서근거" values={outcome.evidence_document_ids} />
              </div>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function ReportActivity({ activity }: { activity: ReportActivityPayload }) {
  return (
    <section className={styles.activityGrid} aria-label="기간 실제 활동 기록">
      <ActivityMetadata activity={activity} />
      <TransitionList transitions={activity.transitions} timezone={activity.timezone} />
      <CurrentTaskList tasks={activity.current_tasks} />
      <IssueList issues={activity.issues} timezone={activity.timezone} />
      <OutcomeList outcomes={activity.outcomes} timezone={activity.timezone} />
    </section>
  );
}
