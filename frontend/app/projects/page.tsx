"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { parseApiErrorMessage } from "../reports/api-error";
import type { ProjectStatus, ProjectSummary } from "./types";
import { projectStatusLabels, serviceStatusLabels } from "./types";
import { projectProgressDisplay, scopedProjectAverage } from "./progress-display";
import styles from "./page.module.css";

const initialForm = {
  title: "",
  description: "",
  role: "",
  status: "idea" as ProjectStatus
};

type ProjectSort = "updated_desc" | "title_asc" | "progress_desc" | "remaining_desc";
type StatusFilter = "all" | ProjectStatus;

const projectSorts: ProjectSort[] = ["updated_desc", "title_asc", "progress_desc", "remaining_desc"];
const projectStatuses = Object.keys(projectStatusLabels) as ProjectStatus[];

function readProjectListSearchParam(params: URLSearchParams, name: "q"): string;
function readProjectListSearchParam(params: URLSearchParams, name: "status"): StatusFilter;
function readProjectListSearchParam(params: URLSearchParams, name: "sort"): ProjectSort;
function readProjectListSearchParam(params: URLSearchParams, name: "q" | "status" | "sort") {
  const value = params.get(name);
  if (name === "status") return value && projectStatuses.includes(value as ProjectStatus) ? value : "all";
  if (name === "sort") return value && projectSorts.includes(value as ProjectSort) ? value : "updated_desc";
  return value ?? "";
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [form, setForm] = useState(initialForm);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<ProjectSort>("updated_desc");
  const [hasMountedFilters, setHasMountedFilters] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [loadErrorMessage, setLoadErrorMessage] = useState("");
  const [saveErrorMessage, setSaveErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const dashboard = useMemo(() => {
    const activeProjects = projects.filter((project) => project.status !== "done" && project.status !== "on_hold");
    const remainingTasks = projects.reduce((sum, project) => sum + project.remaining_tasks, 0);
    const averageProgress = scopedProjectAverage(projects);

    return { activeProjects, remainingTasks, averageProgress };
  }, [projects]);

  const filteredProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ko-KR");
    const matches = projects.filter((project) => {
      const statusMatches = statusFilter === "all" || project.status === statusFilter;
      if (!statusMatches) return false;
      if (!normalizedQuery) return true;

      return [project.title, project.description, project.role]
        .filter(Boolean)
        .some((value) => value.toLocaleLowerCase("ko-KR").includes(normalizedQuery));
    });

    return [...matches].sort((a, b) => {
      if (sort === "title_asc") return a.title.localeCompare(b.title, "ko-KR");
      if (sort === "progress_desc") return b.progress_percent - a.progress_percent;
      if (sort === "remaining_desc") return b.remaining_tasks - a.remaining_tasks;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [projects, query, sort, statusFilter]);

  const isFiltered = query.trim().length > 0 || statusFilter !== "all";
  const contextLabel = isLoading
    ? "불러오는 중"
    : loadErrorMessage
      ? "조회 실패"
      : isFiltered
        ? `${filteredProjects.length}/${projects.length}개 표시`
        : `${projects.length}개`;

  const loadProjects = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setLoadErrorMessage("");
    try {
      const response = await fetch("/api/projects", { cache: "no-store", signal });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      setProjects((await response.json()) as ProjectSummary[]);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setLoadErrorMessage(error instanceof Error ? error.message : "프로젝트를 불러오지 못했습니다.");
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      loadProjects(controller.signal);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [loadProjects]);

  useEffect(() => {
    function applyUrlFilters() {
      const params = new URLSearchParams(window.location.search);
      setQuery(readProjectListSearchParam(params, "q"));
      setStatusFilter(readProjectListSearchParam(params, "status"));
      setSort(readProjectListSearchParam(params, "sort"));
      setHasMountedFilters(true);
    }

    applyUrlFilters();
    window.addEventListener("popstate", applyUrlFilters);
    return () => window.removeEventListener("popstate", applyUrlFilters);
  }, []);

  useEffect(() => {
    if (!hasMountedFilters) return;
    const params = new URLSearchParams(window.location.search);
    const trimmedQuery = query.trim();
    if (trimmedQuery) params.set("q", trimmedQuery);
    else params.delete("q");
    if (statusFilter === "all") params.delete("status");
    else params.set("status", statusFilter);
    if (sort === "updated_desc") params.delete("sort");
    else params.set("sort", sort);
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;
    window.history.replaceState(null, "", nextUrl);
  }, [hasMountedFilters, query, sort, statusFilter]);

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    setSaveErrorMessage("");
    if (!form.title.trim()) {
      setSaveErrorMessage("프로젝트명을 입력하세요.");
      return;
    }

    setIsSaving(true);
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
      const createdProject = (await response.json()) as ProjectSummary;
      setForm(initialForm);
      setIsCreateOpen(false);
      setSuccessMessage("프로젝트 생성 완료");
      setProjects((currentProjects) => [createdProject, ...currentProjects.filter((project) => project.id !== createdProject.id)]);
      router.push(`/projects/${createdProject.id}`);
    } catch (error) {
      setSaveErrorMessage(error instanceof Error ? error.message : "프로젝트를 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  function cancelCreate() {
    setIsCreateOpen(false);
    setSaveErrorMessage("");
  }

  return (
    <main className={`page-shell project-page ${styles.shell}`}>
      <header className={`dashboard-topbar compact-topbar ${styles.header}`}>
        <div>
          <h1>프로젝트</h1>
          <div className={styles.context} aria-live="polite">
            <span>{contextLabel}</span>
            {!isLoading && !loadErrorMessage ? <span>진행 {dashboard.activeProjects.length}</span> : null}
            {!isLoading && !loadErrorMessage ? <span>잔여 {dashboard.remainingTasks}</span> : null}
            {!isLoading && !loadErrorMessage ? <span title={dashboard.averageProgress.basisLabel}>평균 {dashboard.averageProgress.label} · {dashboard.averageProgress.scopedProjects}개</span> : null}
          </div>
        </div>
        <button
          type="button"
          className="primary-button"
          aria-controls="project-create-panel"
          aria-expanded={isCreateOpen}
          onClick={() => {
            setSaveErrorMessage("");
            setIsCreateOpen((current) => !current);
          }}
        >
          프로젝트 추가
        </button>
      </header>

      {loadErrorMessage ? (
        <div className={`alert error ${styles.alert}`} role="alert">
          <span>{loadErrorMessage}</span>
          <button type="button" className="secondary-button" onClick={() => loadProjects()}>다시 시도</button>
        </div>
      ) : null}
      {saveErrorMessage ? <div className="alert error" role="alert">{saveErrorMessage}</div> : null}
      {successMessage ? <div aria-live="polite" className="alert success" role="status">{successMessage}</div> : null}

      {isCreateOpen ? (
        <section className={styles.createPanel} id="project-create-panel">
          <div className="panel-title-row"><h2>프로젝트 생성</h2><span className="meta-pill">필수: 프로젝트명</span></div>
          <form className="stacked-form compact-form" onSubmit={handleCreateProject}>
            <div className={styles.formGrid}>
              <label>프로젝트명<input placeholder="예: 고객 포털 개선" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
              <label>내 역할<input placeholder="예: PM, Backend, Frontend" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} /></label>
              <label>개발 단계<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ProjectStatus })}>{projectStatuses.filter((value) => value !== "done").map((value) => <option key={value} value={value}>{projectStatusLabels[value]}</option>)}</select></label>
            </div>
            <label>설명<textarea placeholder="목표, 범위, 현재 상황" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
            <div className="form-actions">
              <button type="submit" disabled={isSaving}>{isSaving ? "저장 중" : "프로젝트 추가"}</button>
              <button type="button" className="secondary-button" disabled={isSaving} onClick={cancelCreate}>취소</button>
            </div>
          </form>
        </section>
      ) : null}

      <section className={styles.listPanel}>
        <div className={`panel-title-row ${styles.listTitle}`}>
          <h2>프로젝트 목록</h2>
          <span className="count-badge">{contextLabel}</span>
        </div>

        <div className={styles.controls} aria-label="프로젝트 목록 필터">
          <label>
            <span>검색</span>
            <input name="q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="프로젝트명, 설명, 역할" />
          </label>
          <label>
            <span>상태</span>
            <select name="status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)} aria-label="프로젝트 상태 필터">
              <option value="all">전체 상태</option>
              {projectStatuses.map((value) => <option key={value} value={value}>{projectStatusLabels[value]}</option>)}
            </select>
          </label>
          <label>
            <span>정렬</span>
            <select name="sort" value={sort} onChange={(event) => setSort(event.target.value as ProjectSort)} aria-label="프로젝트 정렬">
              <option value="updated_desc">최근 업데이트</option>
              <option value="title_asc">프로젝트명</option>
              <option value="progress_desc">진척 높은순</option>
              <option value="remaining_desc">잔여 많은순</option>
            </select>
          </label>
        </div>

        {isLoading ? <div className="empty-state" role="status">프로젝트를 불러오는 중입니다.</div> : null}
        {!isLoading && !loadErrorMessage && projects.length === 0 ? (
          <div className="empty-state"><span>표시할 프로젝트가 없습니다.</span><button type="button" className="primary-button" onClick={() => setIsCreateOpen(true)}>추가</button></div>
        ) : null}
        {!isLoading && !loadErrorMessage && projects.length > 0 && filteredProjects.length === 0 ? (
          <div className="empty-state">조건에 맞는 프로젝트가 없습니다.</div>
        ) : null}
        {filteredProjects.length > 0 ? (
          <div className={styles.projectRows}>
            {filteredProjects.map((project) => {
              const progress = projectProgressDisplay(project);
              return (
                <article className={styles.projectRow} key={project.id}>
                  <div className={styles.projectMain}>
                    <Link className={styles.projectTitle} href={`/projects/${project.id}`}>{project.title}</Link>
                    <div className={styles.projectMeta}>
                      <span>{project.role || "역할 미지정"}</span>
                      <span>업데이트 {project.updated_at.slice(0, 10)}</span>
                      <span>{progress.basisLabel}</span>
                    </div>
                  </div>
                  <div className={styles.lifecycleStates}>
                    <span className="meta-pill status-navy">{projectStatusLabels[project.status]}</span>
                    <span className="meta-pill">{serviceStatusLabels[project.service_status ?? "unknown"]}</span>
                  </div>
                  <div className={styles.progressCell}>
                    {progress.percent === null ? (
                      <b>{progress.label}</b>
                    ) : (
                      <>
                        <div className="mini-progress" aria-hidden="true"><span style={{ width: `${progress.percent}%` }} /></div>
                        <b>{progress.label}</b>
                      </>
                    )}
                  </div>
                  <div className={styles.counts} aria-label={`${project.completed_tasks}/${project.total_tasks} 완료, 잔여 ${project.remaining_tasks}`}>
                    <span>완료 {project.completed_tasks}/{project.total_tasks}</span>
                    <small>잔여 {project.remaining_tasks}</small>
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </main>
  );
}
