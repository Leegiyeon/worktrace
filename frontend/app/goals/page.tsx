"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { projectProgressDisplay, scopedProjectAverage } from "../projects/progress-display";
import type { MilestoneReview, ProjectMilestone, ProjectSummary } from "../projects/types";

type GoalProject = ProjectSummary & { milestones: ProjectMilestone[] };

type GoalProjectsPayload = {
  projects: GoalProject[];
  milestoneErrors: Record<string, string>;
};

type ProjectDraft = {
  objective: string;
  success_criteria: string;
};

type MilestoneEvidence = {
  milestone_id: string;
  acceptance_criteria: string;
  total_wbs: number;
  completed_wbs: number;
  pending_wbs: Array<{
    id: string;
    title: string;
    status: string;
    priority: string;
    url: string;
  }>;
  evidence_count: number;
  recent_evidence: Array<{
    kind: "commit" | "pull_request";
    id: string;
    title: string;
    url: string;
    occurred_at: string | null;
    status: string;
  }>;
};

function toProjectDraft(project: ProjectSummary): ProjectDraft {
  return {
    objective: project.objective,
    success_criteria: project.success_criteria
  };
}

function draftChanged(draft: ProjectDraft | undefined, project: ProjectSummary) {
  if (!draft) return false;
  return draft.objective !== project.objective || draft.success_criteria !== project.success_criteria;
}

function mergeProjectDrafts(current: Record<string, ProjectDraft>, projects: GoalProject[]) {
  return Object.fromEntries(projects.map((project) => {
    const currentDraft = current[project.id];
    return [project.id, currentDraft && draftChanged(currentDraft, project) ? currentDraft : toProjectDraft(project)];
  }));
}

function basisLabel(project: ProjectSummary) {
  if (project.progress_basis === "milestone") return "마일스톤 기반";
  if (project.progress_basis === "wbs") return "WBS 기반";
  return "진척률 산정 전";
}

function evidenceKindLabel(kind: MilestoneEvidence["recent_evidence"][number]["kind"]) {
  return kind === "commit" ? "Commit" : "PR";
}

function reviewVerdictLabel(review: MilestoneReview) {
  if (review.verdict === "ready_candidate") return "완료 후보";
  if (review.verdict === "not_ready") return "아직 미완료";
  return "추가 확인 필요";
}

async function fetchProjectMilestones(project: ProjectSummary): Promise<ProjectMilestone[]> {
  const milestoneResponse = await fetch(`/api/projects/${project.id}/milestones`, { cache: "no-store" });
  if (!milestoneResponse.ok) throw new Error("마일스톤을 불러오지 못했습니다.");
  return (await milestoneResponse.json()) as ProjectMilestone[];
}

async function fetchGoalProjects(): Promise<GoalProjectsPayload> {
  const response = await fetch("/api/projects", { cache: "no-store" });
  if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
  const baseProjects = (await response.json()) as ProjectSummary[];
  const milestoneErrors: Record<string, string> = {};
  const projects = await Promise.all(
    baseProjects.map(async (project) => {
      try {
        const milestones = await fetchProjectMilestones(project);
        return { ...project, milestones };
      } catch (error) {
        milestoneErrors[project.id] = error instanceof Error ? error.message : "마일스톤을 불러오지 못했습니다.";
        return { ...project, milestones: [] };
      }
    })
  );
  return { projects, milestoneErrors };
}

