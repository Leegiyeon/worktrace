"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { parseApiErrorMessage } from "../reports/api-error";
import type { ProjectStatus, ProjectSummary } from "./types";
import { projectStatusLabels } from "./types";

const initialForm = {
  title: "",
  description: "",
  role: "",
  status: "idea" as ProjectStatus
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [form, setForm] = useState(initialForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const dashboard = useMemo(() => {
    const activeProjects = projects.filter((project) => project.status !== "done" && project.status !== "on_hold");
    const remainingTasks = projects.reduce((sum, project) => sum + project.remaining_tasks, 0);
    const averageProgress = projects.length
      ? Math.round(projects.reduce((sum, project) => sum + project.progress_percent, 0) / projects.length)
      : 0;

    return { activeProjects, remainingTasks, averageProgress };
  }, [projects]);

  async function loadProjects() {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await fetch("/api/projects", { cache: "no-store" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      setProjects((await response.json()) as ProjectSummary[]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "프로젝트를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;

    fetch("/api/projects", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(parseApiErrorMessage(detail));
        }
        return response.json() as Promise<ProjectSummary[]>;
      })
      .then((data) => {
        if (isMounted) setProjects(data);
      })
      .catch((error: unknown) => {
        if (isMounted) setErrorMessage(error instanceof Error ? error.message : "프로젝트를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    if (!form.title.trim()) {
      setErrorMessage("프로젝트명을 입력하세요.");
      return;
    }

    setIsSaving(true);
    setErrorMessage("");
    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form)
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      setForm(initialForm);
      await loadProjects();
      setSuccessMessage("프로젝트 생성 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "프로젝트를 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="page-shell project-page">
      <header className="dashboard-topbar compact-topbar">
        <div>
          <h1>프로젝트</h1>
        </div>
        <div className="task-meta">
          <span className="meta-pill status-navy">진행 {dashboard.activeProjects.length}</span>
          <span className="meta-pill">잔여 {dashboard.remainingTasks}</span>
          <span className="meta-pill">평균 {dashboard.averageProgress}%</span>
        </div>
      </header>

      <section className="summary-grid dashboard-metrics" aria-label="프로젝트 요약">
        <div className="metric-card"><span>진행 중</span><strong>{dashboard.activeProjects.length}</strong></div>
        <div className="metric-card"><span>전체</span><strong>{projects.length}</strong></div>
        <div className="metric-card"><span>잔여 업무</span><strong>{dashboard.remainingTasks}</strong></div>
        <div className="metric-card"><span>평균 진척</span><strong>{dashboard.averageProgress}%</strong></div>
      </section>

      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
      {successMessage ? <div aria-live="polite" className="alert success" role="status">{successMessage}</div> : null}

      <section className="project-management-grid">
        <section className="panel project-create-panel">
          <div className="panel-title-row"><h2>프로젝트 생성</h2><span className="meta-pill">필수: 프로젝트명</span></div>
          <form className="stacked-form compact-form" onSubmit={handleCreateProject}>
            <label>프로젝트명<input placeholder="예: 고객 포털 개선" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
            <label>설명<textarea placeholder="목표, 범위, 현재 상황" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
            <label>내 역할<input placeholder="예: PM, Backend, Frontend" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} /></label>
            <label>상태<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ProjectStatus })}>{Object.entries(projectStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <button type="submit" disabled={isSaving}>{isSaving ? "저장 중" : "프로젝트 추가"}</button>
          </form>
        </section>

        <section className="panel project-table-panel">
          <div className="panel-title-row"><h2>프로젝트 목록</h2><span className="count-badge">{projects.length}개</span></div>
          {isLoading ? <div className="empty-state">로딩 중</div> : null}
          {!isLoading && !errorMessage && projects.length === 0 ? <div className="empty-state">프로젝트 없음</div> : null}
          {projects.length > 0 ? (
            <div className="data-table-wrap">
              <table className="data-table dense-task-table">
                <thead><tr><th>프로젝트</th><th>상태</th><th>역할</th><th>진척도</th><th>잔여</th><th>완료/전체</th><th>업데이트</th></tr></thead>
                <tbody>{projects.map((project) => (
                  <tr key={project.id}>
                    <td><Link className="table-link-button" href={`/projects/${project.id}`}>{project.title}</Link></td>
                    <td><span className="meta-pill status-navy">{projectStatusLabels[project.status]}</span></td>
                    <td>{project.role || "-"}</td>
                    <td><div className="table-progress"><div className="mini-progress"><span style={{ width: `${project.progress_percent}%` }} /></div><b>{project.progress_percent}%</b></div></td>
                    <td>{project.remaining_tasks}</td>
                    <td>{project.completed_tasks}/{project.total_tasks}</td>
                    <td>{project.updated_at.slice(0, 10)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : null}
        </section>
      </section>
    </main>
  );
}
