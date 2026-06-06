export type ProjectStatus = "idea" | "review" | "in_progress" | "on_hold" | "done";
export type TaskStatus = "planned" | "in_progress" | "done" | "on_hold";
export type TaskPriority = "low" | "medium" | "high";
export type WorkType = "planning" | "meeting" | "research" | "deliverable" | "development" | "testing" | "reporting" | "coordination" | "problem_solving" | "other";
export type OutcomeType = "quantitative" | "qualitative";
export type CareerTargetRole = "IT기획" | "PM" | "AI서비스기획" | "Backend" | "DevOps";

export type ProjectSummary = {
  id: string;
  title: string;
  description: string;
  status: ProjectStatus;
  role: string;
  total_tasks: number;
  completed_tasks: number;
  remaining_tasks: number;
  progress_percent: number;
  updated_at: string;
};

export type ProjectTask = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
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
