"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { milestoneProgressDisplay, projectProgressDisplay } from "../projects/progress-display";
import type { MilestoneReview, ProjectMilestone, ProjectSummary } from "../projects/types";
import styles from "./page.module.css";

type ProjectWithMilestones = ProjectSummary & { milestones: ProjectMilestone[] };
type ProjectsLoadPayload = {
  projects: ProjectWithMilestones[];
  milestoneErrors: Record<string, string>;
};
type StoredMilestoneReview = MilestoneReview & {
  milestone_id: string;
  reviewed_at: string;
  model: string;
  is_stale: boolean;
  stale_reason: string;
};

type ValidationWbs = { id: string; title: string; status: string; priority: string; is_validation_task: boolean };
type RecentEvidence = {
  kind: "commit" | "pull_request";
  id: string;
  title: string;
  url: string;
  occurred_at: string | null;
  status: string;
};
type CompletionHistoryEntry = {
  id: string;
  status: "planned" | "done";
  version: number;
  actor_owner_id: string;
  reason: string;
  evidence_note: string;
  confirmed_at: string;
  context_fingerprint: string;
};
type CompletionState = {
  status: "planned" | "done";
  version: number;
  context_fingerprint: string;
  is_stale: boolean;
  can_confirm: boolean;
  block_reasons: string[];
  history: CompletionHistoryEntry[];
};
type EvidenceSummary = {
  milestone_id: string;
  acceptance_criteria: string;
  total_wbs: number;
  completed_wbs: number;
  pending_wbs: ValidationWbs[];
  validation_wbs: ValidationWbs | null;
  evidence_count: number;
  recent_evidence: RecentEvidence[];
  completion: CompletionState;
};
type ConfirmationRequestPayload = {
  status: "done" | "planned";
  expected_version: number;
  expected_context_fingerprint: string;
  request_id: string;
  reason: string;
  evidence_note: string;
};
type ConfirmationDraft = {
  reason: string;
  evidence_note: string;
  request_id: string;
  conflictNeedsRefresh: boolean;
  pending_request: ConfirmationRequestPayload | null;
};

async function loadProjectMilestones(project: ProjectSummary): Promise<ProjectMilestone[]> {
  const milestonesResponse = await fetch(`/api/projects/${project.id}/milestones`, { cache: "no-store" });
  if (!milestonesResponse.ok) throw new Error("마일스톤을 불러오지 못했습니다.");
  return (await milestonesResponse.json()) as ProjectMilestone[];
}

async function loadProjects(): Promise<ProjectsLoadPayload> {
  const response = await fetch("/api/projects", { cache: "no-store" });
  if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
  const projects = (await response.json()) as ProjectSummary[];
  const milestoneErrors: Record<string, string> = {};
  const withMilestones = await Promise.all(projects.map(async (project) => {
    try {
      const milestones = await loadProjectMilestones(project);
      return { ...project, milestones };
    } catch (error) {
      milestoneErrors[project.id] = error instanceof Error ? error.message : "마일스톤을 불러오지 못했습니다.";
      return { ...project, milestones: [] };
    }
  }));
  return { projects: withMilestones, milestoneErrors };
}

async function loadLatestReviews(projects: ProjectWithMilestones[]) {
  const reviewErrors: Record<string, string> = {};
  const groups = await Promise.all(projects.map(async (project) => {
    try {
      const response = await fetch(`/api/ai/milestone-reviews/${project.id}`, { cache: "no-store" });
      if (!response.ok) throw new Error("저장된 AI 검토를 불러오지 못했습니다.");
      return (await response.json()) as StoredMilestoneReview[];
    } catch (error) {
      reviewErrors[project.id] = error instanceof Error ? error.message : "저장된 AI 검토를 불러오지 못했습니다.";
      return [] as StoredMilestoneReview[];
    }
  }));
  const reviews = groups.flat().reduce<Record<string, StoredMilestoneReview>>((result, review) => {
    result[review.milestone_id] = review;
    return result;
  }, {});
  return { reviews, reviewErrors };
}

function statusLabel(status: string) {
  if (status === "done") return "완료";
  if (status === "in_progress") return "진행";
  if (status === "on_hold") return "보류";
  if (status === "review") return "검토";
  if (status === "idea") return "아이디어";
  return "예정";
}

function verdictLabel(review: MilestoneReview) {
  if (review.verdict === "ready_candidate") return "완료 후보";
  if (review.verdict === "not_ready") return "아직 미완료";
  return "추가 확인 필요";
}

