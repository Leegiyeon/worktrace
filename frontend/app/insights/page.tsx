"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { ProjectSummary, ProjectTask } from "../projects/types";
import { projectProgressDisplay } from "../projects/progress-display";

type AnalystAction = {
  task_id: string;
  reason: string;
};

type AnalystResult = {
  summary: string;
  next_actions: AnalystAction[];
  blockers: string[];
  needs_attention: string[];
  confidence: number;
  remaining_wbs_count: number;
  evidence_commit_count: number;
};

function basisLabel(project: ProjectSummary) {
  return projectProgressDisplay(project).basisLabel;
}

function progressLabel(project: ProjectSummary) {
  return projectProgressDisplay(project).label;
}

export default function InsightsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [result, setResult] = useState<AnalystResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/projects", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
        return (await response.json()) as ProjectSummary[];
      })
      .then((items) => {
        if (cancelled) return;
        setProjects(items);
        setSelectedProjectId(items[0]?.id ?? "");
      })
      .catch((error: unknown) => {
        if (!cancelled) setErrorMessage(error instanceof Error ? error.message : "프로젝트를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    let cancelled = false;
    fetch(`/api/projects/${selectedProjectId}/tasks`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("WBS를 불러오지 못했습니다.");
        return (await response.json()) as ProjectTask[];
      })
      .then((items) => {
        if (!cancelled) setTasks(items);
      })
      .catch((error: unknown) => {
        if (!cancelled) setErrorMessage(error instanceof Error ? error.message : "WBS를 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const pendingTasks = useMemo(
    () => tasks.filter((task) => task.counts_toward_progress && task.status !== "done"),
    [tasks]
  );

  const taskMap = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);

  function selectProject(projectId: string) {
    setSelectedProjectId(projectId);
    setTasks([]);
    setResult(null);
    setErrorMessage("");
  }

  async function analyzeProject() {
    if (!selectedProjectId) return;
    setAnalyzing(true);
    setErrorMessage("");
    try {
      const response = await fetch("/api/ai/project-analyst", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: selectedProjectId })
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
        const message = typeof payload?.detail === "object" ? payload.detail?.message : payload?.detail;
        throw new Error(message || "Project Analyst 실행에 실패했습니다.");
      }
      setResult((await response.json()) as AnalystResult);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Project Analyst 실행에 실패했습니다.");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <main className="page-shell project-page">
      <div className="dashboard-topbar">
        <div>
          <span className="eyebrow">PROJECT ANALYST</span>
          <h1>인사이트</h1>
          <p className="muted">목표, 계획 WBS, 마일스톤, GitHub Evidence를 기준으로 지금 처리할 일을 검토합니다.</p>
        </div>
      </div>

      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}

      <section className="panel">
        <div className="panel-title-row">
          <div>
            <h2>프로젝트 선택</h2>
            <small>AI 분석은 버튼을 눌렀을 때만 실행됩니다.</small>
          </div>
        </div>
        {loading ? <p className="muted">프로젝트를 불러오는 중입니다.</p> : null}
        {!loading && projects.length === 0 ? <p className="muted">분석할 프로젝트가 없습니다.</p> : null}
        {projects.length > 0 ? (
          <div className="form-actions">
            <select value={selectedProjectId} onChange={(event) => selectProject(event.target.value)}>
              {projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}
            </select>
            <button type="button" disabled={!selectedProjectId || analyzing} onClick={() => void analyzeProject()}>
              {analyzing ? "AI 분석 중" : "Project Analyst 실행"}
            </button>
          </div>
        ) : null}
      </section>

      {selectedProject ? (
        <>
          <section className="summary-grid dashboard-metrics" aria-label="프로젝트 분석 기준">
            <div className="metric-card"><span>진척</span><strong>{progressLabel(selectedProject)}</strong></div>
            <div className="metric-card"><span>산정 기준</span><strong className="metric-text">{basisLabel(selectedProject)}</strong></div>
            <div className="metric-card"><span>잔여 WBS</span><strong>{pendingTasks.length}</strong></div>
            <div className="metric-card"><span>마일스톤</span><strong>{selectedProject.milestone_count}</strong></div>
          </section>

          {selectedProject.progress_basis === "unscoped" ? (
            <div className="alert error" role="status">
              이 프로젝트는 진척률 0%가 아니라 <strong>산정 전</strong>입니다. 계획 WBS가 정의되어야 진척률을 계산할 수 있습니다.
            </div>
          ) : null}

          <section className="panel">
            <div className="panel-title-row">
              <div>
                <h2>{selectedProject.title}</h2>
                <small>{basisLabel(selectedProject)} · 완료 {selectedProject.completed_tasks}/{selectedProject.total_tasks}</small>
              </div>
              <Link className="secondary-button" href={`/projects/${selectedProject.id}`}>프로젝트 열기</Link>
            </div>
            <p><strong>목표</strong> · {selectedProject.objective || "미정"}</p>
            <p><strong>성취 기준</strong> · {selectedProject.success_criteria || "미정"}</p>
          </section>
        </>
      ) : null}

      {result ? (
        <section className="panel">
          <div className="panel-title-row">
            <div>
              <h2>AI 분석 결과</h2>
              <small>AI 제안 · 커밋 근거 {result.evidence_commit_count}건</small>
            </div>
            <span className="count-badge">잔여 WBS {result.remaining_wbs_count}</span>
          </div>
          <p>{result.summary}</p>

          <div className="stacked-section">
            <div>
              <strong>지금 할 일</strong>
              {result.next_actions.length > 0 ? (
                <div className="dense-list">
                  {result.next_actions.map((action) => {
                    const task = taskMap.get(action.task_id);
                    return (
                      <div className="dense-list-row" key={action.task_id}>
                        <div>
                          <strong>{task?.title ?? "미확인 WBS"}</strong>
                          <small>{action.reason}</small>
                        </div>
                        {task ? <span>{task.status} · {task.priority}</span> : null}
                      </div>
                    );
                  })}
                </div>
              ) : <p className="muted">추천할 실제 미완료 WBS가 없습니다.</p>}
            </div>

            <div>
              <strong>블로커</strong>
              {result.blockers.length > 0 ? <ul>{result.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">확인된 블로커가 없습니다.</p>}
            </div>

            <div>
              <strong>확인 필요</strong>
              {result.needs_attention.length > 0 ? <ul>{result.needs_attention.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">추가 확인 항목이 없습니다.</p>}
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
