export type ProjectStatus = "idea" | "review" | "in_progress" | "on_hold" | "done";
export type TaskStatus = "planned" | "in_progress" | "done" | "on_hold";
export type TaskPriority = "low" | "medium" | "high";
export type ProgressBasis = "milestone" | "wbs" | "unscoped";
export type WorkType = "planning" | "meeting" | "research" | "deliverable" | "development" | "testing" | "reporting" | "coordination" | "problem_solving" | "other";
export type OutcomeType = "quantitative" | "qualitative";
export type CareerTargetRole = "IT기획" | "PM" | "AI서비스기획" | "Backend" | "DevOps";
export type MilestoneReviewVerdict = "ready_candidate" | "not_ready" | "needs_review";

export type ProjectSummary = {
  id: string;
  title: string;
  description: string;
  objective: string;
  success_criteria: string;
  status: ProjectStatus;
  role: string;
  total_tasks: number;
  completed_tasks: number;
  remaining_tasks: number;
  milestone_count: number;
  progress_basis: ProgressBasis;
  progress_percent: number;
  updated_at: string;
};

export type ProjectMilestone = {
  id: string;
  project_id: string;
  milestone_key: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  weight: number;
  sort_order: number;
  total_tasks: number;
  completed_tasks: number;
  progress_percent: number;
  updated_at: string;
};

export type MilestoneReview = {
  verdict: MilestoneReviewVerdict;
  confidence: number;
  reasoning_summary: string;
  missing_checks: string[];
  supporting_evidence_ids: string[];
  reviewed_wbs_total: number;
  reviewed_wbs_completed: number;
  evidence_count: number;
};

export type ProjectTask = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  milestone_id: string | null;
  counts_toward_progress: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkLogItem = {
  id: string;
  log_date: string;
  work_type: WorkType;
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

export type ProjectOutcome = {
  id: string;
  project_id: string;
  title: string;
  outcome_type: OutcomeType;
  before_state: string;
  after_state: string;
  metric_name: string;
  metric_value: string | null;
  metric_unit: string;
  evidence_work_log_ids: string[];
  evidence_document_ids: string[];
  resume_ready: boolean;
  created_at: string;
  updated_at: string;
};

export type CareerAsset = {
  id: string;
  project_id: string;
  source_summary: string;
  work_summary: string;
  outcome_summary: string;
  resume_bullets: string;
  career_description: string;
  portfolio_description: string;
  star_answer: string;
  markdown: string;
  generation_method: string;
  created_at: string;
  updated_at: string;
};

export type RepositorySource = {
  id: string;
  project_id: string;
  repository_id: number;
  full_name: string;
  default_branch: string;
  updated_at: string;
};

export type GitHubCommit = {
  id: string;
  sha: string;
  message: string;
  author_name: string;
  committed_at: string | null;
  url: string;
};

export type GitHubDelivery = {
  id: string;
  delivery_id: string;
  event_name: string;
  ref: string;
  status: "processed" | "ignored" | "failed";
  reason: string;
  processing_attempts: number;
  received_at: string;
  last_processed_at: string;
};

export type ProjectGitHubStatus = {
  repository: RepositorySource | null;
  stored_commit_count: number;
  last_success_at: string | null;
  deliveries: GitHubDelivery[];
};

export const projectStatusLabels: Record<ProjectStatus, string> = {
  idea: "아이디어",
  review: "검토",
  in_progress: "진행",
  on_hold: "보류",
  done: "완료"
};

export const taskStatusLabels: Record<TaskStatus, string> = {
  planned: "예정",
  in_progress: "진행",
  done: "완료",
  on_hold: "보류"
};

export const taskPriorityLabels: Record<TaskPriority, string> = {
  low: "낮음",
  medium: "보통",
  high: "높음"
};

export const progressBasisLabels: Record<ProgressBasis, string> = {
  milestone: "마일스톤 기준",
  wbs: "계획 WBS 기준",
  unscoped: "산정 전"
};

export const workTypeLabels: Record<WorkType, string> = {
  planning: "기획",
  meeting: "회의",
  research: "자료조사",
  deliverable: "산출물",
  development: "개발",
  testing: "테스트",
  reporting: "보고",
  coordination: "협의",
  problem_solving: "문제해결",
  other: "기타"
};

export const outcomeTypeLabels: Record<OutcomeType, string> = {
  quantitative: "정량",
  qualitative: "정성"
};
