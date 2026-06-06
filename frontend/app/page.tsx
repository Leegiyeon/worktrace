"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { ProjectSummary, ProjectTask, TaskStatus, WorkLogItem, WorkType } from "./projects/types";
import { projectStatusLabels, taskPriorityLabels, taskStatusLabels, workTypeLabels } from "./projects/types";
import { parseApiErrorMessage } from "./reports/api-error";

const taskStatusOrder: TaskStatus[] = ["planned", "in_progress", "done", "on_hold"];
const activeStatuses = new Set(["idea", "review", "in_progress"]);

type QuickCaptureForm = {
  project_id: string;
  log_date: string;
  work_type: WorkType;
  title: string;
  content: string;
  decisions: string;
  collaborators: string;
  next_actions: string;
  blockers: string;
  duration_minutes: string;
};

type WorkLogDraftResponse = {
  title: string;
  work_type: WorkType;
  content: string;
  decisions: string;
  collaborators: string;
  next_actions: string;
  blockers: string;
  duration_minutes: number;
  confidence: number;
};

function getWeekStart() {
  const today = new Date();
  const day = today.getDay();
  const daysFromMonday = day === 0 ? 6 : day - 1;
  today.setHours(0, 0, 0, 0);
  today.setDate(today.getDate() - daysFromMonday);
  return today;
}

function formatDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function createInitialQuickCaptureForm(): QuickCaptureForm {
  return {
    project_id: "",
    log_date: formatDateKey(new Date()),
    work_type: "other",
    title: "",
    content: "",
    decisions: "",
    collaborators: "",
    next_actions: "",
    blockers: "",
    duration_minutes: "0"
  };
}


function isDelayed(task: ProjectTask) {
  if (!task.due_date || task.status === "done") return false;
  return new Date(`${task.due_date}T23:59:59`) < new Date();
}

function isCompletedThisWeek(task: ProjectTask, weekStart: Date) {
  if (task.status !== "done") return false;
  return new Date(task.updated_at) >= weekStart;
}

