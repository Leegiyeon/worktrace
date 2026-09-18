export type ProjectStatus = "idea" | "review" | "in_progress" | "on_hold" | "done";
export type ReportType = "daily" | "weekly" | "monthly";
export type ReportActivitySource = "user" | "system" | "milestone_validation";
export type ProgressPlanStatus = "unapproved" | "approved" | "stale";

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

export type ReportActivityTransition = {
  id: string;
  project_id: string;
  project_title: string;
  task_id: string;
  task_title: string;
  current_status: string;
  previous_status: string | null;
  next_status: string;
  source: ReportActivitySource;
  reason: string | null;
  changed_at: string;
  status_version: number;
};

export type ReportActivityCurrentTask = {
  id: string;
  project_id: string;
  project_title: string;
  title: string;
  status: string;
  due_date: string | null;
  source_provider: string | null;
  progress_plan_status: ProgressPlanStatus;
  progress_plan_version: number;
};

export type ReportActivityIssue = {
  id: string;
  project_id: string | null;
  project_title: string;
  title: string;
  blockers: string;
  log_date: string;
  updated_at: string;
};

export type ReportActivityOutcome = {
  id: string;
  project_id: string;
  project_title: string;
  title: string;
  outcome_type: string;
  before_state: string;
  after_state: string;
  metric_name: string;
  metric_value: string | null;
  metric_unit: string;
  updated_at: string;
  evidence_work_log_ids: string[];
  evidence_document_ids: string[];
};

export type ReportActivity = {
  schema_version: "1";
  as_of: string;
  timezone: string;
  start_at: string;
  end_exclusive: string;
  fingerprint: string;
  transitions: ReportActivityTransition[];
  current_tasks: ReportActivityCurrentTask[];
  issues: ReportActivityIssue[];
  outcomes: ReportActivityOutcome[];
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
  activity?: ReportActivity;
};
