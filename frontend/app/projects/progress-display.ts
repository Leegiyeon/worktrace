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

export function projectProgressDisplay(project: Pick<ProjectSummary, "progress_basis" | "progress_percent" | "derived_task_count">): ProgressDisplay {
  if (project.progress_basis === "unscoped") {
    return { label: "산정 전", percent: null, isScoped: false, isEstimate: false, basisLabel: "산정 WBS 없음" };
  }
  if (project.derived_task_count === undefined) {
    return { label: "기준 미확인", percent: null, isScoped: false, isEstimate: true, basisLabel: "WBS 출처 조회 필요" };
  }
  const isEstimate = project.derived_task_count > 0;
  return {
    label: `${isEstimate ? "참고 " : ""}${project.progress_percent}%`,
    percent: project.progress_percent,
    isScoped: true,
    isEstimate,
    basisLabel: isEstimate ? "커밋 기반 자동 구성 포함" : project.progress_basis === "milestone" ? "마일스톤 가중 WBS" : "등록 WBS 완료 비율"
  };
}

export function milestoneProgressDisplay(milestone: ProjectMilestone): ProgressDisplay {
  return projectProgressDisplay({
    progress_basis: milestone.total_tasks === 0 ? "unscoped" : "wbs",
    progress_percent: milestone.progress_percent,
    derived_task_count: milestone.derived_task_count
  });
}

export function scopedProjectAverage(projects: ProjectSummary[]): ScopedProgressAverage {
  const scopedProjects = projects.filter((project) => {
    const progress = projectProgressDisplay(project);
    return progress.isScoped && !progress.isEstimate;
  });
  if (scopedProjects.length === 0) {
    return { label: "산정 전", percent: null, isScoped: false, isEstimate: false, basisLabel: "자동 구성·출처 미확인·미산정 제외", scopedProjects: 0 };
  }
  const percent = Math.round(scopedProjects.reduce((sum, project) => sum + project.progress_percent, 0) / scopedProjects.length);
  return { label: `${percent}%`, percent, isScoped: true, isEstimate: false, basisLabel: "자동 구성·출처 미확인·미산정 제외", scopedProjects: scopedProjects.length };
}

export function wbsActivityCounts(tasks: ProjectTask[]): WbsActivityCounts {
  const countedWbs = tasks.filter((task) => task.counts_toward_progress).length;
  return {
    allActivities: tasks.length,
    countedWbs,
    referenceActivities: tasks.length - countedWbs
  };
}