export default function GoalsPage() {
  const [projects, setProjects] = useState<GoalProject[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ProjectDraft>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [savingProjects, setSavingProjects] = useState<Record<string, boolean>>({});
  const [loadingMilestoneProjectId, setLoadingMilestoneProjectId] = useState<string | null>(null);
  const [expandedMilestoneId, setExpandedMilestoneId] = useState<string | null>(null);
  const [evidenceByMilestone, setEvidenceByMilestone] = useState<Record<string, MilestoneEvidence>>({});
  const [reviewByMilestone, setReviewByMilestone] = useState<Record<string, MilestoneReview>>({});
  const [milestoneErrors, setMilestoneErrors] = useState<Record<string, string>>({});
  const [evidenceErrors, setEvidenceErrors] = useState<Record<string, string>>({});
  const [reviewErrors, setReviewErrors] = useState<Record<string, string>>({});
  const [loadingEvidenceId, setLoadingEvidenceId] = useState<string | null>(null);
  const [reviewingMilestoneId, setReviewingMilestoneId] = useState<string | null>(null);
  const [loadErrorMessage, setLoadErrorMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const loadGoalData = useCallback(async () => {
    setIsLoading(true);
    setLoadErrorMessage("");
    try {
      const payload = await fetchGoalProjects();
      setProjects(payload.projects);
      setMilestoneErrors(payload.milestoneErrors);
      setDrafts((current) => mergeProjectDrafts(current, payload.projects));
    } catch (error) {
      setLoadErrorMessage(error instanceof Error ? error.message : "목표 데이터를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGoalData();
  }, [loadGoalData]);

  const dirtyProjectIds = useMemo(() => projects.filter((project) => draftChanged(drafts[project.id], project)).map((project) => project.id), [drafts, projects]);

  useEffect(() => {
    if (dirtyProjectIds.length === 0) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirtyProjectIds.length]);

  async function retryProjectMilestones(project: GoalProject) {
    setLoadingMilestoneProjectId(project.id);
    setErrorMessage("");
    try {
      const milestones = await fetchProjectMilestones(project);
      setProjects((current) => current.map((item) => item.id === project.id ? { ...item, milestones } : item));
      setMilestoneErrors((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
    } catch (error) {
      setMilestoneErrors((current) => ({ ...current, [project.id]: error instanceof Error ? error.message : "마일스톤을 불러오지 못했습니다." }));
    } finally {
      setLoadingMilestoneProjectId(null);
    }
  }

  const averageProgress = useMemo(() => scopedProjectAverage(projects), [projects]);

  async function saveProject(event: FormEvent, project: GoalProject) {
    event.preventDefault();
    const draft = drafts[project.id];
    if (!draft) return;
    setSavingProjects((current) => ({ ...current, [project.id]: true }));
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: draft.objective.trim(), success_criteria: draft.success_criteria.trim() })
      });
      if (!response.ok) throw new Error("목표와 성취 기준을 저장하지 못했습니다.");
      const savedProject = (await response.json()) as ProjectSummary;
      setProjects((current) => current.map((item) => item.id === project.id ? { ...savedProject, milestones: item.milestones } : item));
      setDrafts((current) => {
        const currentDraft = current[project.id];
        const saveCompletedBeforeFurtherEdit = currentDraft?.objective === draft.objective && currentDraft.success_criteria === draft.success_criteria;
        return { ...current, [project.id]: saveCompletedBeforeFurtherEdit ? toProjectDraft(savedProject) : currentDraft ?? toProjectDraft(savedProject) };
      });
      setSuccessMessage(`${project.title} 목표를 저장했습니다.`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSavingProjects((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
    }
  }

  async function toggleMilestoneEvidence(projectId: string, milestoneId: string) {
    if (expandedMilestoneId === milestoneId) {
      setExpandedMilestoneId(null);
      return;
    }
    setExpandedMilestoneId(milestoneId);
    if (evidenceByMilestone[milestoneId]) return;
    await loadMilestoneEvidence(projectId, milestoneId);
  }

  async function loadMilestoneEvidence(projectId: string, milestoneId: string) {
    setLoadingEvidenceId(milestoneId);
    setErrorMessage("");
    setEvidenceErrors((current) => {
      const next = { ...current };
      delete next[milestoneId];
      return next;
    });
    try {
      const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/evidence`, { cache: "no-store" });
      if (!response.ok) throw new Error("마일스톤 근거를 불러오지 못했습니다.");
      const evidence = (await response.json()) as MilestoneEvidence;
      setEvidenceByMilestone((current) => ({ ...current, [milestoneId]: evidence }));
    } catch (error) {
      setEvidenceErrors((current) => ({ ...current, [milestoneId]: error instanceof Error ? error.message : "마일스톤 근거 조회 중 오류가 발생했습니다." }));
    } finally {
      setLoadingEvidenceId(null);
    }
  }

  async function reviewMilestone(projectId: string, milestoneId: string) {
    setReviewingMilestoneId(milestoneId);
    setErrorMessage("");
    setReviewErrors((current) => {
      const next = { ...current };
      delete next[milestoneId];
      return next;
    });
    try {
      const response = await fetch("/api/ai/milestone-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, milestone_id: milestoneId })
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
        const message = typeof payload?.detail === "object" ? payload.detail?.message : payload?.detail;
        throw new Error(message || "AI 마일스톤 검토를 완료하지 못했습니다.");
      }
      const review = (await response.json()) as MilestoneReview;
      setReviewByMilestone((current) => ({ ...current, [milestoneId]: review }));
    } catch (error) {
      setReviewErrors((current) => ({ ...current, [milestoneId]: error instanceof Error ? error.message : "AI 검토 중 오류가 발생했습니다." }));
    } finally {
      setReviewingMilestoneId(null);
    }
  }

  return (
    <main className="page-shell project-page">
      <div className="dashboard-topbar">
        <div>
          <span className="eyebrow">PROJECT GOVERNANCE</span>
          <h1>목표 · 마일스톤</h1>
          <p className="muted">프로젝트 완료를 커밋 수가 아니라 목표, 성취 기준, 계획 WBS로 판단합니다.</p>
        </div>
      </div>

      <section className="summary-grid dashboard-metrics" aria-label="목표 관리 지표">
        <div className="metric-card"><span>관리 프로젝트</span><strong>{projects.length}</strong></div>
        <div className="metric-card"><span>마일스톤</span><strong>{projects.reduce((sum, project) => sum + project.milestone_count, 0)}</strong></div>
        <div className="metric-card"><span>평균 진척</span><strong>{averageProgress.label}</strong></div>
        <div className="metric-card"><span>산정 전</span><strong>{projects.filter((project) => project.progress_basis === "unscoped").length}</strong></div>
      </section>

      {loadErrorMessage ? (
        <div className="alert error" role="alert">
          {loadErrorMessage}
          <button className="secondary-button" type="button" disabled={isLoading} onClick={() => void loadGoalData()}>다시 불러오기</button>
        </div>
      ) : null}
      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
      {successMessage ? <div className="alert success" role="status">{successMessage}</div> : null}
      {isLoading ? <section className="panel muted">목표 데이터를 불러오는 중입니다.</section> : null}
      {!isLoading && !loadErrorMessage && projects.length === 0 ? <section className="empty-state">프로젝트가 없습니다.</section> : null}

      {!isLoading ? (
        <div className="stacked-section">
          {projects.map((project) => {
            const draft = drafts[project.id] ?? { objective: "", success_criteria: "" };
            const isDirty = dirtyProjectIds.includes(project.id);
            const isSavingProject = Boolean(savingProjects[project.id]);
            const completedMilestones = project.milestones.filter((milestone) => milestone.progress_percent === 100).length;
            const milestoneError = milestoneErrors[project.id];
            const progress = projectProgressDisplay(project);
            return (
              <section className="panel" key={project.id}>
                <div className="panel-title-row">
                  <div>
                    <h2><Link className="text-link" href={`/projects/${project.id}`}>{project.title}</Link></h2>
                    <small>{basisLabel(project)} · {milestoneError ? "마일스톤 조회 실패" : `${completedMilestones}/${project.milestone_count} 마일스톤 완료`}</small>
                  </div>
                  <span className="count-badge">{progress.label}</span>
                </div>

                {progress.percent !== null ? <div className="overview-bars">
                  <div>
                    <span>전체 진척</span>
                    <div className="progress-row-bar"><span style={{ width: `${progress.percent}%` }} /></div>
                  </div>
                </div> : null}

                <form className="stacked-form compact-form" onSubmit={(event) => void saveProject(event, project)}>
                  <label>
                    프로젝트 목표
                    <textarea
                      value={draft.objective}
                      placeholder="이 프로젝트가 최종적으로 달성해야 하는 상태"
                      onChange={(event) => setDrafts((current) => ({ ...current, [project.id]: { ...draft, objective: event.target.value } }))}
                    />
                  </label>
                  <label>
                    성취 기준
                    <textarea
                      value={draft.success_criteria}
                      placeholder="완료라고 판단할 수 있는 구체적인 검증 기준"
                      onChange={(event) => setDrafts((current) => ({ ...current, [project.id]: { ...draft, success_criteria: event.target.value } }))}
                    />
                  </label>
                  <div className="form-actions">
                    {isDirty ? <span className="count-badge">저장 안 됨</span> : null}
                    <button disabled={isSavingProject} type="submit">
                      {isSavingProject ? "저장 중" : "목표 저장"}
                    </button>
                  </div>
                </form>

                <div className="dense-list">
                  {milestoneError ? (
                    <div className="alert error" role="alert">
                      {milestoneError}
                      <button className="secondary-button" type="button" disabled={loadingMilestoneProjectId === project.id} onClick={() => void retryProjectMilestones(project)}>
                        {loadingMilestoneProjectId === project.id ? "다시 불러오는 중" : "마일스톤 다시 불러오기"}
                      </button>
                    </div>
                  ) : null}
                  {project.milestones.map((milestone) => {
                    const evidence = evidenceByMilestone[milestone.id];
                    const review = reviewByMilestone[milestone.id];
                    const evidenceError = evidenceErrors[milestone.id];
                    const reviewError = reviewErrors[milestone.id];
                    const isExpanded = expandedMilestoneId === milestone.id;
                    return (
                      <article key={milestone.id}>
                        <div className="dense-list-row">
                          <div>
                            <strong>{milestone.title}</strong>
                            <small>{milestone.acceptance_criteria || "성취 기준 미정"}</small>
                          </div>
                          <span>{milestone.completed_tasks}/{milestone.total_tasks} WBS</span>
                          <b>{milestone.progress_percent}% · {milestone.weight}%</b>
                          <button
                            className="secondary-button"
                            type="button"
                            aria-expanded={isExpanded}
                            onClick={() => void toggleMilestoneEvidence(project.id, milestone.id)}
                          >
                            {isExpanded ? "근거 닫기" : "근거 보기"}
                          </button>
                        </div>

                        {isExpanded ? (
                          <div className="panel milestone-evidence-panel">
                            {loadingEvidenceId === milestone.id ? <p className="muted">근거를 불러오는 중입니다.</p> : null}
                            {evidenceError ? (
                              <div className="alert error" role="alert">
                                {evidenceError}
                                <button className="secondary-button" type="button" disabled={loadingEvidenceId === milestone.id} onClick={() => void loadMilestoneEvidence(project.id, milestone.id)}>
                                  근거 다시 불러오기
                                </button>
                              </div>
                            ) : null}
                            {evidence ? (
                              <>
                                <div className="panel-title-row">
                                  <div>
                                    <strong>완료 판단 근거</strong>
                                    <small>
                                      WBS {evidence.completed_wbs}/{evidence.total_wbs} 완료 · Evidence {evidence.evidence_count}건
                                    </small>
                                  </div>
                                  <div className="form-actions">
                                    <span className="count-badge">
                                      {milestone.progress_percent === 100 ? "완료 후보" : "진행 중"}
                                    </span>
                                    <button
                                      className="secondary-button"
                                      type="button"
                                      disabled={reviewingMilestoneId === milestone.id}
                                      onClick={() => void reviewMilestone(project.id, milestone.id)}
                                    >
                                      {reviewingMilestoneId === milestone.id ? "AI 검토 중" : review ? "AI 다시 검토" : "AI 검토"}
                                    </button>
                                  </div>
                                </div>

                                {review ? (
                                  <div className="panel">
                                    <div className="panel-title-row">
                                      <div>
                                        <strong>AI 완료 판단 보조</strong>
                                        <small>AI는 완료 상태를 변경하지 않습니다. 최종 판단은 사용자가 합니다.</small>
                                      </div>
                                      <span className="count-badge">{reviewVerdictLabel(review)} · {Math.round(review.confidence * 100)}%</span>
                                    </div>
                                    <p>{review.reasoning_summary}</p>
                                    <small>
                                      검토 WBS {review.reviewed_wbs_completed}/{review.reviewed_wbs_total} · Evidence {review.evidence_count}건 중 실제 인용 {review.supporting_evidence_ids.length}건
                                    </small>
                                    <div className="stacked-section">
                                      <div>
                                        <strong>추가 확인 항목</strong>
                                        {review.missing_checks.length > 0 ? (
                                          <ul>
                                            {review.missing_checks.map((item) => <li key={item}>{item}</li>)}
                                          </ul>
                                        ) : (
                                          <p className="muted">AI가 추가 확인이 필요하다고 판단한 항목은 없습니다.</p>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ) : null}
                                {reviewError ? (
                                  <div className="alert error" role="alert">
                                    {reviewError}
                                    <button className="secondary-button" type="button" disabled={reviewingMilestoneId === milestone.id} onClick={() => void reviewMilestone(project.id, milestone.id)}>
                                      AI 검토 다시 실행
                                    </button>
                                  </div>
                                ) : null}

                                <div className="stacked-section">
                                  <div>
                                    <strong>성취 기준</strong>
                                    <p className="muted">{evidence.acceptance_criteria || "성취 기준이 정의되지 않았습니다."}</p>
                                    {milestone.progress_percent === 100 ? (
                                      <small>계획 WBS는 완료되었습니다. 성취 기준 충족 여부는 근거를 확인해 최종 판단하세요.</small>
                                    ) : (
                                      <small>아직 완료되지 않은 계획 WBS가 있어 성취 기준 검증 전 단계입니다.</small>
                                    )}
                                  </div>

                                  <div>
                                    <strong>남은 WBS</strong>
                                    <div className="dense-list">
                                      {evidence.pending_wbs.map((item) => (
                                        <div className="dense-list-row" key={item.id}>
                                          <span>{item.title}</span>
                                          <small>{item.status} · {item.priority}</small>
                                        </div>
                                      ))}
                                      {evidence.pending_wbs.length === 0 ? <div className="empty-state">남은 계획 WBS가 없습니다.</div> : null}
                                    </div>
                                  </div>

                                  <div>
                                    <strong>최근 Evidence</strong>
                                    <div className="dense-list">
                                      {evidence.recent_evidence.map((item) => (
                                        <div className="dense-list-row" key={`${item.kind}-${item.id}`}>
                                          <div>
                                            {item.url ? (
                                              <a className="text-link" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                                            ) : (
                                              <span>{item.title}</span>
                                            )}
                                            <small>{evidenceKindLabel(item.kind)} · {item.status}</small>
                                          </div>
                                          <small>{item.occurred_at ? item.occurred_at.slice(0, 10) : "날짜 없음"}</small>
                                        </div>
                                      ))}
                                      {evidence.recent_evidence.length === 0 ? <div className="empty-state">연결된 GitHub Evidence가 없습니다.</div> : null}
                                    </div>
                                  </div>
                                </div>
                              </>
                            ) : null}
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                  {!milestoneError && project.milestones.length === 0 ? <div className="empty-state">마일스톤이 없습니다. 프로젝트 상세에서 계획 WBS부터 정의하세요.</div> : null}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </main>
  );
}
