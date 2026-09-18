import type { ProjectMilestone, ProjectSummary, ProjectTask } from "./types";

export type ProgressDisplay = {
  label: string;
  percent: number | null;
  isScoped: boolean;
  isEstimate: boolean;
  basisLabel: string;
};

export type ScopedProgressAverage = ProgressDisplay & {
  scopedProjects: number;
};

export type WbsActivityCounts = {
  allActivities: number;
  countedWbs: number;
  referenceActivities: number;
};

function isFinitePercent(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
}

function isLegacySyntheticCheckpoint(task: Pick<ProjectTask, "source_provider" | "source_key">) {
  return task.source_provider === "derived-github" && (task.source_key ?? "").startsWith("milestone-validation:");
}

export function projectProgressDisplay(project: Pick<ProjectSummary, "progress_basis" | "progress_percent" | "derived_task_count" | "progress_plan_status">): ProgressDisplay {
  if (project.progress_plan_status === "unapproved") return { label: "계획 미승인", percent: null, isScoped: false, isEstimate: true, basisLabel: "진행 계획 승인 필요" };
  if (project.progress_plan_status === "stale") return { label: "계획 재승인 필요", percent: null, isScoped: false, isEstimate: true, basisLabel: "진행 계획 재승인 필요" };
  if (project.progress_plan_status !== "approved") return { label: "기준 미확인", percent: null, isScoped: false, isEstimate: true, basisLabel: "진행 계획 승인 상태 미확인" };
  if (project.progress_basis === "unscoped") {
    return { label: "산정 전", percent: null, isScoped: false, isEstimate: false, basisLabel: "산정 WBS 없음" };
  }
  if (!isFinitePercent(project.progress_percent) || project.derived_task_count === undefined) {
    return { label: "기준 미확인", percent: null, isScoped: false, isEstimate: true, basisLabel: "승인된 진행률 없음" };
  }
  return {
    label: `${project.progress_percent}%`,
    percent: project.progress_percent,
    isScoped: true,
    isEstimate: false,
    basisLabel: (project.derived_task_count ?? 0) > 0 ? "승인 WBS (자동 구성 포함)" : project.progress_basis === "milestone" ? "승인 마일스톤 가중 WBS" : "승인 WBS 완료 비율"
  };
}

export function milestoneProgressDisplay(milestone: ProjectMilestone): ProgressDisplay {
  if (milestone.total_tasks === 0) return { label: "산정 전", percent: null, isScoped: false, isEstimate: false, basisLabel: "산정 WBS 없음" };
  const isEstimate = (milestone.derived_task_count ?? 0) > 0;
  return {
    label: `${isEstimate ? "참고 " : ""}${milestone.progress_percent}%`,
    percent: milestone.progress_percent,
    isScoped: true,
    isEstimate,
    basisLabel: isEstimate ? "등록 WBS 참고 (자동 구성 포함)" : "등록 WBS 완료 비율"
  };
}

export function scopedProjectAverage(projects: ProjectSummary[]): ScopedProgressAverage {
  const scopedProjects = projects.filter((project) => {
    const progress = projectProgressDisplay(project);
    return progress.isScoped && !progress.isEstimate;
  });
  if (scopedProjects.length === 0) {
    return { label: "산정 전", percent: null, isScoped: false, isEstimate: false, basisLabel: "현재 승인 계획 기준", scopedProjects: 0 };
  }
  const percent = Math.round(scopedProjects.reduce((sum, project) => sum + (project.progress_percent ?? 0), 0) / scopedProjects.length);
  return { label: `${percent}%`, percent, isScoped: true, isEstimate: false, basisLabel: "현재 승인 계획 기준", scopedProjects: scopedProjects.length };
}

export function wbsActivityCounts(tasks: ProjectTask[]): WbsActivityCounts {
  const eligibleTasks = tasks.filter((task) => !isLegacySyntheticCheckpoint(task));
  const countedWbs = eligibleTasks.filter((task) => task.counts_toward_progress).length;
  return {
    allActivities: eligibleTasks.length,
    countedWbs,
    referenceActivities: eligibleTasks.length - countedWbs
  };
}
