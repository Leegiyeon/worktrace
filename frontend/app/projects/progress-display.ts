import type { ProjectSummary, ProjectTask } from "./types";

export type ProgressDisplay = {
  label: string;
  percent: number | null;
  isScoped: boolean;
};

export type ScopedProgressAverage = ProgressDisplay & {
  scopedProjects: number;
};

export type WbsActivityCounts = {
  allActivities: number;
  countedWbs: number;
  referenceActivities: number;
};

export function projectProgressDisplay(project: ProjectSummary): ProgressDisplay {
  if (project.progress_basis === "unscoped") {
    return { label: "산정 전", percent: null, isScoped: false };
  }
  return { label: `${project.progress_percent}%`, percent: project.progress_percent, isScoped: true };
}

export function scopedProjectAverage(projects: ProjectSummary[]): ScopedProgressAverage {
  const scopedProjects = projects.filter((project) => projectProgressDisplay(project).isScoped);
  if (scopedProjects.length === 0) {
    return { label: "산정 전", percent: null, isScoped: false, scopedProjects: 0 };
  }
  const percent = Math.round(scopedProjects.reduce((sum, project) => sum + project.progress_percent, 0) / scopedProjects.length);
  return { label: `${percent}%`, percent, isScoped: true, scopedProjects: scopedProjects.length };
}

export function wbsActivityCounts(tasks: ProjectTask[]): WbsActivityCounts {
  const countedWbs = tasks.filter((task) => task.counts_toward_progress).length;
  return {
    allActivities: tasks.length,
    countedWbs,
    referenceActivities: tasks.length - countedWbs
  };
}
