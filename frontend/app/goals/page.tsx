"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { ProjectMilestone, ProjectSummary } from "../projects/types";

type GoalProject = ProjectSummary & { milestones: ProjectMilestone[] };

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

function basisLabel(project: ProjectSummary) {
  if (project.progress_basis === "milestone") return "마일스톤 기반";
  if (project.progress_basis === "wbs") return "WBS 기반";
  return "진척률 산정 전";
}

function evidenceKindLabel(kind: MilestoneEvidence["recent_evidence"][number]["kind"]) {
  return kind === "commit" ? "Commit" : "PR";
}

async function fetchGoalProjects(): Promise<GoalProject[]> {
  const response = await fetch("/api/projects", { cache: "no-store" });
  if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
  const baseProjects = (await response.json()) as ProjectSummary[];
  return Promise.all(
    baseProjects.map(async (project) => {
      const milestoneResponse = await fetch(`/api/projects/${project.id}/milestones`, { cache: "no-store" });
      const milestones = milestoneResponse.ok ? ((await milestoneResponse.json()) as ProjectMilestone[]) : [];
      return { ...project, milestones };
    })
  );
}

function projectDrafts(projects: GoalProject[]) {
  return Object.fromEntries(projects.map((project) => [project.id, {
    objective: project.objective,
    success_criteria: project.success_criteria
  }]));
}

export default function GoalsPage() {
  const [projects, setProjects] = useState<GoalProject[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ProjectDraft>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [savingProjectId, setSavingProjectId] = useState<string | null>(null);
  const [expandedMilestoneId, setExpandedMilestoneId] = useState<string | null>(null);
  const [evidenceByMilestone, setEvidenceByMilestone] = useState<Record<string, MilestoneEvidence>>({});
  const [loadingEvidenceId, setLoadingEvidenceId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const withMilestones = await fetchGoalProjects();
      setProjects(withMilestones);
      setDrafts(projectDrafts(withMilestones));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "목표 데이터를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchGoalProjects()
      .then((withMilestones) => {
        if (cancelled) return;
        setProjects(withMilestones);
        setDrafts(projectDrafts(withMilestones));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setErrorMessage(error instanceof Error ? error.message : "목표 데이터를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const averageProgress = useMemo(() => {
    const scoped = projects.filter((project) => project.progress_basis !== "unscoped");
    if (scoped.length === 0) return 0;
    return Math.round(scoped.reduce((sum, project) => sum + project.progress_percent, 0) / scoped.length);
  }, [projects]);

  async function saveProject(event: FormEvent, project: GoalProject) {
    event.preventDefault();
    const draft = drafts[project.id];
    if (!draft) return;
    setSavingProjectId(project.id);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: draft.objective.trim(), success_criteria: draft.success_criteria.trim() })
      });
      if (!response.ok) throw new Error("목표와 성취 기준을 저장하지 못했습니다.");
      await load();
      setSuccessMessage(`${project.title} 목표를 저장했습니다.`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSavingProjectId(null);
    }
  }

  async function toggleMilestoneEvidence(projectId: string, milestoneId: string) {
    if (expandedMilestoneId === milestoneId) {
      setExpandedMilestoneId(null);
      return;
    }
    setExpandedMilestoneId(milestoneId);
    if (evidenceByMilestone[milestoneId]) return;
    setLoadingEvidenceId(milestoneId);
    setErrorMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/evidence`, { cache: "no-store" });
      if (!response.ok) throw new Error("마일스톤 근거를 불러오지 못했습니다.");
      const evidence = (await response.json()) as MilestoneEvidence;
      setEvidenceByMilestone((current) => ({ ...current, [milestoneId]: evidence }));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "마일스톤 근거 조회 중 오류가 발생했습니다.");
    } finally {
      setLoadingEvidenceId(null);
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
        <div className="metric-card"><span>마일스톤</span><strong>{projects.reduce((sum, project) => sum + project.milestones.length, 0)}</strong></div>
        <div className="metric-card"><span>평균 진척</span><strong>{averageProgress}%</strong></div>
        <div className="metric-card"><span>산정 전</span><strong>{projects.filter((project) => project.progress_basis === "unscoped").length}</strong></div>
      </section>

      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
      {successMessage ? <div className="alert success" role="status">{successMessage}</div> : null}
      {isLoading ? <section className="panel muted">목표 데이터를 불러오는 중입니다.</section> : null}

      {!isLoading ? (
        <div className="stacked-section">
          {projects.map((project) => {
            const draft = drafts[project.id] ?? { objective: "", success_criteria: "" };
            const completedMilestones = project.milestones.filter((milestone) => milestone.progress_percent === 100).length;
            return (
              <section className="panel" key={project.id}>
                <div className="panel-title-row">
                  <div>
                    <h2><Link className="text-link" href={`/projects/${project.id}`}>{project.title}</Link></h2>
                    <small>{basisLabel(project)} · {completedMilestones}/{project.milestones.length} 마일스톤 완료</small>
                  </div>
                  <span className="count-badge">{project.progress_percent}%</span>
                </div>

                <div className="overview-bars">
                  <div>
                    <span>전체 진척</span>
                    <div className="progress-row-bar"><span style={{ width: `${project.progress_percent}%` }} /></div>
                  </div>
                </div>

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
                    <button disabled={savingProjectId === project.id} type="submit">
                      {savingProjectId === project.id ? "저장 중" : "목표 저장"}
                    </button>
                  </div>
                </form>

                <div className="dense-list">
                  {project.milestones.map((milestone) => {
                    const evidence = evidenceByMilestone[milestone.id];
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
                            {evidence ? (
                              <>
                                <div className="panel-title-row">
                                  <div>
                                    <strong>완료 판단 근거</strong>
                                    <small>
                                      WBS {evidence.completed_wbs}/{evidence.total_wbs} 완료 · Evidence {evidence.evidence_count}건
                                    </small>
                                  </div>
                                  <span className="count-badge">
                                    {milestone.progress_percent === 100 ? "완료 후보" : "진행 중"}
                                  </span>
                                </div>

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
                  {project.milestones.length === 0 ? <div className="empty-state">마일스톤이 없습니다. 프로젝트 상세에서 계획 WBS부터 정의하세요.</div> : null}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </main>
  );
}
