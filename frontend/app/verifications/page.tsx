"use client";

import { useEffect, useState } from "react";

import type { MilestoneReview, ProjectMilestone, ProjectSummary } from "../projects/types";

type ProjectWithMilestones = ProjectSummary & { milestones: ProjectMilestone[] };
type StoredMilestoneReview = MilestoneReview & {
  milestone_id: string;
  reviewed_at: string;
  model: string;
  is_stale: boolean;
  stale_reason: string;
};

type ValidationWbs = { id: string; title: string; status: string; priority: string; is_validation_task: boolean };
type EvidenceSummary = {
  milestone_id: string;
  acceptance_criteria: string;
  total_wbs: number;
  completed_wbs: number;
  pending_wbs: ValidationWbs[];
  validation_wbs: ValidationWbs | null;
  evidence_count: number;
};

async function loadProjects(): Promise<ProjectWithMilestones[]> {
  const response = await fetch("/api/projects", { cache: "no-store" });
  if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
  const projects = (await response.json()) as ProjectSummary[];
  return Promise.all(projects.map(async (project) => {
    const milestonesResponse = await fetch(`/api/projects/${project.id}/milestones`, { cache: "no-store" });
    const milestones = milestonesResponse.ok ? ((await milestonesResponse.json()) as ProjectMilestone[]) : [];
    return { ...project, milestones };
  }));
}

async function loadLatestReviews(projects: ProjectWithMilestones[]) {
  const groups = await Promise.all(projects.map(async (project) => {
    const response = await fetch(`/api/ai/milestone-reviews/${project.id}`, { cache: "no-store" });
    if (!response.ok) return [] as StoredMilestoneReview[];
    return (await response.json()) as StoredMilestoneReview[];
  }));
  return groups.flat().reduce<Record<string, StoredMilestoneReview>>((result, review) => {
    result[review.milestone_id] = review;
    return result;
  }, {});
}

function verdictLabel(review: MilestoneReview) {
  if (review.verdict === "ready_candidate") return "완료 후보";
  if (review.verdict === "not_ready") return "아직 미완료";
  return "추가 확인 필요";
}

function isStoredReview(review: MilestoneReview | StoredMilestoneReview): review is StoredMilestoneReview {
  return "reviewed_at" in review;
}

function needsReview(review: MilestoneReview | StoredMilestoneReview | undefined) {
  return !review || (isStoredReview(review) && review.is_stale);
}