type ProjectTaskBundle = {
  project: ProjectSummary;
  tasks: ProjectTask[];
};

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectTasks, setProjectTasks] = useState<Record<string, ProjectTask[]>>({});
  const [recentWorkLogs, setRecentWorkLogs] = useState<WorkLogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [quickCaptureForm, setQuickCaptureForm] = useState<QuickCaptureForm>(() => createInitialQuickCaptureForm());
  const [isSavingQuickCapture, setIsSavingQuickCapture] = useState(false);
  const [isDraftingQuickCapture, setIsDraftingQuickCapture] = useState(false);
  const [quickCaptureMessage, setQuickCaptureMessage] = useState("");
  const [aiMemoText, setAiMemoText] = useState("");
  const [draftConfidence, setDraftConfidence] = useState<number | null>(null);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const [projectResponse, logsResponse] = await Promise.all([
        fetch("/api/projects", { cache: "no-store" }),
        fetch("/api/work-logs", { cache: "no-store" })
      ]);
      if (!projectResponse.ok) {
        const detail = await projectResponse.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      const nextProjects = (await projectResponse.json()) as ProjectSummary[];
      setProjects(nextProjects);
      setRecentWorkLogs(logsResponse.ok ? ((await logsResponse.json()) as WorkLogItem[]) : []);

      const taskEntries = await Promise.all(
        nextProjects.map(async (project) => {
          const response = await fetch(`/api/projects/${project.id}/tasks`, { cache: "no-store" });
          if (!response.ok) return [project.id, []] as const;
          return [project.id, (await response.json()) as ProjectTask[]] as const;
        })
      );
      setProjectTasks(Object.fromEntries(taskEntries));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "대시보드 데이터를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const dashboard = useMemo(() => {
    const taskBundles: ProjectTaskBundle[] = projects.map((project) => ({
      project,
      tasks: projectTasks[project.id] ?? []
    }));
    const allTasks = taskBundles.flatMap(({ project, tasks }) => tasks.map((task) => ({ ...task, project_title: project.title })));
    const weekStart = getWeekStart();
    const activeProjects = projects.filter((project) => activeStatuses.has(project.status));
    const remainingTasks = projects.reduce((sum, project) => sum + project.remaining_tasks, 0);
    const averageProgress = projects.length
      ? Math.round(projects.reduce((sum, project) => sum + project.progress_percent, 0) / projects.length)
      : 0;
    const delayedTasks = allTasks.filter(isDelayed).sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"));
    const completedThisWeek = allTasks
      .filter((task) => isCompletedThisWeek(task, weekStart))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    const weeklyLogs = recentWorkLogs.filter((log) => new Date(`${log.log_date}T00:00:00`) >= weekStart);
    const taskStatusCounts = taskStatusOrder.map((status) => ({
      status,
      label: taskStatusLabels[status],
      count: allTasks.filter((task) => task.status === status).length
    }));
    const maxStatusCount = Math.max(1, ...taskStatusCounts.map((item) => item.count));

    return {
      activeProjects,
      averageProgress,
      completedThisWeek,
      delayedTasks,
      maxStatusCount,
      remainingTasks,
      weeklyLogs,
      taskStatusCounts,
      totalTasks: allTasks.length
    };
  }, [projectTasks, projects, recentWorkLogs]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDashboard();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDashboard]);

  async function handleQuickCaptureSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quickCaptureForm.title.trim()) {
      setQuickCaptureMessage("");
      setErrorMessage("빠른 기록 제목을 입력하세요.");
      return;
    }
    if (!quickCaptureForm.log_date) {
      setQuickCaptureMessage("");
      setErrorMessage("빠른 기록 수행일을 선택하세요.");
      return;
    }

    const durationMinutes = Number.parseInt(quickCaptureForm.duration_minutes || "0", 10);
    const payload = {
      project_id: quickCaptureForm.project_id || null,
      log_date: quickCaptureForm.log_date,
      work_type: quickCaptureForm.work_type,
      title: quickCaptureForm.title.trim(),
      content: quickCaptureForm.content.trim(),
      decisions: quickCaptureForm.decisions.trim(),
      collaborators: quickCaptureForm.collaborators.trim(),
      next_actions: quickCaptureForm.next_actions.trim(),
      blockers: quickCaptureForm.blockers.trim(),
      duration_minutes: Number.isFinite(durationMinutes) && durationMinutes > 0 ? durationMinutes : 0
    };

    setIsSavingQuickCapture(true);
    setErrorMessage("");
    setQuickCaptureMessage("");
    try {
      const response = await fetch("/api/work-logs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "빠른 기록을 저장하지 못했습니다."));
      }
      setQuickCaptureForm(createInitialQuickCaptureForm());
      setAiMemoText("");
      setDraftConfidence(null);
      setQuickCaptureMessage("업무 로그 저장 완료");
      await loadDashboard();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "빠른 기록을 저장하지 못했습니다.");
    } finally {
      setIsSavingQuickCapture(false);
    }
  }

  async function handleQuickCaptureDraft() {
    if (!aiMemoText.trim()) {
      setQuickCaptureMessage("");
      setErrorMessage("정리할 업무 메모를 입력하세요.");
      return;
    }

    setIsDraftingQuickCapture(true);
    setErrorMessage("");
    setQuickCaptureMessage("");
    try {
      const response = await fetch("/api/ai/work-log-draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: aiMemoText.trim(),
          project_id: quickCaptureForm.project_id || null
        })
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "AI 초안을 생성하지 못했습니다."));
      }
      const draft = (await response.json()) as WorkLogDraftResponse;
      setQuickCaptureForm({
        ...quickCaptureForm,
        title: draft.title,
        work_type: draft.work_type,
        content: draft.content,
        decisions: draft.decisions,
        collaborators: draft.collaborators,
        next_actions: draft.next_actions,
        blockers: draft.blockers,
        duration_minutes: String(draft.duration_minutes)
      });
      setDraftConfidence(draft.confidence);
      setQuickCaptureMessage("AI 초안 생성 완료 · 검토 후 저장");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "AI 초안을 생성하지 못했습니다.");
    } finally {
      setIsDraftingQuickCapture(false);
    }
  }

  return (
    <main className="page-shell dashboard-page">
      <header className="dashboard-topbar">
        <div>
          <span className="section-kicker">Dashboard</span>
          <h1>대시보드</h1>
          <p className="page-subtitle">프로젝트 진척, 지연 업무, 업무 기록을 한 화면에서 관리합니다.</p>
        </div>
        <nav className="hero-actions" aria-label="주요 이동">
          <Link className="primary-link" href="/projects">프로젝트 보기</Link>
          <Link className="secondary-button" href="/reports">리포트 생성</Link>
        </nav>
      </header>

      {errorMessage ? <div className="alert error">{errorMessage}</div> : null}
      {quickCaptureMessage ? <div className="alert success">{quickCaptureMessage}</div> : null}

      <section className="summary-grid dashboard-metrics" aria-label="핵심 지표">
        <div className="metric-card"><span>진행 프로젝트</span><strong>{dashboard.activeProjects.length}</strong></div>
        <div className="metric-card"><span>잔여 업무</span><strong>{dashboard.remainingTasks}</strong></div>
        <div className="metric-card"><span>지연 업무</span><strong>{dashboard.delayedTasks.length}</strong></div>
        <div className="metric-card"><span>이번 주 로그</span><strong>{dashboard.weeklyLogs.length}</strong></div>
      </section>

      <section className="dashboard-grid" aria-label="프로젝트 관리 대시보드">
        <section className="panel dashboard-main-panel">
          <div className="panel-title-row">
            <h2>프로젝트 진행률</h2>
            <span className="count-badge">{projects.length}개</span>
          </div>
          {isLoading ? <div className="empty-state">로딩 중</div> : null}
          {!isLoading && projects.length === 0 ? (
            <div className="empty-state"><span>프로젝트 없음</span><Link className="primary-link" href="/projects">추가</Link></div>
          ) : null}
          <div className="progress-chart-list">
            {projects.slice(0, 5).map((project) => (
              <Link className="progress-row" href={`/projects/${project.id}`} key={project.id}>
                <div className="progress-row-head">
                  <strong>{project.title}</strong>
                  <span className="meta-pill status-navy">{projectStatusLabels[project.status]}</span>
                  <span className="meta-pill">잔여 {project.remaining_tasks}</span>
                  <span className="meta-pill">{project.completed_tasks}/{project.total_tasks}</span>
                </div>
                <div className="progress-row-bar" aria-label={`${project.title} 진행률 ${project.progress_percent}%`}>
                  <span style={{ width: `${project.progress_percent}%` }} />
                </div>
                <b>{project.progress_percent}%</b>
              </Link>
            ))}
          </div>
        </section>

        <section className="panel quick-capture-panel">
          <div className="panel-title-row">
            <h2>빠른 기록</h2>
            <span className="meta-pill">{draftConfidence === null ? "업무 로그" : `신뢰도 ${Math.round(draftConfidence * 100)}%`}</span>
          </div>
          <div className="quick-ai-draft">
            <label>메모
              <textarea
                placeholder="자연어 업무 메모"
                value={aiMemoText}
                onChange={(event) => setAiMemoText(event.target.value)}
              />
            </label>
            <button className="secondary-button" type="button" onClick={() => void handleQuickCaptureDraft()} disabled={isDraftingQuickCapture}>
              {isDraftingQuickCapture ? "정리 중" : "AI로 정리"}
            </button>
          </div>
          <form className="stacked-form compact-form quick-capture-form" onSubmit={handleQuickCaptureSubmit}>
            <div className="form-grid two-columns">
              <label>프로젝트
                <select
                  value={quickCaptureForm.project_id}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, project_id: event.target.value })}
                >
                  <option value="">미지정</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>{project.title}</option>
                  ))}
                </select>
              </label>
              <label>수행일
                <input
                  required
                  type="date"
                  value={quickCaptureForm.log_date}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, log_date: event.target.value })}
                />
              </label>
            </div>
            <div className="form-grid two-columns">
              <label>유형
                <select
                  value={quickCaptureForm.work_type}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, work_type: event.target.value as WorkType })}
                >
                  {Object.entries(workTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label>소요(분)
                <input
                  min="0"
                  type="number"
                  value={quickCaptureForm.duration_minutes}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, duration_minutes: event.target.value })}
                />
              </label>
            </div>
            <label>제목
              <input
                placeholder="예: 주간 현황 정리"
                value={quickCaptureForm.title}
                onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, title: event.target.value })}
              />
            </label>
            <div className="form-grid two-columns">
              <label>수행 내용
                <textarea
                  placeholder="실제로 한 일"
                  value={quickCaptureForm.content}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, content: event.target.value })}
                />
              </label>
              <label>다음 액션
                <textarea
                  placeholder="다음에 할 일"
                  value={quickCaptureForm.next_actions}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, next_actions: event.target.value })}
                />
              </label>
            </div>
            <div className="form-grid three-columns">
              <label>결정
                <textarea
                  placeholder="결정사항"
                  value={quickCaptureForm.decisions}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, decisions: event.target.value })}
                />
              </label>
              <label>협업자
                <input
                  placeholder="이름/팀"
                  value={quickCaptureForm.collaborators}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, collaborators: event.target.value })}
                />
              </label>
              <label>블로커
                <textarea
                  placeholder="막힌 점"
                  value={quickCaptureForm.blockers}
                  onChange={(event) => setQuickCaptureForm({ ...quickCaptureForm, blockers: event.target.value })}
                />
              </label>
            </div>
            <div className="form-actions">
              <button type="submit" disabled={isSavingQuickCapture}>{isSavingQuickCapture ? "저장 중" : "기록 저장"}</button>
            </div>
          </form>
        </section>

        <section className="panel status-graph-panel">
          <div className="panel-title-row">
            <h2>상태별 업무</h2>
            <span className="count-badge">{dashboard.totalTasks}개</span>
          </div>
          <div className="status-bars">
            {dashboard.taskStatusCounts.map((item) => (
              <div className="status-bar-row" key={item.status}>
                <span>{item.label}</span>
                <div className="status-bar-track"><i style={{ width: `${(item.count / dashboard.maxStatusCount) * 100}%` }} /></div>
                <strong>{item.count}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="panel recent-panel">
          <div className="panel-title-row">
            <h2>최근 로그</h2>
            <span className="count-badge">{recentWorkLogs.length}개</span>
          </div>
          {recentWorkLogs.length === 0 ? <div className="empty-state">로그 없음</div> : null}
          <div className="dense-list">
            {recentWorkLogs.slice(0, 7).map((log) => (
              <Link className="dense-list-row" href={log.project_id ? `/projects/${log.project_id}` : "/projects"} key={log.id}>
                <span>{log.title}</span>
                <small>{log.project_title || "미지정"} · {workTypeLabels[log.work_type]}</small>
                <b>{log.log_date}</b>
              </Link>
            ))}
          </div>
        </section>

        <section className="panel delayed-panel">
          <div className="panel-title-row">
            <h2>지연 업무</h2>
            <span className="count-badge danger-count">{dashboard.delayedTasks.length}개</span>
          </div>
          {dashboard.delayedTasks.length === 0 ? <div className="empty-state">지연 없음</div> : null}
          <div className="dense-list">
            {dashboard.delayedTasks.slice(0, 6).map((task) => (
              <Link className="dense-list-row" href={`/projects/${task.project_id}`} key={task.id}>
                <span>{task.title}</span>
                <small>{task.project_title}</small>
                <b>{task.due_date}</b>
              </Link>
            ))}
          </div>
        </section>

        <section className="panel completed-panel">
          <div className="panel-title-row">
            <h2>이번 주 완료</h2>
            <span className="count-badge">{dashboard.completedThisWeek.length}개</span>
          </div>
          {dashboard.completedThisWeek.length === 0 ? <div className="empty-state">완료 업무 없음</div> : null}
          <div className="data-table-wrap">
            {dashboard.completedThisWeek.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>업무</th>
                    <th>프로젝트</th>
                    <th>우선순위</th>
                    <th>완료일</th>
                  </tr>
                </thead>
                <tbody>
                  {dashboard.completedThisWeek.slice(0, 8).map((task) => (
                    <tr key={task.id}>
                      <td>{task.title}</td>
                      <td>{task.project_title}</td>
                      <td><span className={`meta-pill priority-${task.priority}`}>{taskPriorityLabels[task.priority]}</span></td>
                      <td>{task.updated_at.slice(0, 10)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </section>
      </section>
    </main>
  );
}