function evidenceKindLabel(kind: RecentEvidence["kind"]) {
  return kind === "commit" ? "Commit" : "PR";
}

function evidenceStatusLabel(status: string) {
  if (status === "collected") return "수집됨";
  if (status === "merged") return "병합됨";
  if (status === "closed") return "종료됨";
  if (status === "open") return "열림";
  return status || "상태 없음";
}

function isStoredReview(review: MilestoneReview | StoredMilestoneReview): review is StoredMilestoneReview {
  return "reviewed_at" in review;
}

function needsReview(review: MilestoneReview | StoredMilestoneReview | undefined) {
  return !review || (isStoredReview(review) && review.is_stale);
}

function isSafeEvidenceUrl(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatDate(value: string | null) {
  if (!value) return "날짜 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toLocaleDateString("ko-KR");
}

function formatDateTimeSeoul(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function createRequestId() {
  return crypto.randomUUID();
}

function emptyConfirmationDraft(): ConfirmationDraft {
  return {
    reason: "",
    evidence_note: "",
    request_id: "",
    conflictNeedsRefresh: false,
    pending_request: null
  };
}

function editableConfirmationDraft(): ConfirmationDraft {
  return {
    ...emptyConfirmationDraft(),
    request_id: createRequestId()
  };
}

function defaultCompletion(): CompletionState {
  return {
    status: "planned",
    version: 0,
    context_fingerprint: "",
    is_stale: false,
    can_confirm: false,
    block_reasons: [],
    history: []
  };
}

function completionFor(evidence: EvidenceSummary | undefined) {
  return evidence?.completion ?? defaultCompletion();
}

function isConfirmedCompletion(evidence: EvidenceSummary | undefined) {
  const completion = completionFor(evidence);
  return completion.status === "done" && !completion.is_stale;
}

function validationStateLabel(evidence: EvidenceSummary | undefined, review: MilestoneReview | StoredMilestoneReview | undefined) {
  if (!evidence) return "확인 대기";
  const completion = completionFor(evidence);
  if (completion.status === "done" && !completion.is_stale) return "확인 완료";
  if (completion.status === "done" && completion.is_stale) return "재확인 필요";
  if (evidence.pending_wbs.length > 0) return "검토 필요";
  if (review && isStoredReview(review) && review.is_stale) return "검토 필요";
  if (completion.can_confirm || review?.verdict === "ready_candidate") return "확인 가능";
  if (review?.verdict === "not_ready") return "확인 대기";
  return "근거 확인";
}

function milestoneHasPendingWbs(milestone: ProjectMilestone, evidence: EvidenceSummary | undefined) {
  if (evidence) return evidence.pending_wbs.length > 0;
  return milestone.total_tasks > milestone.completed_tasks;
}

function defaultProjectId(projects: ProjectWithMilestones[]) {
  return projects.find((project) => project.status !== "done")?.id ?? projects[0]?.id ?? "";
}

export default function VerificationsPage() {
  const [projects, setProjects] = useState<ProjectWithMilestones[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [wbsFilter, setWbsFilter] = useState<"all" | "pending" | "completed">("all");
  const [evidence, setEvidence] = useState<Record<string, EvidenceSummary>>({});
  const [evidenceLoadErrors, setEvidenceLoadErrors] = useState<Record<string, string>>({});
  const [reviews, setReviews] = useState<Record<string, MilestoneReview | StoredMilestoneReview>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [milestoneErrors, setMilestoneErrors] = useState<Record<string, string>>({});
  const [reviewLoadErrors, setReviewLoadErrors] = useState<Record<string, string>>({});
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [confirmationDrafts, setConfirmationDrafts] = useState<Record<string, ConfirmationDraft>>({});
  const [loadingMilestoneProjectId, setLoadingMilestoneProjectId] = useState<string | null>(null);
  const [loadingReviewProjectId, setLoadingReviewProjectId] = useState<string | null>(null);
  const [loadingEvidenceProjectId, setLoadingEvidenceProjectId] = useState<string | null>(null);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [batchWorkingProjectId, setBatchWorkingProjectId] = useState<string | null>(null);
  const [batchMode, setBatchMode] = useState<"needed" | "force" | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const savingMilestonesRef = useRef<Set<string>>(new Set());

  const loadVerificationData = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const payload = await loadProjects();
      setProjects(payload.projects);
      setSelectedProjectId((current) => payload.projects.some((project) => project.id === current) ? current : defaultProjectId(payload.projects));
      setMilestoneErrors(payload.milestoneErrors);
      const storedReviews = await loadLatestReviews(payload.projects);
      setReviews(storedReviews.reviews);
      setReviewLoadErrors(storedReviews.reviewErrors);
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "데이터를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadVerificationData();
  }, [loadVerificationData]);

  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId) ?? null, [projects, selectedProjectId]);

  const loadEvidenceForProject = useCallback(async (project: ProjectWithMilestones) => {
    if (milestoneErrors[project.id] || project.milestones.length === 0) return;
    setLoadingEvidenceProjectId(project.id);
    const nextEvidence: Record<string, EvidenceSummary> = {};
    const nextErrors: Record<string, string> = {};
    try {
      await Promise.all(project.milestones.map(async (milestone) => {
        try {
          const response = await fetch(`/api/projects/${project.id}/milestones/${milestone.id}/evidence`, { cache: "no-store" });
          if (!response.ok) throw new Error("마일스톤 근거를 불러오지 못했습니다.");
          nextEvidence[milestone.id] = (await response.json()) as EvidenceSummary;
        } catch (reason) {
          nextErrors[milestone.id] = reason instanceof Error ? reason.message : "마일스톤 근거를 불러오지 못했습니다.";
        }
      }));
      setEvidence((current) => ({ ...current, ...nextEvidence }));
      setEvidenceLoadErrors((current) => {
        const cleaned = { ...current };
        for (const milestone of project.milestones) delete cleaned[milestone.id];
        return { ...cleaned, ...nextErrors };
      });
    } finally {
      setLoadingEvidenceProjectId(null);
    }
  }, [milestoneErrors]);

  useEffect(() => {
    if (!selectedProject) return;
    void loadEvidenceForProject(selectedProject);
  }, [loadEvidenceForProject, selectedProject]);

  async function retryMilestones(project: ProjectWithMilestones) {
    setLoadingMilestoneProjectId(project.id);
    try {
      const milestones = await loadProjectMilestones(project);
      const nextProject = { ...project, milestones };
      setProjects((current) => current.map((item) => item.id === project.id ? nextProject : item));
      setMilestoneErrors((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
      await loadEvidenceForProject(nextProject);
    } catch (reason) {
      setMilestoneErrors((current) => ({ ...current, [project.id]: reason instanceof Error ? reason.message : "마일스톤을 불러오지 못했습니다." }));
    } finally {
      setLoadingMilestoneProjectId(null);
    }
  }

  async function retryStoredReviews(project: ProjectWithMilestones) {
    setLoadingReviewProjectId(project.id);
    try {
      const loaded = await loadLatestReviews([project]);
      setReviews((current) => {
        const next = { ...current };
        for (const milestone of project.milestones) delete next[milestone.id];
        return { ...next, ...loaded.reviews };
      });
      setReviewLoadErrors((current) => {
        const next = { ...current, ...loaded.reviewErrors };
        if (!loaded.reviewErrors[project.id]) delete next[project.id];
        return next;
      });
    } finally {
      setLoadingReviewProjectId(null);
    }
  }

  async function getEvidence(projectId: string, milestoneId: string, options: { resolveConfirmationDraft?: boolean } = {}) {
    const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/evidence`, { cache: "no-store" });
    if (!response.ok) throw new Error("마일스톤 근거를 불러오지 못했습니다.");
    const payload = (await response.json()) as EvidenceSummary;
    setEvidence((current) => ({ ...current, [milestoneId]: payload }));
    setEvidenceLoadErrors((current) => {
      const next = { ...current };
      delete next[milestoneId];
      return next;
    });
    if (options.resolveConfirmationDraft) {
      setConfirmationDrafts((current) => {
        const existing = current[milestoneId];
        if (!existing?.conflictNeedsRefresh && !existing?.pending_request) return current;
        return {
          ...current,
          [milestoneId]: {
            ...existing,
            request_id: createRequestId(),
            conflictNeedsRefresh: false,
            pending_request: null
          }
        };
      });
    }
    return payload;
  }

  async function retryEvidence(projectId: string, milestoneId: string) {
    setWorkingId(milestoneId);
    setError("");
    setMessage("");
    try {
      await getEvidence(projectId, milestoneId, { resolveConfirmationDraft: true });
      setActionErrors((current) => {
        const next = { ...current };
        delete next[milestoneId];
        return next;
      });
    } catch (reason) {
      setEvidenceLoadErrors((current) => ({ ...current, [milestoneId]: reason instanceof Error ? reason.message : "마일스톤 근거를 불러오지 못했습니다." }));
    } finally {
      setWorkingId(null);
    }
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
    setActionErrors((current) => {
      const next = { ...current };
      delete next[milestoneId];
      return next;
    });
    try {
      await getEvidence(projectId, milestoneId);
      await requestReview(projectId, milestoneId);
    } catch (reason) {
      setActionErrors((current) => ({ ...current, [milestoneId]: reason instanceof Error ? reason.message : "AI 검토 중 오류가 발생했습니다." }));
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
        if (isConfirmedCompletion(evidence[milestone.id])) {
          skippedDone += 1;
          continue;
        }
        const currentReview = reviews[milestone.id];
        if (!force && !needsReview(currentReview)) {
          skippedCurrent += 1;
          continue;
        }

        setWorkingId(milestone.id);
        setActionErrors((current) => {
          const next = { ...current };
          delete next[milestone.id];
          return next;
        });
        try {
          const milestoneEvidence = await getEvidence(project.id, milestone.id);
          if (isConfirmedCompletion(milestoneEvidence)) {
            skippedDone += 1;
            continue;
          }
          await requestReview(project.id, milestone.id);
          reviewed += 1;
        } catch (reviewError) {
          console.error(`Failed to review milestone [${milestone.id}] "${milestone.title}":`, reviewError);
          setActionErrors((current) => ({ ...current, [milestone.id]: reviewError instanceof Error ? reviewError.message : "AI 검토 중 오류가 발생했습니다." }));
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

  function updateConfirmationDraft(milestoneId: string, patch: Partial<ConfirmationDraft>) {
    setConfirmationDrafts((current) => {
      const existing = current[milestoneId] ?? editableConfirmationDraft();
      if (existing.pending_request) return current;
      return { ...current, [milestoneId]: { ...existing, ...patch } };
    });
  }

  function draftFor(milestoneId: string) {
    return confirmationDrafts[milestoneId] ?? emptyConfirmationDraft();
  }

  async function changeValidation(projectId: string, milestoneId: string, status: "done" | "planned") {
    if (savingMilestonesRef.current.has(milestoneId)) return;
    const currentEvidence = evidence[milestoneId];
    if (!currentEvidence) return;
    const completion = completionFor(currentEvidence);
    const draft = draftFor(milestoneId);
    if (draft.conflictNeedsRefresh) {
      setActionErrors((current) => ({ ...current, [milestoneId]: "근거를 새로고침한 뒤 다시 저장해 주세요." }));
      return;
    }
    const pendingRequest = draft.pending_request;
    if (pendingRequest && pendingRequest.status !== status) {
      setActionErrors((current) => ({ ...current, [milestoneId]: "이전 요청 결과를 확인할 때까지 같은 요청만 다시 시도할 수 있습니다." }));
      return;
    }
    const reason = pendingRequest?.reason ?? draft.reason.trim();
    const evidenceNote = pendingRequest?.evidence_note ?? draft.evidence_note.trim();
    if (!pendingRequest && !reason) {
      setActionErrors((current) => ({ ...current, [milestoneId]: "변경 사유를 입력해 주세요." }));
      return;
    }
    if (!pendingRequest && status === "done" && !evidenceNote) {
      setActionErrors((current) => ({ ...current, [milestoneId]: "검증 완료에는 수동 Evidence 메모가 필요합니다." }));
      return;
    }
    const requestPayload: ConfirmationRequestPayload = pendingRequest ?? {
      status,
      expected_version: completion.version,
      expected_context_fingerprint: completion.context_fingerprint,
      request_id: draft.request_id || createRequestId(),
      reason,
      evidence_note: status === "done" ? evidenceNote : ""
    };
    savingMilestonesRef.current.add(milestoneId);
    setWorkingId(milestoneId);
    setError("");
    setMessage("");
    setActionErrors((current) => {
      const next = { ...current };
      delete next[milestoneId];
      return next;
    });
    setConfirmationDrafts((current) => ({
      ...current,
      [milestoneId]: {
        ...(current[milestoneId] ?? editableConfirmationDraft()),
        pending_request: requestPayload
      }
    }));
    try {
      const response = await fetch(`/api/projects/${projectId}/milestones/${milestoneId}/validation`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload)
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
        const detail = typeof payload?.detail === "object" ? payload.detail.message : payload?.detail;
        if (response.status === 409) {
          setConfirmationDrafts((current) => {
            const existing = current[milestoneId] ?? editableConfirmationDraft();
            return { ...current, [milestoneId]: { ...existing, conflictNeedsRefresh: true, pending_request: null } };
          });
          throw new Error(detail || "근거가 변경되었습니다. 근거 새로고침 후 다시 저장해 주세요.");
        }
        throw new Error(detail || "검증 상태를 변경하지 못했습니다.");
      }
      const payload = (await response.json()) as EvidenceSummary;
      setEvidence((current) => ({ ...current, [milestoneId]: payload }));
      setConfirmationDrafts((current) => ({
        ...current,
        [milestoneId]: editableConfirmationDraft()
      }));
      setMessage(status === "done" ? "마일스톤 완료 확인을 저장했습니다." : "마일스톤 완료 확인을 다시 계획 상태로 열었습니다.");
    } catch (reason) {
      setActionErrors((current) => ({ ...current, [milestoneId]: reason instanceof Error ? reason.message : "검증 상태 변경 중 오류가 발생했습니다." }));
    } finally {
      savingMilestonesRef.current.delete(milestoneId);
      setWorkingId(null);
    }
  }

  const evidenceBusy = selectedProject ? loadingEvidenceProjectId === selectedProject.id : false;
  const controlsLocked = Boolean(workingId || batchWorkingProjectId || loadingMilestoneProjectId || loadingReviewProjectId || loadingEvidenceProjectId);

  return (
    <main className={`page-shell ${styles.page}`}>
      <header className={styles.header}>
        <div>
          <h1>완료 검토</h1>
        </div>
        <label className={styles.projectSelect} htmlFor="review-project">
          <span>프로젝트</span>
          <select id="review-project" aria-label="프로젝트" value={selectedProjectId} disabled={isLoading || controlsLocked || projects.length === 0} onChange={(event) => setSelectedProjectId(event.target.value)}>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.status === "done" ? `[완료] ${project.title}` : project.title}</option>
            ))}
          </select>
        </label>
      </header>

      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {loadError ? (
        <div className="alert error" role="alert">
          {loadError}
          <button className="secondary-button" type="button" disabled={isLoading || controlsLocked} onClick={() => void loadVerificationData()}>다시 불러오기</button>
        </div>
      ) : null}
      {message ? <div className="alert success" role="status" aria-live="polite">{message}</div> : null}
      {isLoading ? <section className="empty-state" role="status">검증 데이터를 불러오는 중입니다.</section> : null}
      {!isLoading && !loadError && projects.length === 0 ? <section className="empty-state">프로젝트가 없습니다.</section> : null}

      {!isLoading && selectedProject ? (() => {
        const project = selectedProject;
        const currentReviewedCount = project.milestones.filter((milestone) => {
          const review = reviews[milestone.id];
          return Boolean(review && (!isStoredReview(review) || !review.is_stale));
        }).length;
        const neededCount = project.milestones.filter((milestone) => !isConfirmedCompletion(evidence[milestone.id]) && needsReview(reviews[milestone.id])).length;
        const batchBusy = batchWorkingProjectId === project.id;
        const milestoneError = milestoneErrors[project.id];
        const reviewLoadError = reviewLoadErrors[project.id];
        const hasEvidenceErrors = project.milestones.some((milestone) => Boolean(evidenceLoadErrors[milestone.id]));
        const allEvidenceLoaded = project.milestones.every((milestone) => Boolean(evidence[milestone.id]));
        const evidenceReady = project.milestones.length > 0 && allEvidenceLoaded && !hasEvidenceErrors && !evidenceBusy;
        const countsUnavailable = Boolean(milestoneError || reviewLoadError || !evidenceReady);
        const progress = projectProgressDisplay(project);
        const verifiedCount = project.milestones.filter((milestone) => isConfirmedCompletion(evidence[milestone.id])).length;
        const pendingWbsCount = project.milestones.reduce((sum, milestone) => sum + (evidence[milestone.id]?.pending_wbs.length ?? 0), 0);
        const visibleMilestones = project.milestones.filter((milestone) => {
          if (wbsFilter === "all") return true;
          const hasPending = milestoneHasPendingWbs(milestone, evidence[milestone.id]);
          return wbsFilter === "pending" ? hasPending : !hasPending;
        });

        return (
          <section className={styles.projectSurface} aria-busy={controlsLocked || evidenceBusy}>
            <div className={styles.summaryGrid}>
              <div className={styles.metric}>
                <strong>{progress.label}</strong>
                <span>{progress.basisLabel}</span>
              </div>
              <div className={styles.metric}>
                <strong>{evidenceReady ? `${verifiedCount}/${project.milestones.length}` : "-"}</strong>
                <span>확인 완료</span>
              </div>
              <div className={styles.metric}>
                <strong>{evidenceReady ? pendingWbsCount : "-"}</strong>
                <span>남은 WBS</span>
              </div>
              <div className={styles.metric}>
                <strong>{countsUnavailable ? "조회 보류" : `${currentReviewedCount}/${project.milestones.length}`}</strong>
                <span>보조 AI 검토</span>
              </div>
            </div>

            {milestoneError ? (
              <div className="alert error" role="alert">
                {milestoneError}
                <button className="secondary-button" type="button" disabled={loadingMilestoneProjectId === project.id || controlsLocked} onClick={() => void retryMilestones(project)}>
                  {loadingMilestoneProjectId === project.id ? "다시 불러오는 중" : "마일스톤 다시 불러오기"}
                </button>
              </div>
            ) : null}
            {reviewLoadError ? (
              <div className="alert error" role="alert">
                {reviewLoadError}
                <button className="secondary-button" type="button" disabled={loadingReviewProjectId === project.id || controlsLocked} onClick={() => void retryStoredReviews(project)}>
                  {loadingReviewProjectId === project.id ? "다시 불러오는 중" : "AI 검토 다시 불러오기"}
                </button>
              </div>
            ) : null}
            {evidenceBusy ? <div className="empty-state" role="status">근거와 검증 상태를 불러오는 중입니다.</div> : null}

            <fieldset className={styles.lockableArea} disabled={controlsLocked}>
              <legend className={styles.visuallyHidden}>완료 검토 작업</legend>
              <div className={styles.projectToolbar}>
                <div>
                  <strong>{project.title}</strong>
                  <small>{project.status === "done" ? "완료 프로젝트" : "활성 프로젝트"} · 마일스톤 {project.milestone_count}개</small>
                </div>
                <div className={styles.aiActions}>
                  <label className={styles.compactSelect}>
                    <span>WBS 상태</span>
                    <select value={wbsFilter} onChange={(event) => setWbsFilter(event.target.value as "all" | "pending" | "completed")}>
                      <option value="all">전체</option>
                      <option value="pending">남은 WBS</option>
                      <option value="completed">WBS 완료</option>
                    </select>
                  </label>
                  <span className="count-badge">{countsUnavailable ? "AI 검토 조회 보류" : `유효 AI 검토 ${currentReviewedCount}/${project.milestones.length}`}</span>
                  {!countsUnavailable && neededCount > 0 ? <span className="count-badge">검토 필요 {neededCount}</span> : null}
                  <button className="secondary-button" type="button" disabled={batchWorkingProjectId !== null || countsUnavailable || neededCount === 0} onClick={() => void reviewProject(project)}>
                    {batchBusy && batchMode === "needed" ? "필요 항목 검토 중" : countsUnavailable ? "조회 복구 필요" : neededCount > 0 ? `필요 항목 검토 ${neededCount}건` : "검토 필요 없음"}
                  </button>
                  <details className={styles.advancedReview}>
                    <summary>고급</summary>
                    <button className="secondary-button" type="button" disabled={batchWorkingProjectId !== null || countsUnavailable || project.milestones.length === 0} onClick={() => void reviewProject(project, true)}>
                      {batchBusy && batchMode === "force" ? "전체 재검토 중" : "전체 강제 재검토"}
                    </button>
                  </details>
                </div>
              </div>

              <div className={styles.milestoneList}>
                {visibleMilestones.map((milestone) => {
                  const milestoneEvidence = evidence[milestone.id];
                  const reviewResult = reviews[milestone.id];
                  const completion = completionFor(milestoneEvidence);
                  const currentConfirmed = isConfirmedCompletion(milestoneEvidence);
                  const draft = draftFor(milestone.id);
                  const pendingRequest = draft.pending_request;
                  const confirmationEditLocked = Boolean(pendingRequest || draft.conflictNeedsRefresh);
                  const doneRetryPending = pendingRequest?.status === "done";
                  const plannedRetryPending = pendingRequest?.status === "planned";
                  const busy = workingId === milestone.id || batchBusy;
                  const storedReview = reviewResult && isStoredReview(reviewResult) ? reviewResult : null;
                  const isStale = storedReview?.is_stale ?? false;
                  const actionError = actionErrors[milestone.id];
                  const evidenceError = evidenceLoadErrors[milestone.id];
                  const stateLabel = validationStateLabel(milestoneEvidence, reviewResult);
                  const milestoneProgress = milestoneProgressDisplay(milestone);
                  const reasonInputId = `confirmation-reason-${milestone.id}`;
                  const evidenceNoteInputId = `confirmation-evidence-note-${milestone.id}`;
                  return (
                    <article className={styles.milestoneRow} key={milestone.id}>
                      <div className={styles.milestoneMain}>
                        <div>
                          <strong>{milestone.title}</strong>
                        </div>
                        <div className={styles.stateStack}>
                          <span className={styles.stateBadge}>{stateLabel}</span>
                          <span className="count-badge">{milestoneProgress.label}</span>
                          <small>{milestoneProgress.basisLabel}</small>
                        </div>
                      </div>

                      <div className={styles.evidenceGrid}>
                        <div>
                          <strong>성취 기준</strong>
                          <p>{milestoneEvidence?.acceptance_criteria || milestone.acceptance_criteria || "성취 기준이 정의되지 않았습니다."}</p>
                        </div>
                        <div>
                          <strong>WBS</strong>
                          <p>{milestoneEvidence ? `${milestoneEvidence.completed_wbs}/${milestoneEvidence.total_wbs} 완료` : `${milestone.completed_tasks}/${milestone.total_tasks} 완료`}</p>
                        </div>
                        <div>
                          <strong>Evidence</strong>
                          <p>{milestoneEvidence ? `${milestoneEvidence.evidence_count}건` : "조회 대기"}</p>
                        </div>
                        <div>
                          <strong>사용자 확인</strong>
                          <p>{milestoneEvidence ? `${completion.status === "done" ? "완료" : "계획"} · v${completion.version}${completion.is_stale ? " · 재확인 필요" : ""}` : "조회 대기"}</p>
                        </div>
                      </div>

                      {evidenceError ? (
                        <div className="alert error" role="alert">
                          {evidenceError}
                          <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void retryEvidence(project.id, milestone.id)}>근거 다시 불러오기</button>
                        </div>
                      ) : null}

                      <div className={styles.detailColumns}>
                        <div>
                          <strong>남은 WBS</strong>
                          <div className={styles.compactList}>
                            {(milestoneEvidence?.pending_wbs ?? []).map((item) => (
                              <div className={styles.compactRow} key={item.id}>
                                <span>{item.title}</span>
                                <small>{statusLabel(item.status)} · {item.priority}</small>
                              </div>
                            ))}
                            {milestoneEvidence && milestoneEvidence.pending_wbs.length === 0 ? <div className="empty-state">남은 계획 WBS가 없습니다.</div> : null}
                            {!milestoneEvidence && !evidenceError ? <div className="empty-state">근거 조회 대기</div> : null}
                          </div>
                        </div>
                        <div>
                          <strong>최근 Evidence</strong>
                          <div className={styles.compactList}>
                            {(milestoneEvidence?.recent_evidence ?? []).map((item) => (
                              <div className={styles.compactRow} key={`${item.kind}-${item.id}`}>
                                <span>
                                  {item.url && isSafeEvidenceUrl(item.url) ? (
                                    <a className="text-link" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                                  ) : (
                                    item.title
                                  )}
                                </span>
                                <small>{evidenceKindLabel(item.kind)} · {evidenceStatusLabel(item.status)} · {formatDate(item.occurred_at)}</small>
                              </div>
                            ))}
                            {milestoneEvidence && (milestoneEvidence.recent_evidence ?? []).length === 0 ? <div className="empty-state">연결된 GitHub Evidence가 없습니다.</div> : null}
                            {!milestoneEvidence && !evidenceError ? <div className="empty-state">근거 조회 대기</div> : null}
                          </div>
                        </div>
                      </div>

                      {isStale ? (
                        <div className="alert error" role="status">
                          {storedReview?.stale_reason || "검토 이후 프로젝트 근거가 변경되어 AI 재검토가 필요합니다."}
                        </div>
                      ) : null}
                      {reviewResult ? (
                        <div className={styles.reviewSummary}>
                          <strong>{verdictLabel(reviewResult)}{isStale ? " · 이전 판단" : ""}</strong>
                          <p>{reviewResult.reasoning_summary}</p>
                          {reviewResult.missing_checks.length > 0 ? (
                            <div>
                              <strong>추가 확인</strong>
                              <ul>{reviewResult.missing_checks.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {storedReview ? <small>최근 AI 검토 {new Date(storedReview.reviewed_at).toLocaleString("ko-KR")}</small> : null}
                        </div>
                      ) : null}
                      {actionError ? (
                        <div className="alert error" role="alert">
                          {actionError}
                          {!draft.conflictNeedsRefresh && actionError.includes("AI") ? (
                            <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void review(project.id, milestone.id)}>
                              다시 시도
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                      {milestoneEvidence ? (
                        <details className={styles.confirmationPanel} open={actionError || confirmationEditLocked ? true : undefined}>
                          <summary className={styles.confirmationSummary}>
                            <span>수동 완료 확인</span>
                            <span className="count-badge">{currentConfirmed ? "확인 완료" : completion.can_confirm ? "확인 가능" : "확인 제한"}</span>
                          </summary>
                          {completion.block_reasons.length > 0 ? (
                            <ul className={styles.blockList}>
                              {completion.block_reasons.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                          ) : null}
                          <label htmlFor={reasonInputId}>
                            <span>사유</span>
                          </label>
                          <input
                            id={reasonInputId}
                            disabled={confirmationEditLocked}
                            maxLength={2000}
                            placeholder="예: 수용 기준과 남은 WBS를 직접 확인"
                            value={draft.reason}
                            onChange={(event) => updateConfirmationDraft(milestone.id, { reason: event.target.value })}
                          />
                          <label htmlFor={evidenceNoteInputId}>
                            <span>Evidence 메모</span>
                          </label>
                          <textarea
                            id={evidenceNoteInputId}
                            disabled={confirmationEditLocked}
                            maxLength={8000}
                            placeholder="완료 확인에 사용한 수동 근거를 기록"
                            rows={3}
                            value={draft.evidence_note}
                            onChange={(event) => updateConfirmationDraft(milestone.id, { evidence_note: event.target.value })}
                          />
                          <div className={styles.rowActions}>
                            <button
                              type="button"
                              disabled={busy || batchWorkingProjectId !== null || draft.conflictNeedsRefresh || (currentConfirmed && !doneRetryPending) || (!pendingRequest && (!completion.can_confirm || !draft.reason.trim() || !draft.evidence_note.trim())) || (Boolean(pendingRequest) && !doneRetryPending)}
                              onClick={() => void changeValidation(project.id, milestone.id, "done")}
                            >
                              {doneRetryPending ? "같은 완료 확인 다시 시도" : "완료 확인 저장"}
                            </button>
                            <button
                              className="secondary-button"
                              type="button"
                              disabled={busy || batchWorkingProjectId !== null || draft.conflictNeedsRefresh || (!pendingRequest && (completion.status !== "done" || !draft.reason.trim())) || (Boolean(pendingRequest) && !plannedRetryPending)}
                              onClick={() => void changeValidation(project.id, milestone.id, "planned")}
                            >
                              {plannedRetryPending ? "같은 다시 열기 요청 재시도" : "다시 계획으로 열기"}
                            </button>
                          </div>
                          <details className={styles.historyDisclosure}>
                            <summary>최근 확인 이력 {completion.history.length}</summary>
                            <div className={styles.compactList}>
                              {completion.history.map((entry) => (
                                <div className={styles.compactRow} key={entry.id}>
                                  <span>{entry.status === "done" ? "완료 확인" : "계획 전환"} · v{entry.version}</span>
                                  <small>{formatDateTimeSeoul(entry.confirmed_at)} Asia/Seoul · {entry.actor_owner_id} · {entry.reason}</small>
                                  {entry.evidence_note ? <small>{entry.evidence_note}</small> : null}
                                </div>
                              ))}
                              {completion.history.length === 0 ? <div className="empty-state">확인 이력이 없습니다.</div> : null}
                            </div>
                          </details>
                        </details>
                      ) : null}
                      <div className={styles.rowActions}>
                        <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void retryEvidence(project.id, milestone.id)}>근거 새로고침</button>
                        <button className="secondary-button" type="button" disabled={busy || batchWorkingProjectId !== null} onClick={() => void review(project.id, milestone.id)}>
                          {workingId === milestone.id ? "처리 중" : reviewResult ? "AI 다시 검토" : "AI 검토"}
                        </button>
                      </div>
                    </article>
                  );
                })}
                {!milestoneError && project.milestones.length === 0 ? <div className="empty-state">마일스톤이 없습니다.</div> : null}
                {!milestoneError && project.milestones.length > 0 && visibleMilestones.length === 0 ? <div className="empty-state">필터에 맞는 마일스톤이 없습니다.</div> : null}
              </div>
            </fieldset>
          </section>
        );
      })() : null}
      {!isLoading && !loadError && selectedProjectId && !selectedProject && projects.length > 0 ? <section className="empty-state">선택한 프로젝트를 찾을 수 없습니다.</section> : null}
    </main>
  );
}