export default function VerificationsPage() {
  const [projects, setProjects] = useState<ProjectWithMilestones[]>([]);
  const [evidence, setEvidence] = useState<Record<string, EvidenceSummary>>({});
  const [reviews, setReviews] = useState<Record<string, MilestoneReview | StoredMilestoneReview>>({});
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [batchWorkingProjectId, setBatchWorkingProjectId] = useState<string | null>(null);
  const [batchMode, setBatchMode] = useState<"needed" | "force" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refreshProjects() {
    const next = await loadProjects();
    setProjects(next);
  }

  useEffect(() => {
    let cancelled = false;
    loadProjects()
      .then(async (items) => {
        if (cancelled) return;
        setProjects(items);
        const storedReviews = await loadLatestReviews(items);
        if (!cancelled) setReviews(storedReviews);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "데이터를 불러오지 못했습니다.");
      });
    return () => { cancelled = true; };
  }, []);

  async function getEvidence(projectId: string, milestoneId: string) {
    const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/evidence`, { cache: "no-store" });
    if (!response.ok) throw new Error("마일스톤 근거를 불러오지 못했습니다.");
    const payload = (await response.json()) as EvidenceSummary;
    setEvidence((current) => ({ ...current, [milestoneId]: payload }));
    return payload;
  }

  async function requestReview(projectId: string, milestoneId: string) {
    const response = await fetch("/api/ai/milestone-review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, milestone_id: milestoneId })
    });
    if (!response.ok) throw new Error("AI 마일스톤 검토를 완료하지 못했습니다.");
    const payload = (await response.json()) as MilestoneReview;
    setReviews((current) => ({ ...current, [milestoneId]: payload }));
    return payload;
  }

  async function review(projectId: string, milestoneId: string) {
    setWorkingId(milestoneId);
    setError("");
    setMessage("");
    try {
      await getEvidence(projectId, milestoneId);
      await requestReview(projectId, milestoneId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 검토 중 오류가 발생했습니다.");
    } finally {
      setWorkingId(null);
    }
  }

  async function reviewProject(project: ProjectWithMilestones, force = false) {
    if (project.milestones.length === 0) return;
    setBatchWorkingProjectId(project.id);
    setBatchMode(force ? "force" : "needed");
    setError("");
    setMessage("");
    let reviewed = 0;
    let skippedCurrent = 0;
    let skippedDone = 0;
    let failed = 0;
    try {
      for (const milestone of project.milestones) {
        const currentReview = reviews[milestone.id];
        if (!force && !needsReview(currentReview)) {
          skippedCurrent += 1;
          continue;
        }

        setWorkingId(milestone.id);
        try {
          const milestoneEvidence = await getEvidence(project.id, milestone.id);
          if (milestoneEvidence.validation_wbs?.status === "done") {
            skippedDone += 1;
            continue;
          }
          await requestReview(project.id, milestone.id);
          reviewed += 1;
        } catch (reviewError) {
          console.error(`Failed to review milestone [${milestone.id}] "${milestone.title}":`, reviewError);
          failed += 1;
        }
      }
      const modeLabel = force ? "전체 강제 재검토" : "필요 항목 검토";
      const summary = `${project.title} ${modeLabel}: AI 검토 ${reviewed}건 · 최신 검토 유지 ${skippedCurrent}건 · 검증 완료 유지 ${skippedDone}건`;
      setMessage(failed > 0 ? `${summary} · 실패 ${failed}건` : summary);
      if (failed > 0) setError(`일부 마일스톤 ${failed}건은 검토하지 못했습니다. 해당 항목에서 AI 검토를 다시 실행해 주세요.`);
    } finally {
      setWorkingId(null);
      setBatchWorkingProjectId(null);
      setBatchMode(null);
    }
  }

  async function changeValidation(projectId: string, milestoneId: string, status: "done" | "planned") {
    if (status === "done" && !window.confirm("성취 기준과 Evidence를 직접 확인했습니다. 검증 완료로 반영할까요?")) return;
    setWorkingId(milestoneId);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/validation`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
        const detail = typeof payload?.detail === "object" ? payload.detail.message : payload?.detail;
        throw new Error(detail || "검증 상태를 변경하지 못했습니다.");
      }
      const payload = (await response.json()) as EvidenceSummary;
      setEvidence((current) => ({ ...current, [milestoneId]: payload }));
      setReviews((current) => {
        const next = { ...current };
        delete next[milestoneId];
        return next;
      });
      await refreshProjects();
      setMessage(status === "done" ? "검증 완료를 진척률에 반영했습니다." : "검증 완료를 취소했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "검증 상태 변경 중 오류가 발생했습니다.");
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <main className="page-shell project-page verification-page">
      <div className="dashboard-topbar">
        <div>
          <span className="eyebrow">MILESTONE VERIFICATION</span>
          <h1>검증센터</h1>
          <p className="muted">기본 일괄 검토는 미검토·재검토 필요 항목만 AI를 호출합니다. 전체 강제 재검토는 최신 판단까지 다시 확인할 때만 사용하세요.</p>
        </div>
      </div>
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {message ? <div className="alert success" role="status" aria-live="polite">{message}</div> : null}
      <div className="stacked-section">
        {projects.map((project) => {
          const currentReviewedCount = project.milestones.filter((milestone) => {
            const review = reviews[milestone.id];
            return Boolean(review && (!isStoredReview(review) || !review.is_stale));
          }).length;
          const staleCount = project.milestones.filter((milestone) => {
            const review = reviews[milestone.id];
            return Boolean(review && isStoredReview(review) && review.is_stale);
          }).length;
          const missingCount = project.milestones.filter((milestone) => !reviews[milestone.id]).length;
          const neededCount = staleCount + missingCount;
          const batchBusy = batchWorkingProjectId === project.id;
          return (
            <section className="panel verification-project-panel" key={project.id}>
              <div className="panel-title-row">
                <div>
                  <h2>{project.title}</h2>
                  <small>전체 진척 {project.progress_percent}% · 마일스톤 {project.milestones.length}개</small>
                </div>
                <div className="form-actions verification-project-actions">
                  <span className="count-badge">유효 AI 검토 {currentReviewedCount}/{project.milestones.length}</span>
                  {neededCount > 0 ? <span className="count-badge">검토 필요 {neededCount}</span> : null}
                  <button className="secondary-button" type="button" disabled={batchWorkingProjectId !== null || neededCount === 0} onClick={() => void reviewProject(project)}>
                    {batchBusy && batchMode === "needed" ? "필요 항목 검토 중" : neededCount > 0 ? `필요 항목 검토 ${neededCount}건` : "검토 필요 없음"}
                  </button>
                  <button className="secondary-button" type="button" disabled={batchWorkingProjectId !== null || project.milestones.length === 0} onClick={() => void reviewProject(project, true)}>
                    {batchBusy && batchMode === "force" ? "전체 재검토 중" : "전체 강제 재검토"}
                  </button>
                  <span className="count-badge">{project.progress_percent}%</span>
                </div>
              </div>
              <div className="dense-list">
                {project.milestones.map((milestone) => {
                  const milestoneEvidence = evidence[milestone.id];
                  const reviewResult = reviews[milestone.id];
                  const validation = milestoneEvidence?.validation_wbs;
                  const busy = workingId === milestone.id || batchBusy;
                  const storedReview = reviewResult && isStoredReview(reviewResult) ? reviewResult : null;
                  const isStale = storedReview?.is_stale ?? false;
                  return (
                    <article className="panel verification-card" key={milestone.id}>
                      <div className="panel-title-row">
                        <div>
                          <strong>{milestone.title}</strong>
                          <small>{milestone.acceptance_criteria || "성취 기준 미정"}</small>
                        </div>
                        <span className="count-badge">{milestone.progress_percent}%</span>
                      </div>
                      <p className="muted">WBS {milestone.completed_tasks}/{milestone.total_tasks} 완료{milestoneEvidence ? ` · Evidence ${milestoneEvidence.evidence_count}건` : ""}{storedReview ? ` · 최근 AI 검토 ${new Date(storedReview.reviewed_at).toLocaleString("ko-KR")}` : ""}</p>
                      {isStale ? (
                        <div className="alert error" role="status">
                          {storedReview?.stale_reason || "검토 이후 프로젝트 근거가 변경되어 AI 재검토가 필요합니다."}
                        </div>
                      ) : null}
                      {reviewResult ? (
                        <div className="stacked-section verification-review">
                          <div>
                            <strong>{verdictLabel(reviewResult)} · 신뢰도 {Math.round(reviewResult.confidence * 100)}%{isStale ? " · 이전 판단" : ""}</strong>
                            <p>{reviewResult.reasoning_summary}</p>
                          </div>
                          {reviewResult.missing_checks.length > 0 ? (
                            <div>
                              <strong>추가 확인</strong>
                              <ul>{reviewResult.missing_checks.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      <div className="form-actions verification-actions">
                        <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void review(project.id, milestone.id)}>
                          {workingId === milestone.id ? "처리 중" : reviewResult ? "AI 다시 검토" : "AI 검토"}
                        </button>
                        {validation?.status === "done" ? (
                          <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void changeValidation(project.id, milestone.id, "planned")}>검증 완료 취소</button>
                        ) : reviewResult?.verdict === "ready_candidate" && validation && !isStale ? (
                          <button type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void changeValidation(project.id, milestone.id, "done")}>성취 기준 확인 · 검증 완료</button>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
