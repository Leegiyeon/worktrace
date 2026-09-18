export type ProjectStatus = "idea" | "review" | "in_progress" | "on_hold" | "done";
export type ReportType = "daily" | "weekly" | "monthly";

export type ReportProject = {
  id: string;
  title: string;
  status: ProjectStatus;
  documents: unknown[];
  tasks: unknown[];
  decisions: unknown[];
  risks: unknown[];
  next_checks: string[];
};

export type WorkLogItem = {
  id: string;
  log_date: string;
  work_type: string;
  title: string;
  content: string;
  decisions: string;
  collaborators: string;
  next_actions: string;
  duration_minutes: number;
  blockers: string;
  project_id: string | null;
  project_title: string;
  updated_at: string;
};

export type TaskAlert = {
  project_id: string;
  project_title: string;
  title: string;
  status: string;
  due_date: string | null;
  is_delayed: boolean;
};

export type ProjectProgressCandidate = {
  project_id: string;
  project_title: string;
  current_status: ProjectStatus;
  suggested_progress_percent: number | null;
  progress_percent: number | null;
  progress_basis: "milestone" | "wbs" | "unscoped" | "unknown";
  total_tasks: number | null;
  completed_tasks: number | null;
  derived_task_count: number | null;
  provenance: string;
  as_of: string;
  reason: string;
};

export type MonthlyPerformanceCandidate = {
  project_id: string;
  project_title: string;
  qualitative_improvement: string;
  evidence: string[];
  requires_user_metric_confirmation: boolean;
  resume_ready: boolean;
};

export type WeeklyReportResponse = {
  start_date: string;
  end_date: string;
  markdown: string;
  projects: ReportProject[];
};

export type AutoReportResponse = WeeklyReportResponse & {
  report_type: ReportType;
  work_logs: WorkLogItem[];
  remaining_tasks: TaskAlert[];
  delayed_tasks: TaskAlert[];
  progress_candidates: ProjectProgressCandidate[];
  monthly_performance_candidates: MonthlyPerformanceCandidate[];
};
