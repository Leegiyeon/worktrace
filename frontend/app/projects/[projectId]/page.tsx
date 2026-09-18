"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, use, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { parseApiErrorMessage } from "../../reports/api-error";
import { CareerPanel } from "./CareerPanel";
import { GitHubEvidencePanel } from "./GitHubEvidencePanel";
import { ProjectLifecyclePanel } from "./ProjectLifecyclePanel";
import styles from "./page.module.css";
import type {
  CareerAsset,
  CareerTargetRole,
  GitHubCommit,
  GitHubDelivery,
  ProjectMilestone,
  ProjectOutcome,
  ProjectGitHubStatus,
  ProjectSummary,
  ProjectTask,
  RepositorySource,
  TaskPriority,
  TaskStatus,
  OutcomeType,
  WorkLogItem,
  WorkType
} from "../types";
import {
  outcomeTypeLabels,
  projectStatusLabels,
  serviceStatusLabels,
  taskPriorityLabels,
  taskStatusLabels,
  workTypeLabels
} from "../types";
import { projectProgressDisplay, wbsActivityCounts } from "../progress-display";
import { ProgressEvidence } from "../ProgressEvidence";

type PageProps = {
  params: Promise<{ projectId: string }>;
};

type DetailTab = "overview" | "tasks" | "github" | "logs" | "outcomes" | "career";
type TaskViewMode = "board" | "list" | "calendar";
type DetailLoadFailure = "logs" | "outcomes" | "career" | "commits" | "githubStatus" | "milestones";
type OutcomeStage = "candidates" | "review" | "confirmed";

type TaskForm = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string;
  milestone_id: string;
  counts_toward_progress: boolean;
};

type ProjectForm = {
  title: string;
  description: string;
  role: string;
};

type WorkLogForm = {
  log_date: string;
  work_type: WorkType;
  title: string;
  content: string;
  decisions: string;
  collaborators: string;
  next_actions: string;
  duration_minutes: string;
  blockers: string;
};

type OutcomeForm = {
  title: string;
  outcome_type: OutcomeType;
  before_state: string;
  after_state: string;
  metric_name: string;
  metric_value: string;
  metric_unit: string;
  evidence_work_log_ids: string[];
  resume_ready: boolean;
};

type OutcomeCandidate = OutcomeForm & {
  id: string;
  evidence: string[];
  source: "task" | "work_log";
};

const tabs: { id: DetailTab; label: string }[] = [
  { id: "overview", label: "현황" },
  { id: "tasks", label: "WBS · 이슈" },
  { id: "github", label: "GitHub 근거" },
  { id: "logs", label: "업무 로그" },
  { id: "outcomes", label: "성과" },
  { id: "career", label: "경력 자산" }
];

const taskStatusOrder: TaskStatus[] = ["planned", "in_progress", "done", "on_hold"];
const priorityOrder: Record<TaskPriority, number> = { high: 1, medium: 2, low: 3 };
const taskViewModes: TaskViewMode[] = ["board", "list", "calendar"];
const taskSortKeys = ["due_date", "priority", "created_at", "status", "progress_scope"] as const;
type TaskSortKey = (typeof taskSortKeys)[number];
const initialTaskForm: TaskForm = {
  title: "",
  description: "",
  status: "planned",
  priority: "medium",
  due_date: "",
  milestone_id: "",
  counts_toward_progress: true
};

function isDetailTab(value: string | null): value is DetailTab {
  return tabs.some((tab) => tab.id === value);
}

function isTaskViewMode(value: string | null): value is TaskViewMode {
  return taskViewModes.some((mode) => mode === value);
}

function isTaskStatusFilter(value: string | null): value is TaskStatus | "all" {
  return value === "all" || taskStatusOrder.some((status) => status === value);
}

function isTaskPriorityFilter(value: string | null): value is TaskPriority | "all" {
  return value === "all" || Object.keys(taskPriorityLabels).some((priority) => priority === value);
}

function isIssueFilter(value: string | null): value is "all" | "issue" | "normal" {
  return value === "all" || value === "issue" || value === "normal";
}

function isTaskSortKey(value: string | null): value is TaskSortKey {
  return taskSortKeys.some((key) => key === value);
}

const initialProjectForm: ProjectForm = {
  title: "",
  description: "",
  role: ""
};

function createInitialWorkLogForm(): WorkLogForm {
  return {
    log_date: formatDateKey(new Date()),
    work_type: "other",
    title: "",
    content: "",
    decisions: "",
    collaborators: "",
    next_actions: "",
    duration_minutes: "0",
    blockers: ""
  };
}

function createInitialOutcomeForm(): OutcomeForm {
  return {
    title: "",
    outcome_type: "qualitative",
    before_state: "",
    after_state: "",
    metric_name: "",
    metric_value: "",
    metric_unit: "",
    evidence_work_log_ids: [],
    resume_ready: false
  };
}

function isDelayed(task: ProjectTask) {
  if (!task.due_date || task.status === "done") return false;
  return new Date(`${task.due_date}T23:59:59`) < new Date();
}

function formatDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDeliveryTime(value: string | null) {
  if (!value) return "성공 기록 없음";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function deliveryStatusLabel(status: GitHubDelivery["status"]) {
  return { processed: "성공", ignored: "무시", failed: "실패" }[status];
}

function deliveryReasonLabel(delivery: GitHubDelivery) {
  if (!delivery.reason) return `${delivery.processing_attempts}회 처리`;
  return {
    unsupported_event: "지원하지 않는 이벤트",
    non_main_ref: "main 이외 브랜치",
    non_default_ref: "기준 브랜치 외 push",
    repository_not_linked: "연결되지 않은 저장소",
    duplicate_delivery: "중복 전달"
  }[delivery.reason] ?? delivery.reason;
}

function parseDueDate(date: string) {
  return new Date(`${date}T00:00:00`);
}

function getWeekRange() {
  const start = new Date();
  const day = start.getDay();
  const daysFromMonday = day === 0 ? 6 : day - 1;
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - daysFromMonday);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  end.setHours(23, 59, 59, 999);
  return { start, end };
}

function getMonthCells(baseDate = new Date()) {
  const year = baseDate.getFullYear();
  const month = baseDate.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const leadingBlanks = firstDay.getDay();
  const cells: (Date | null)[] = Array.from({ length: leadingBlanks }, () => null);

  for (let day = 1; day <= lastDay.getDate(); day += 1) {
    cells.push(new Date(year, month, day));
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  return cells;
}

function sortTasks(tasks: ProjectTask[]) {
  return [...tasks].sort((a, b) => {
    const statusDiff = taskStatusOrder.indexOf(a.status) - taskStatusOrder.indexOf(b.status);
    if (statusDiff !== 0) return statusDiff;
    const priorityDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
    if (priorityDiff !== 0) return priorityDiff;
    return (a.due_date ?? "9999-12-31").localeCompare(b.due_date ?? "9999-12-31");
  });
}

function compactEvidenceText(value: string, maxLength = 150) {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function logEvidenceText(log: WorkLogItem) {
  return `${log.log_date} · ${workTypeLabels[log.work_type]} · ${log.title}`;
}

function logContainsTask(log: WorkLogItem, task: ProjectTask) {
  const taskTitle = task.title.trim().toLocaleLowerCase();
  if (!taskTitle) return false;
  return [log.title, log.content, log.decisions, log.next_actions]
    .some((value) => value.toLocaleLowerCase().includes(taskTitle));
}

function createLogCandidate(log: WorkLogItem): OutcomeCandidate {
  const afterState = [log.content, log.decisions ? `결정: ${log.decisions}` : "", log.next_actions ? `다음 액션: ${log.next_actions}` : ""]
    .filter(Boolean)
    .join(" / ");

  return {
    id: `log-${log.id}`,
    title: `${log.title} 성과 후보`,
    outcome_type: "qualitative",
    before_state: log.blockers ? `블로커: ${log.blockers}` : "",
    after_state: compactEvidenceText(afterState || log.title),
    metric_name: "",
    metric_value: "",
    metric_unit: "",
    evidence_work_log_ids: [log.id],
    resume_ready: false,
    evidence: [logEvidenceText(log)],
    source: "work_log"
  };
}

function createTaskCandidate(task: ProjectTask, evidenceLogs: WorkLogItem[]): OutcomeCandidate {
  return {
    id: `task-${task.id}`,
    title: `${task.title} 완료 성과`,
    outcome_type: "qualitative",
    before_state: task.description ? compactEvidenceText(task.description) : "",
    after_state: `완료 업무: ${task.title}`,
    metric_name: "",
    metric_value: "",
    metric_unit: "",
    evidence_work_log_ids: evidenceLogs.map((log) => log.id),
    resume_ready: false,
    evidence: [`완료 업무: ${task.title}`, ...evidenceLogs.map(logEvidenceText)],
    source: "task"
  };
}

function buildOutcomeCandidates(logs: WorkLogItem[], tasks: ProjectTask[], outcomes: ProjectOutcome[]) {
  const usedLogIds = new Set(outcomes.flatMap((outcome) => outcome.evidence_work_log_ids));
  const existingTitles = new Set(outcomes.map((outcome) => outcome.title.trim().toLocaleLowerCase()));
  const sortedLogs = [...logs].sort((a, b) => b.log_date.localeCompare(a.log_date));
  const candidates: OutcomeCandidate[] = [];

  for (const task of tasks.filter((item) => item.status === "done")) {
    const evidenceLogs = sortedLogs.filter((log) => logContainsTask(log, task) && !usedLogIds.has(log.id)).slice(0, 3);
    if (evidenceLogs.length === 0) continue;
    const candidate = createTaskCandidate(task, evidenceLogs);
    if (!existingTitles.has(candidate.title.trim().toLocaleLowerCase())) {
      candidates.push(candidate);
    }
  }

  for (const log of sortedLogs) {
    if (usedLogIds.has(log.id)) continue;
    const candidate = createLogCandidate(log);
    if (!existingTitles.has(candidate.title.trim().toLocaleLowerCase())) {
      candidates.push(candidate);
    }
  }

  return candidates.slice(0, 6);
}

export default function ProjectDetailPage({ params }: PageProps) {
  const { projectId } = use(params);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const viewParam = searchParams.get("view");
  const statusParam = searchParams.get("status");
  const priorityParam = searchParams.get("priority");
  const issueParam = searchParams.get("issue");
  const sortParam = searchParams.get("sort");
  const activeTab: DetailTab = isDetailTab(tabParam) ? tabParam : "overview";
  const taskViewMode: TaskViewMode = isTaskViewMode(viewParam) ? viewParam : "list";
  const taskStatusFilter: TaskStatus | "all" = isTaskStatusFilter(statusParam) ? statusParam : "all";
  const taskPriorityFilter: TaskPriority | "all" = isTaskPriorityFilter(priorityParam) ? priorityParam : "all";
  const taskIssueFilter: "all" | "issue" | "normal" = isIssueFilter(issueParam) ? issueParam : "all";
  const taskSortKey: TaskSortKey = isTaskSortKey(sortParam) ? sortParam : "due_date";
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [milestones, setMilestones] = useState<ProjectMilestone[]>([]);
  const [workLogs, setWorkLogs] = useState<WorkLogItem[]>([]);
  const [outcomes, setOutcomes] = useState<ProjectOutcome[]>([]);
  const [careerAssets, setCareerAssets] = useState<CareerAsset[]>([]);
  const [repository, setRepository] = useState<RepositorySource | null>(null);
  const [commits, setCommits] = useState<GitHubCommit[]>([]);
  const [githubStatus, setGitHubStatus] = useState<ProjectGitHubStatus | null>(null);
  const [repositoryForm, setRepositoryForm] = useState({ repository_id: "", full_name: "", default_branch: "main" });
  const [projectForm, setProjectForm] = useState<ProjectForm>(initialProjectForm);
  const [taskForm, setTaskForm] = useState<TaskForm>(initialTaskForm);
  const [logForm, setLogForm] = useState<WorkLogForm>(() => createInitialWorkLogForm());
  const [outcomeForm, setOutcomeForm] = useState<OutcomeForm>(() => createInitialOutcomeForm());
  const [outcomeBaseline, setOutcomeBaseline] = useState<OutcomeForm>(() => createInitialOutcomeForm());
  const [isOutcomeFormVisible, setIsOutcomeFormVisible] = useState(false);
  const [outcomeStage, setOutcomeStage] = useState<OutcomeStage>("review");
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [isTaskFormVisible, setIsTaskFormVisible] = useState(false);
  const [editingLogId, setEditingLogId] = useState<string | null>(null);
  const [isLogFormVisible, setIsLogFormVisible] = useState(false);
  const [editingOutcomeId, setEditingOutcomeId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingProject, setIsSavingProject] = useState(false);
  const [isSavingTask, setIsSavingTask] = useState(false);
  const [isSavingLog, setIsSavingLog] = useState(false);
  const [isSavingOutcome, setIsSavingOutcome] = useState(false);
  const [isGeneratingCareer, setIsGeneratingCareer] = useState(false);
  const [isSavingRepository, setIsSavingRepository] = useState(false);
  const [reprocessingDeliveryId, setReprocessingDeliveryId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loadFailures, setLoadFailures] = useState<DetailLoadFailure[]>([]);
  const [careerMessage, setCareerMessage] = useState("");
  const planningRefreshSequence = useRef(0);

  useEffect(() => {
    return () => { planningRefreshSequence.current += 1; };
  }, [projectId]);

  const updateProjectDetailUrl = useCallback((updates: Partial<Record<"tab" | "view" | "status" | "priority" | "issue" | "sort", string>>) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (!value || (key === "tab" && value === "overview") || (key === "view" && value === "list") || value === "all" || (key === "sort" && value === "due_date")) {
        nextParams.delete(key);
      } else {
        nextParams.set(key, value);
      }
    }
    const queryString = nextParams.toString();
    router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }, [pathname, router, searchParams]);

  function setActiveDetailTab(tab: DetailTab) {
    updateProjectDetailUrl({ tab });
  }

  function setTaskView(view: TaskViewMode) {
    updateProjectDetailUrl({ tab: "tasks", view });
  }

  function showNewTaskForm() {
    setSuccessMessage("");
    setIsTaskFormVisible(true);
    updateProjectDetailUrl({ tab: "tasks" });
  }

  function hideTaskForm() {
    setIsTaskFormVisible(false);
  }

  function cancelTaskForm() {
    setEditingTaskId(null);
    setTaskForm(initialTaskForm);
    setIsTaskFormVisible(false);
  }

  const groupedTasks = useMemo(() => {
    return taskStatusOrder.map((status) => ({
      status,
      label: taskStatusLabels[status],
      items: sortTasks(tasks.filter((task) => task.status === status))
    }));
  }, [tasks]);

  const dashboard = useMemo(() => {
    const delayedTasks = tasks.filter(isDelayed);
    const activityCounts = wbsActivityCounts(tasks);
    const sortedTasks = sortTasks(tasks);
    const dueTasks = sortedTasks.filter((task) => task.due_date);
    const { start: weekStart, end: weekEnd } = getWeekRange();
    const thisWeekDueTasks = dueTasks.filter((task) => {
      if (!task.due_date) return false;
      const dueDate = parseDueDate(task.due_date);
      return dueDate >= weekStart && dueDate <= weekEnd;
    });
    const recentLogs = [...workLogs].sort((a, b) => b.log_date.localeCompare(a.log_date)).slice(0, 5);
    const latestOutcomes = [...outcomes].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5);
    const quantitativeOutcomes = outcomes.filter((outcome) => outcome.outcome_type === "quantitative").length;
    const resumeReadyOutcomes = outcomes.filter((outcome) => outcome.resume_ready).length;
    return { activityCounts, delayedTasks, dueTasks, latestOutcomes, quantitativeOutcomes, recentLogs, resumeReadyOutcomes, sortedTasks, thisWeekDueTasks };
  }, [outcomes, tasks, workLogs]);

  const loadProject = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const [projectResponse, tasksResponse, milestonesResponse, logsResponse, outcomesResponse, careerResponse, repositoryResponse, commitsResponse, githubStatusResponse] = await Promise.all([
        fetch(`/api/projects/${projectId}`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/tasks`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/milestones`, { cache: "no-store" }).catch(() => null),
        fetch(`/api/work-logs?project_id=${projectId}`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/outcomes`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/career-assets`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/repository`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/commits`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/github-status`, { cache: "no-store" })
      ]);
      if (!projectResponse.ok) {
        const detail = await projectResponse.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      if (!tasksResponse.ok) {
        const detail = await tasksResponse.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      const nextProject = (await projectResponse.json()) as ProjectSummary;
      setProject(nextProject);
      setProjectForm({
        title: nextProject.title,
        description: nextProject.description,
        role: nextProject.role
      });
      setTasks((await tasksResponse.json()) as ProjectTask[]);
      const failures: DetailLoadFailure[] = [];
      if (milestonesResponse?.ok) setMilestones((await milestonesResponse.json()) as ProjectMilestone[]);
      else failures.push("milestones");
      if (logsResponse.ok) setWorkLogs((await logsResponse.json()) as WorkLogItem[]);
      else failures.push("logs");
      if (outcomesResponse.ok) setOutcomes((await outcomesResponse.json()) as ProjectOutcome[]);
      else failures.push("outcomes");
      if (careerResponse.ok) setCareerAssets((await careerResponse.json()) as CareerAsset[]);
      else failures.push("career");
      if (repositoryResponse.ok) {
        const nextRepository = (await repositoryResponse.json()) as RepositorySource | null;
        setRepository(nextRepository);
        if (nextRepository) setRepositoryForm({ repository_id: String(nextRepository.repository_id), full_name: nextRepository.full_name, default_branch: nextRepository.default_branch });
      }
      if (commitsResponse.ok) setCommits((await commitsResponse.json()) as GitHubCommit[]);
      else failures.push("commits");
      if (githubStatusResponse.ok) setGitHubStatus((await githubStatusResponse.json()) as ProjectGitHubStatus);
      else failures.push("githubStatus");
      setLoadFailures(failures);
    } catch (error) {
      setLoadFailures([]);
      setErrorMessage(error instanceof Error ? error.message : "프로젝트 상세를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  async function refreshPlanningData() {
    const sequence = ++planningRefreshSequence.current;
    const responses = await Promise.all([
      fetch(`/api/projects/${projectId}`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/tasks`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/milestones`, { cache: "no-store" })
    ]);
    if (responses.some((response) => !response.ok)) throw new Error("WBS 현황 조회 실패");
    const [nextProject, nextTasks, nextMilestones] = await Promise.all(responses.map((response) => response.json()));
    if (sequence !== planningRefreshSequence.current) return;
    setProject(nextProject as ProjectSummary);
    setTasks(nextTasks as ProjectTask[]);
    setMilestones(nextMilestones as ProjectMilestone[]);
  }

  async function handleSaveRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const repositoryId = Number(repositoryForm.repository_id);
    if (!Number.isSafeInteger(repositoryId) || repositoryId <= 0 || !repositoryForm.full_name.includes("/")) {
      setErrorMessage("GitHub 저장소 ID와 owner/repository 이름을 확인하세요.");
      return;
    }
    setIsSavingRepository(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/repository`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...repositoryForm, repository_id: repositoryId })
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "저장소를 연결하지 못했습니다."));
      }
      setRepository((await response.json()) as RepositorySource);
      setSuccessMessage("GitHub 저장소 연결 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "저장소를 연결하지 못했습니다.");
    } finally {
      setIsSavingRepository(false);
    }
  }

  async function handleReprocessDelivery(delivery: GitHubDelivery) {
    setReprocessingDeliveryId(delivery.delivery_id);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(
        `/api/projects/${projectId}/github-deliveries/${encodeURIComponent(delivery.delivery_id)}/reprocess`,
        { method: "POST" }
      );
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "전달을 재처리하지 못했습니다."));
      }
      await loadProject();
      setSuccessMessage("GitHub 전달 재처리 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "전달을 재처리하지 못했습니다.");
    } finally {
      setReprocessingDeliveryId(null);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadProject();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadProject]);

  async function handleSaveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    if (!projectForm.title.trim()) {
      setErrorMessage("프로젝트명을 입력하세요.");
      return;
    }

    setIsSavingProject(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projectForm)
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      await loadProject();
      setSuccessMessage("프로젝트 수정 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "프로젝트를 저장하지 못했습니다.");
    } finally {
      setIsSavingProject(false);
    }
  }

  async function handleDeleteProject() {
    if (!window.confirm("프로젝트와 연결된 업무를 삭제할까요?")) return;

    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      router.push("/projects");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "프로젝트를 삭제하지 못했습니다.");
    }
  }

  async function handleSaveTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    if (!taskForm.title.trim()) {
      setErrorMessage("업무명을 입력하세요.");
      return;
    }

    const payload = { ...taskForm, due_date: taskForm.due_date || null, milestone_id: taskForm.milestone_id || null };
    const success = editingTaskId ? "업무 수정 완료" : "업무 추가 완료";
    setIsSavingTask(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(
        editingTaskId ? `/api/projects/${projectId}/tasks/${editingTaskId}` : `/api/projects/${projectId}/tasks`,
        {
          method: editingTaskId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }
      );
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      setTaskForm(initialTaskForm);
      setEditingTaskId(null);
      setIsTaskFormVisible(false);
      await loadProject();
      setSuccessMessage(success);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무를 저장하지 못했습니다.");
    } finally {
      setIsSavingTask(false);
    }
  }

  function startEdit(task: ProjectTask) {
    setSuccessMessage("");
    setEditingTaskId(task.id);
    setTaskForm({
      title: task.title,
      description: task.description,
      status: task.status,
      priority: task.priority,
      due_date: task.due_date ?? "",
      milestone_id: task.milestone_id ?? "",
      counts_toward_progress: task.counts_toward_progress
    });
    setIsTaskFormVisible(true);
    setActiveDetailTab("tasks");
  }

  async function updateStatus(task: ProjectTask, status: TaskStatus) {
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      await loadProject();
      setSuccessMessage("업무 상태 변경 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무 상태를 변경하지 못했습니다.");
    }
  }

  async function deleteTask(task: ProjectTask) {
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/tasks/${task.id}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      if (editingTaskId === task.id) {
        setEditingTaskId(null);
        setIsTaskFormVisible(false);
        setTaskForm(initialTaskForm);
      }
      await loadProject();
      setSuccessMessage("업무 삭제 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무를 삭제하지 못했습니다.");
    }
  }

  async function handleSaveLog(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    if (!logForm.title.trim()) {
      setErrorMessage("로그 제목을 입력하세요.");
      return;
    }

    const durationMinutes = Number.parseInt(logForm.duration_minutes || "0", 10);
    const payload = {
      ...logForm,
      title: logForm.title.trim(),
      duration_minutes: Number.isFinite(durationMinutes) && durationMinutes > 0 ? durationMinutes : 0,
      project_id: projectId
    };
    const success = editingLogId ? "업무 로그 수정 완료" : "업무 로그 추가 완료";

    setIsSavingLog(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(editingLogId ? `/api/work-logs/${editingLogId}` : "/api/work-logs", {
        method: editingLogId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      const savedLog = (await response.json()) as WorkLogItem;
      setWorkLogs((current) => editingLogId
        ? current.map((log) => log.id === savedLog.id ? savedLog : log)
        : [...current, savedLog]
      );
      setLogForm(createInitialWorkLogForm());
      setEditingLogId(null);
      setIsLogFormVisible(false);
      setSuccessMessage(success);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무 로그를 저장하지 못했습니다.");
    } finally {
      setIsSavingLog(false);
    }
  }

  function startEditLog(log: WorkLogItem) {
    setSuccessMessage("");
    setEditingLogId(log.id);
    setLogForm({
      log_date: log.log_date,
      work_type: log.work_type,
      title: log.title,
      content: log.content,
      decisions: log.decisions,
      collaborators: log.collaborators,
      next_actions: log.next_actions,
      duration_minutes: String(log.duration_minutes),
      blockers: log.blockers
    });
    setIsLogFormVisible(true);
    setActiveDetailTab("logs");
  }

  function showNewLogForm() {
    setSuccessMessage("");
    setIsLogFormVisible(true);
    setActiveDetailTab("logs");
  }

  function hideLogForm() {
    setIsLogFormVisible(false);
  }

  function cancelLogForm() {
    setEditingLogId(null);
    setLogForm(createInitialWorkLogForm());
    setIsLogFormVisible(false);
  }

  async function deleteLog(log: WorkLogItem) {
    if (!window.confirm("업무 로그를 삭제할까요?")) return;
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/work-logs/${log.id}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      if (editingLogId === log.id) {
        setEditingLogId(null);
        setLogForm(createInitialWorkLogForm());
        setIsLogFormVisible(false);
      }
      setWorkLogs((current) => current.filter((item) => item.id !== log.id));
      setSuccessMessage("업무 로그 삭제 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무 로그를 삭제하지 못했습니다.");
    }
  }

  async function handleSaveOutcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSavingOutcome) return;
    setSuccessMessage("");
    if (!outcomeForm.title.trim()) {
      setErrorMessage("개선 항목을 입력하세요.");
      return;
    }
    if (outcomeForm.outcome_type === "quantitative" && !outcomeForm.metric_value.trim()) {
      setErrorMessage("정량 성과는 수치를 입력하세요.");
      return;
    }
    const existingOutcome = outcomes.find((outcome) => outcome.id === editingOutcomeId);
    if (outcomeForm.resume_ready && !outcomeForm.evidence_work_log_ids.some((id) => workLogs.some((log) => log.id === id)) && !existingOutcome?.evidence_document_ids.length) {
      setErrorMessage("이력서 반영을 확정하려면 근거를 연결하세요.");
      return;
    }

    const payload = {
      title: outcomeForm.title.trim(),
      outcome_type: outcomeForm.outcome_type,
      before_state: outcomeForm.before_state.trim(),
      after_state: outcomeForm.after_state.trim(),
      metric_name: outcomeForm.metric_name.trim(),
      metric_value: outcomeForm.metric_value.trim() ? outcomeForm.metric_value.trim() : null,
      metric_unit: outcomeForm.metric_unit.trim(),
      evidence_work_log_ids: outcomeForm.evidence_work_log_ids,
      evidence_document_ids: existingOutcome?.evidence_document_ids ?? [],
      resume_ready: outcomeForm.resume_ready
    };
    const success = outcomeForm.resume_ready ? "이력서 반영 확정 완료" : "검토 중 성과 저장 완료";

    setIsSavingOutcome(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(
        editingOutcomeId ? `/api/projects/${projectId}/outcomes/${editingOutcomeId}` : `/api/projects/${projectId}/outcomes`,
        {
          method: editingOutcomeId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }
      );
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      const savedOutcome = (await response.json()) as ProjectOutcome;
      setOutcomes((current) => editingOutcomeId
        ? current.map((outcome) => outcome.id === savedOutcome.id ? savedOutcome : outcome)
        : [savedOutcome, ...current]);
      setOutcomeStage(savedOutcome.resume_ready ? "confirmed" : "review");
      setIsOutcomeFormVisible(false);
      setOutcomeForm(createInitialOutcomeForm());
      setOutcomeBaseline(createInitialOutcomeForm());
      setEditingOutcomeId(null);
      setSuccessMessage(success);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "성과를 저장하지 못했습니다.");
    } finally {
      setIsSavingOutcome(false);
    }
  }

  function confirmOutcomeReplacement(message = "작성 중인 성과를 버리고 다른 성과를 검토할까요?") {
    if (isSavingOutcome) return false;
    return JSON.stringify(outcomeForm) === JSON.stringify(outcomeBaseline)
      || window.confirm(message);
  }

  function cancelOutcomeEdit() {
    if (!confirmOutcomeReplacement("작성 중인 성과 변경을 버릴까요?")) return;
    setOutcomeForm(createInitialOutcomeForm());
    setOutcomeBaseline(createInitialOutcomeForm());
    setEditingOutcomeId(null);
    setIsOutcomeFormVisible(false);
  }

  function startEditOutcome(outcome: ProjectOutcome) {
    if (!confirmOutcomeReplacement()) return;
    setSuccessMessage("");
    setErrorMessage("");
    setEditingOutcomeId(outcome.id);
    const form: OutcomeForm = {
      title: outcome.title,
      outcome_type: outcome.outcome_type,
      before_state: outcome.before_state,
      after_state: outcome.after_state,
      metric_name: outcome.metric_name,
      metric_value: outcome.metric_value ?? "",
      metric_unit: outcome.metric_unit,
      evidence_work_log_ids: outcome.evidence_work_log_ids,
      resume_ready: outcome.resume_ready
    };
    setOutcomeForm(form);
    setOutcomeBaseline(form);
    setIsOutcomeFormVisible(true);
    setActiveDetailTab("outcomes");
  }

  function applyOutcomeCandidate(candidate: OutcomeCandidate) {
    if (!confirmOutcomeReplacement()) return;
    setSuccessMessage("");
    setErrorMessage("");
    setEditingOutcomeId(null);
    setOutcomeBaseline(createInitialOutcomeForm());
    setOutcomeForm({
      title: candidate.title,
      outcome_type: candidate.outcome_type,
      before_state: candidate.before_state,
      after_state: candidate.after_state,
      metric_name: candidate.metric_name,
      metric_value: "",
      metric_unit: candidate.metric_unit,
      evidence_work_log_ids: candidate.evidence_work_log_ids,
      resume_ready: false
    });
    setIsOutcomeFormVisible(true);
    setActiveDetailTab("outcomes");
  }

  async function deleteOutcome(outcome: ProjectOutcome) {
    if (isSavingOutcome) return;
    if (!window.confirm("성과를 삭제할까요?")) return;
    setIsSavingOutcome(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/outcomes/${outcome.id}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail));
      }
      if (editingOutcomeId === outcome.id) {
        setEditingOutcomeId(null);
        setOutcomeForm(createInitialOutcomeForm());
        setOutcomeBaseline(createInitialOutcomeForm());
        setIsOutcomeFormVisible(false);
      }
      setOutcomes((current) => current.filter((item) => item.id !== outcome.id));
      setSuccessMessage("성과 삭제 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "성과를 삭제하지 못했습니다.");
    } finally {
      setIsSavingOutcome(false);
    }
  }

  async function handleGenerateCareerAsset(targetRole: CareerTargetRole) {
    setIsGeneratingCareer(true);
    setErrorMessage("");
    setSuccessMessage("");
    setCareerMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/career-assets/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_role: targetRole })
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "경력 자산을 생성하지 못했습니다."));
      }
      const generatedAsset = (await response.json()) as CareerAsset;
      setCareerAssets((current) => [generatedAsset, ...current.filter((asset) => asset.id !== generatedAsset.id)]);
      setCareerMessage("경력 자산 생성 완료");
      return generatedAsset;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "경력 자산을 생성하지 못했습니다.");
      return null;
    } finally {
      setIsGeneratingCareer(false);
    }
  }

  function handleCareerAssetUpdated(updatedAsset: CareerAsset) {
    setCareerAssets((current) => current.map((asset) => asset.id === updatedAsset.id ? updatedAsset : asset));
  }

  return (
    <main className={`page-shell project-page project-detail-page ${styles.projectDetailPage}`}>
      <div className="dashboard-topbar compact-topbar">
        <div>
          <Link className="text-link" href="/projects">← 프로젝트</Link>
          <h1>{project?.title ?? "프로젝트"}</h1>
        </div>
        {project ? (
          <div className="task-meta">
            <span className="meta-pill status-navy">{projectStatusLabels[project.status]}</span>
            <span className="meta-pill">{serviceStatusLabels[project.service_status ?? "unknown"]}</span>
            <span className="meta-pill">진척 {projectProgressDisplay(project).label}</span>
            <span className="meta-pill">잔여 {project.remaining_tasks}</span>
            <span className="meta-pill priority-high">지연 {dashboard.delayedTasks.length}</span>
          </div>
        ) : null}
      </div>

      {isLoading ? <section aria-live="polite" className="panel muted">로딩 중</section> : null}
      {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
      {loadFailures.length > 0 ? (
        <div className="alert error data-load-alert" role="alert">
          <span>
            일부 데이터를 불러오지 못했습니다: {loadFailures.map((failure) => ({ logs: "업무 로그", outcomes: "성과", career: "경력 자산", commits: "커밋 근거", githubStatus: "GitHub 수집 상태", milestones: "마일스톤" })[failure]).join(", ")}.
          </span>
          <button className="secondary-button" disabled={isLoading} type="button" onClick={() => void loadProject()}>
            다시 시도
          </button>
        </div>
      ) : null}
      {successMessage ? <div aria-live="polite" className="alert success" role="status">{successMessage}</div> : null}

      {project ? (
        <>
          <nav className="tab-nav" aria-label="프로젝트 상세 탭" role="tablist">
            {tabs.map((tab) => (
              <button
                aria-controls={`panel-${tab.id}`}
                aria-selected={activeTab === tab.id}
                className={activeTab === tab.id ? "active" : ""}
                id={`tab-${tab.id}`}
                key={tab.id}
                role="tab"
                type="button"
                onClick={() => setActiveDetailTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          <div hidden={activeTab !== "overview"}>
            <ProjectLifecyclePanel key={projectId} project={project} onSaved={(value) => setProject((current) => current ? { ...current, status: value.status, service_status: value.service_status, development_ended_on: value.development_ended_on, lifecycle_version: value.lifecycle_version, lifecycle_confirmed_at: value.lifecycle_confirmed_at } : current)} />
          </div>

          {activeTab === "overview" ? (
            <section aria-labelledby="tab-overview" className="overview-dashboard" id="panel-overview" role="tabpanel">
              <section className="summary-grid dashboard-metrics" aria-label="프로젝트 지표">
                <div className="metric-card"><span>진척도</span><strong>{projectProgressDisplay(project).label}</strong></div>
                <div className="metric-card"><span>산정 WBS / 전체 활동</span><strong>{dashboard.activityCounts.countedWbs} / {dashboard.activityCounts.allActivities}</strong></div>
                <div className="metric-card"><span>조회된 커밋 근거</span><strong>{loadFailures.includes("commits") ? "-" : commits.length}</strong></div>
                <div className="metric-card"><span>성과</span><strong>{loadFailures.includes("outcomes") ? "-" : outcomes.length}</strong></div>
              </section>
              <section className="panel">
                <div className="panel-title-row"><h2>진척</h2><span className="count-badge">{projectStatusLabels[project.status]}</span></div>
                <ProgressEvidence project={project} />
                <div className="overview-bars">
                  {projectProgressDisplay(project).percent === null ? <div><span>WBS 완료율</span><strong>{projectProgressDisplay(project).label}</strong></div> : <div><span>{projectProgressDisplay(project).isEstimate ? "참고 완료율" : "WBS 완료율"}</span><div className="progress-row-bar"><span style={{ width: `${projectProgressDisplay(project).percent}%` }} /></div></div>}
                  {groupedTasks.map((group) => <div className="status-bar-row" key={group.status}><span>{group.label}</span><div className="status-bar-track"><i style={{ width: `${tasks.length ? (group.items.length / tasks.length) * 100 : 0}%` }} /></div><strong>{group.items.length}</strong></div>)}
                </div>
              </section>
              <section className="panel">
                <div className="panel-title-row"><h2>이번 주 마감</h2><span className="count-badge">{dashboard.thisWeekDueTasks.length}개</span></div>
                <DueTaskList empty="마감 없음" tasks={dashboard.thisWeekDueTasks.slice(0, 5)} />
              </section>
              <section className="panel">
                <div className="panel-title-row"><h2>지연 업무</h2><span className="count-badge danger-count">{dashboard.delayedTasks.length}개</span></div>
                <DueTaskList empty="지연 없음" tasks={dashboard.delayedTasks.slice(0, 5)} />
              </section>
              <section className="panel">
                <div className="panel-title-row"><h2>최근 로그</h2><span className="count-badge">{loadFailures.includes("logs") ? "-" : `${dashboard.recentLogs.length}개`}</span></div>
                {loadFailures.includes("logs") ? <div className="empty-state">업무 로그를 불러오지 못했습니다.</div> : <MiniLogList logs={dashboard.recentLogs} />}
              </section>
              <section className="panel">
                <div className="panel-title-row"><h2>최근 성과</h2><span className="count-badge">{loadFailures.includes("outcomes") ? "-" : `${dashboard.latestOutcomes.length}개`}</span></div>
                {loadFailures.includes("outcomes") ? <div className="empty-state">성과를 불러오지 못했습니다.</div> : <MiniOutcomeList outcomes={dashboard.latestOutcomes} />}
              </section>
              <section className="panel commit-evidence-panel">
                <div className="panel-title-row"><h2>최근 커밋 근거</h2><span className="count-badge">{loadFailures.includes("commits") ? "-" : `${commits.length}개`}</span></div>
                {repository ? <span className="meta-pill status-navy">{repository.full_name} · {repository.default_branch}</span> : null}
                {!loadFailures.includes("commits") && commits.length === 0 ? <div className="empty-state">수집된 main 커밋 없음</div> : null}
                <div className="dense-list">
                  {commits.slice(0, 6).map((commit) => <a className="dense-list-row" href={commit.url} key={commit.id} rel="noreferrer" target="_blank"><span>{commit.message.split("\n")[0]}</span><small>{commit.author_name || "작성자 미상"}</small><b>{commit.committed_at?.slice(0, 10) ?? commit.sha.slice(0, 7)}</b></a>)}
                </div>
              </section>
              <section className="panel github-operations-panel">
                <div className="panel-title-row">
                  <h2>GitHub 수집 상태</h2>
                  <span className="count-badge">{githubStatus?.deliveries.length ?? 0}건</span>
                </div>
                {loadFailures.includes("githubStatus") ? <div className="empty-state">수집 상태를 불러오지 못했습니다.</div> : null}
                {!loadFailures.includes("githubStatus") && !githubStatus?.repository ? <div className="empty-state">연결된 저장소 없음</div> : null}
                {githubStatus?.repository ? (
                  <>
                    <div className="github-status-summary">
                      <div><span>저장 커밋</span><strong>{githubStatus.stored_commit_count.toLocaleString()}개</strong></div>
                      <div><span>마지막 성공</span><strong>{formatDeliveryTime(githubStatus.last_success_at)}</strong></div>
                    </div>
                    {githubStatus.deliveries.length === 0 ? <div className="empty-state">수신된 webhook 없음</div> : (
                      <div className="delivery-list">
                        {githubStatus.deliveries.slice(0, 8).map((delivery) => (
                          <article className="delivery-row" key={delivery.id}>
                            <div>
                              <strong>{delivery.event_name} · {delivery.ref.replace("refs/heads/", "") || "ref 없음"}</strong>
                              <small>{formatDeliveryTime(delivery.received_at)} · {deliveryReasonLabel(delivery)}</small>
                            </div>
                            <span className={`meta-pill delivery-${delivery.status}`}>{deliveryStatusLabel(delivery.status)}</span>
                            {delivery.status !== "processed" ? (
                              <button className="secondary-button" disabled={reprocessingDeliveryId === delivery.delivery_id} type="button" onClick={() => void handleReprocessDelivery(delivery)}>
                                {reprocessingDeliveryId === delivery.delivery_id ? "처리 중" : "재처리"}
                              </button>
                            ) : <span className="delivery-attempts">{delivery.processing_attempts}회</span>}
                          </article>
                        ))}
                      </div>
                    )}
                  </>
                ) : null}
              </section>
              <details className="panel project-settings-panel">
                <summary>GitHub 저장소 연결</summary>
                <form className="stacked-form compact-form" onSubmit={handleSaveRepository}>
                  <div className="form-grid three-columns">
                    <label>저장소 ID<input inputMode="numeric" placeholder="GitHub repository ID" value={repositoryForm.repository_id} onChange={(event) => setRepositoryForm({ ...repositoryForm, repository_id: event.target.value })} /></label>
                    <label>저장소 이름<input placeholder="owner/repository" value={repositoryForm.full_name} onChange={(event) => setRepositoryForm({ ...repositoryForm, full_name: event.target.value })} /></label>
                    <label>수집 브랜치<input disabled value={repositoryForm.default_branch} /></label>
                  </div>
                  <div className="form-actions"><button type="submit" disabled={isSavingRepository}>{isSavingRepository ? "연결 중" : repository ? "연결 수정" : "저장소 연결"}</button></div>
                </form>
              </details>
              <details className="panel project-settings-panel">
                <summary>프로젝트 수정</summary>
                <form className="stacked-form compact-form" onSubmit={handleSaveProject}>
                  <label>프로젝트명<input placeholder="프로젝트 이름" value={projectForm.title} onChange={(event) => setProjectForm({ ...projectForm, title: event.target.value })} /></label>
                  <div className="form-grid two-columns"><label>역할<input placeholder="내 역할" value={projectForm.role} onChange={(event) => setProjectForm({ ...projectForm, role: event.target.value })} /></label><label>설명<textarea placeholder="핵심 목표 또는 범위" value={projectForm.description} onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })} /></label></div>
                  <div className="form-actions"><button type="submit" disabled={isSavingProject}>{isSavingProject ? "저장 중" : "수정 저장"}</button></div>
                  <div className="danger-zone"><span>삭제는 되돌릴 수 없습니다.</span><button className="danger-button" type="button" onClick={() => void handleDeleteProject()}>프로젝트 삭제</button></div>
                </form>
              </details>
            </section>
          ) : null}

      <section aria-labelledby="tab-github" id="panel-github" role="tabpanel" hidden={activeTab !== "github"}>
        <GitHubEvidencePanel key={projectId} projectId={projectId} active={activeTab === "github"} tasks={tasks}
          onPlanningChanged={refreshPlanningData} onOpenTask={startEdit} />
      </section>

      {activeTab === "tasks" ? (
            <section aria-labelledby="tab-tasks" className="task-workspace" id="panel-tasks" role="tabpanel">
              <div className={styles.taskCommandBar}>
                <div className="view-switcher" aria-label="업무 보기 방식">
                  {taskViewModes.map((mode) => (
                    <button
                      aria-pressed={taskViewMode === mode}
                      className={taskViewMode === mode ? "active" : ""}
                      key={mode}
                      type="button"
                      onClick={() => setTaskView(mode)}
                    >
                      {{ board: "보드", list: "목록", calendar: "캘린더" }[mode]}
                    </button>
                  ))}
                </div>
                {!isTaskFormVisible ? <button className="primary-button" type="button" onClick={showNewTaskForm}>{editingTaskId ? "편집 양식 열기" : "WBS 항목 추가"}</button> : null}
              </div>
              {isTaskFormVisible ? <TaskFormPanel editingTaskId={editingTaskId} isSavingTask={isSavingTask} milestones={milestones} milestonesUnavailable={loadFailures.includes("milestones")} taskForm={taskForm} setTaskForm={setTaskForm} onSubmit={handleSaveTask} onCancel={cancelTaskForm} onHide={hideTaskForm} /> : null}
              {taskViewMode === "board" ? (
                <section className="board-layout">
                  <section className="task-board" aria-label="업무 보드">
                    {groupedTasks.map((group) => (
                      <div className="panel task-column" key={group.status}>
                        <div className="panel-title-row"><h2>{group.label}</h2><span className="count-badge">{group.items.length}개</span></div>
                        {group.items.length === 0 ? <div className="empty-state">없음</div> : null}
                        {group.items.map((task) => <TaskCard deleteTask={deleteTask} key={task.id} startEdit={startEdit} task={task} updateStatus={updateStatus} />)}
                      </div>
                    ))}
                  </section>
                </section>
              ) : null}
              {taskViewMode === "list" ? (
                <section className="panel"><TaskTable issueFilter={taskIssueFilter} priorityFilter={taskPriorityFilter} setIssueFilter={(issue) => updateProjectDetailUrl({ tab: "tasks", issue })} setPriorityFilter={(priority) => updateProjectDetailUrl({ tab: "tasks", priority })} setSortKey={(sort) => updateProjectDetailUrl({ tab: "tasks", sort })} setStatusFilter={(status) => updateProjectDetailUrl({ tab: "tasks", status })} sortKey={taskSortKey} startEdit={startEdit} statusFilter={taskStatusFilter} tasks={dashboard.sortedTasks} updateStatus={updateStatus} /></section>
              ) : null}
              {taskViewMode === "calendar" ? <CalendarPanel tasks={tasks} /> : null}
            </section>
          ) : null}

          {activeTab === "logs" ? (
            <div aria-labelledby="tab-logs" id="panel-logs" role="tabpanel">
              {loadFailures.includes("logs") ? <section className="panel"><div className="empty-state">업무 로그를 불러오지 못했습니다.</div></section> : <LogPanel deleteLog={deleteLog} editingLogId={editingLogId} isLogFormVisible={isLogFormVisible} isSavingLog={isSavingLog} logForm={logForm} logs={workLogs} setLogForm={setLogForm} showNewLogForm={showNewLogForm} startEditLog={startEditLog} onCancel={cancelLogForm} onHide={hideLogForm} onSubmit={handleSaveLog} />}
            </div>
          ) : null}

          {activeTab === "outcomes" ? (
            <div aria-labelledby="tab-outcomes" id="panel-outcomes" role="tabpanel">
              {isLoading ? <div role="status">성과를 불러오는 중</div> : loadFailures.includes("outcomes") || loadFailures.includes("logs") ? <section className="panel"><div className="empty-state">성과와 근거 로그를 불러오지 못했습니다.</div></section> : <OutcomePanel deleteOutcome={deleteOutcome} editingOutcomeId={editingOutcomeId} isSavingOutcome={isSavingOutcome} isOutcomeFormVisible={isOutcomeFormVisible} onToggleForm={() => setIsOutcomeFormVisible((visible) => !visible)} stage={outcomeStage} onStageChange={(stage) => { setOutcomeStage(stage); setIsOutcomeFormVisible(false); }} hasDraft={Boolean(editingOutcomeId) || JSON.stringify(outcomeForm) !== JSON.stringify(outcomeBaseline)} logs={workLogs} outcomeForm={outcomeForm} outcomes={outcomes} setOutcomeForm={setOutcomeForm} startEditOutcome={startEditOutcome} tasks={tasks} onApplyCandidate={applyOutcomeCandidate} onCancel={cancelOutcomeEdit} onSubmit={handleSaveOutcome} />}
            </div>
          ) : null}

          {activeTab === "career" ? (
            <div aria-labelledby="tab-career" id="panel-career" role="tabpanel">
              {isLoading ? <div role="status">경력 자산을 불러오는 중</div> : loadFailures.includes("career") ? <section className="panel"><div className="empty-state">경력 자산을 불러오지 못했습니다.</div></section> : <CareerPanel projectId={projectId} careerAssets={careerAssets} careerMessage={careerMessage} isGeneratingCareer={isGeneratingCareer} onAssetUpdated={handleCareerAssetUpdated} onGenerate={handleGenerateCareerAsset} />}
            </div>
          ) : null}
        </>
      ) : null}
    </main>
  );
}

function MiniLogList({ logs }: { logs: WorkLogItem[] }) {
  if (logs.length === 0) return <div className="empty-state">로그 없음</div>;
  return <div className="compact-list">{logs.map((log) => <div className="dense-list-row" key={log.id}><span>{log.title}</span><small>{workTypeLabels[log.work_type]} · {log.log_date} · {log.duration_minutes}분</small><b>{log.next_actions || "-"}</b></div>)}</div>;
}

function MiniOutcomeList({ outcomes }: { outcomes: ProjectOutcome[] }) {
  if (outcomes.length === 0) return <div className="empty-state">성과 없음</div>;
  return <div className="compact-list">{outcomes.map((outcome) => <div className="dense-list-row" key={outcome.id}><span>{outcome.title}</span><small>{outcomeMetric(outcome)}</small><b>{outcome.resume_ready ? "가능" : "보류"}</b></div>)}</div>;
}

function TaskFormPanel({ editingTaskId, isSavingTask, milestones, milestonesUnavailable, taskForm, setTaskForm, onSubmit, onCancel, onHide }: { editingTaskId: string | null; isSavingTask: boolean; milestones: ProjectMilestone[]; milestonesUnavailable: boolean; taskForm: TaskForm; setTaskForm: (form: TaskForm) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onCancel: () => void; onHide: () => void }) {
  const selectedMilestoneMissing = taskForm.milestone_id && !milestones.some((milestone) => milestone.id === taskForm.milestone_id);
  const titleInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleInput.current?.focus();
  }, [editingTaskId]);

  return (
    <section className="panel task-form-panel">
      <div className="panel-title-row">
        <h2>{editingTaskId ? "WBS 항목 수정" : "WBS 항목 추가"}</h2>
        <div className="form-actions compact-actions">
          <button className="secondary-button" type="button" onClick={onHide}>양식 숨기기</button>
          {editingTaskId ? <button className="secondary-button" type="button" onClick={onCancel}>편집 취소</button> : <span className="meta-pill">필수: 항목명</span>}
        </div>
      </div>
      <form className="stacked-form compact-form" onSubmit={onSubmit}>
        <div className="form-grid three-columns">
          <label>항목명<input ref={titleInput} placeholder="예: API 응답 시간 개선" value={taskForm.title} onChange={(event) => setTaskForm({ ...taskForm, title: event.target.value })} /></label>
          <label>상태<select value={taskForm.status} onChange={(event) => setTaskForm({ ...taskForm, status: event.target.value as TaskStatus })}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>우선순위<select value={taskForm.priority} onChange={(event) => setTaskForm({ ...taskForm, priority: event.target.value as TaskPriority })}>{Object.entries(taskPriorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        <div className="form-grid two-columns">
          <label>마감일<input type="date" value={taskForm.due_date} onChange={(event) => setTaskForm({ ...taskForm, due_date: event.target.value })} /></label>
          <label>설명<textarea placeholder="완료 기준 또는 참고 메모" value={taskForm.description} onChange={(event) => setTaskForm({ ...taskForm, description: event.target.value })} /></label>
        </div>
        <div className="form-grid two-columns">
          <label>마일스톤<select aria-label="마일스톤" disabled={milestonesUnavailable} value={taskForm.milestone_id} onChange={(event) => setTaskForm({ ...taskForm, milestone_id: event.target.value })}><option value="">미지정</option>{selectedMilestoneMissing ? <option value={taskForm.milestone_id}>현재 연결된 마일스톤</option> : null}{milestones.map((milestone) => <option key={milestone.id} value={milestone.id}>{milestone.title}</option>)}</select></label>
          <label className="checkbox-row"><input checked={taskForm.counts_toward_progress} type="checkbox" onChange={(event) => setTaskForm({ ...taskForm, counts_toward_progress: event.target.checked })} /><span>진척 산정에 포함</span></label>
        </div>
        <div className="form-actions"><button type="submit" disabled={isSavingTask}>{isSavingTask ? "저장 중" : editingTaskId ? "수정 저장" : "WBS 항목 추가"}</button></div>
      </form>
    </section>
  );
}

function TaskCard({ task, updateStatus, startEdit, deleteTask }: { task: ProjectTask; updateStatus: (task: ProjectTask, status: TaskStatus) => Promise<void>; startEdit: (task: ProjectTask) => void; deleteTask: (task: ProjectTask) => Promise<void> }) {
  return (
    <article className="task-card jira-task-card">
      <div className="jira-card-topline">
        <span className="meta-pill status-navy">{taskStatusLabels[task.status]}</span>
        <span className={`meta-pill priority-${task.priority}`}>{taskPriorityLabels[task.priority]}</span>
        {isDelayed(task) ? <span className="meta-pill priority-high">지연</span> : null}
      </div>
      <h3>{task.title}</h3>
      <div className="jira-card-facts">
        <span className={isDelayed(task) ? "meta-pill priority-high" : "meta-pill"}>{task.due_date ?? "마감 없음"}</span>
        <span className="meta-pill">{task.counts_toward_progress ? "산정 WBS" : "참고 활동"}</span>
      </div>
      <select value={task.status} onChange={(event) => void updateStatus(task, event.target.value as TaskStatus)} aria-label={`${task.title} 상태 변경`}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <div className="form-actions compact-actions"><button className="secondary-button" type="button" onClick={() => startEdit(task)}>수정</button><button className="danger-button" type="button" onClick={() => void deleteTask(task)}>삭제</button></div>
    </article>
  );
}

function TaskTable({ issueFilter, priorityFilter, setIssueFilter, setPriorityFilter, setSortKey, setStatusFilter, sortKey, statusFilter, tasks, updateStatus, startEdit }: { issueFilter: "all" | "issue" | "normal"; priorityFilter: TaskPriority | "all"; setIssueFilter: (filter: "all" | "issue" | "normal") => void; setPriorityFilter: (filter: TaskPriority | "all") => void; setSortKey: (sortKey: TaskSortKey) => void; setStatusFilter: (filter: TaskStatus | "all") => void; sortKey: TaskSortKey; statusFilter: TaskStatus | "all"; tasks: ProjectTask[]; updateStatus: (task: ProjectTask, status: TaskStatus) => Promise<void>; startEdit: (task: ProjectTask) => void }) {
  const filteredTasks = useMemo(() => {
    return [...tasks]
      .filter((task) => statusFilter === "all" || task.status === statusFilter)
      .filter((task) => priorityFilter === "all" || task.priority === priorityFilter)
      .filter((task) => {
        if (issueFilter === "all") return true;
        const hasIssue = task.status !== "done" && (isDelayed(task) || task.status === "on_hold" || task.priority === "high");
        return issueFilter === "issue" ? hasIssue : !hasIssue;
      })
      .sort((a, b) => {
        if (sortKey === "priority") return priorityOrder[a.priority] - priorityOrder[b.priority];
        if (sortKey === "created_at") return a.created_at.localeCompare(b.created_at);
        if (sortKey === "status") return taskStatusOrder.indexOf(a.status) - taskStatusOrder.indexOf(b.status);
        if (sortKey === "progress_scope") return Number(b.counts_toward_progress) - Number(a.counts_toward_progress);
        return (a.due_date ?? "9999-12-31").localeCompare(b.due_date ?? "9999-12-31");
      });
  }, [issueFilter, priorityFilter, sortKey, statusFilter, tasks]);

  return (
    <>
      <div className="panel-title-row table-section-title"><h2>WBS 목록</h2><span className="count-badge">{filteredTasks.length} / {tasks.length}개</span></div>
      <div className="list-toolbar" aria-label="WBS 필터와 정렬">
        <label>상태<select aria-label="상태" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TaskStatus | "all")}><option value="all">전체</option>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>우선순위<select aria-label="우선순위" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value as TaskPriority | "all")}><option value="all">전체</option>{Object.entries(taskPriorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>이슈<select aria-label="이슈" value={issueFilter} onChange={(event) => setIssueFilter(event.target.value as "all" | "issue" | "normal")}><option value="all">전체</option><option value="issue">관리 필요</option><option value="normal">정상</option></select></label>
        <label>정렬<select aria-label="정렬" value={sortKey} onChange={(event) => setSortKey(event.target.value as TaskSortKey)}><option value="due_date">마감일</option><option value="priority">우선순위</option><option value="created_at">시작일</option><option value="status">상태</option><option value="progress_scope">산정 여부</option></select></label>
      </div>
      {filteredTasks.length === 0 ? <div className="empty-state">{tasks.length ? "조건에 맞는 WBS 항목이 없습니다." : "WBS 항목 없음"}</div> : null}
      {filteredTasks.length > 0 ? (
        <div className="data-table-wrap">
          <table className="data-table dense-task-table">
            <thead><tr><th>WBS 항목</th><th>상태</th><th>우선순위</th><th>이슈</th><th>산정</th><th>시작일</th><th>마감일</th></tr></thead>
            <tbody>{filteredTasks.map((task) => {
              const delayed = isDelayed(task);
              const issueLabel = delayed ? "기한 초과" : task.status === "on_hold" ? "보류" : task.status !== "done" && task.priority === "high" ? "우선 확인" : "정상";
              const hasIssue = issueLabel !== "정상";
              return <tr key={task.id}><td data-label="WBS 항목"><button className="table-link-button" type="button" onClick={() => startEdit(task)}>{task.title}</button></td><td data-label="상태"><select aria-label={`${task.title} 상태 변경`} value={task.status} onChange={(event) => void updateStatus(task, event.target.value as TaskStatus)}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td><td data-label="우선순위"><span className={`meta-pill priority-${task.priority}`}>{taskPriorityLabels[task.priority]}</span></td><td data-label="이슈"><span className={`meta-pill ${hasIssue ? "priority-high" : "priority-medium"}`}>{issueLabel}</span></td><td data-label="산정"><span className="meta-pill">{task.counts_toward_progress ? "산정 WBS" : "참고 활동"}</span></td><td data-label="시작일">{task.created_at.slice(0, 10)}</td><td data-label="마감일">{task.due_date ?? "-"}</td></tr>;
            })}</tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}



function CalendarPanel({ tasks }: { tasks: ProjectTask[] }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const monthCells = getMonthCells(today);
  const monthLabel = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, "0")}`;
  const { start: weekStart, end: weekEnd } = getWeekRange();
  const dueTasks = [...tasks]
    .filter((task) => task.due_date)
    .sort((a, b) => (a.due_date ?? "").localeCompare(b.due_date ?? ""));
  const tasksByDate = dueTasks.reduce<Record<string, ProjectTask[]>>((groups, task) => {
    if (!task.due_date) return groups;
    groups[task.due_date] = [...(groups[task.due_date] ?? []), task];
    return groups;
  }, {});
  const delayedTasks = dueTasks.filter(isDelayed);
  const thisWeekTasks = dueTasks.filter((task) => {
    if (!task.due_date) return false;
    const dueDate = parseDueDate(task.due_date);
    return dueDate >= weekStart && dueDate <= weekEnd;
  });

  return (
    <section className="calendar-dashboard">
      <section className="panel calendar-month-panel">
        <div className="panel-title-row"><h2>{monthLabel}</h2><span className="count-badge">{dueTasks.length}개</span></div>
        <div className="month-calendar" aria-label="월간 마감 캘린더">
          {["일", "월", "화", "수", "목", "금", "토"].map((day) => <div className="calendar-weekday" key={day}>{day}</div>)}
          {monthCells.map((date, index) => {
            const key = date ? formatDateKey(date) : `blank-${index}`;
            const dayTasks = date ? tasksByDate[formatDateKey(date)] ?? [] : [];
            const hasDelayed = dayTasks.some(isDelayed);
            const isToday = date ? formatDateKey(date) === formatDateKey(today) : false;
            return (
              <div className={`calendar-day ${date ? "" : "is-empty"} ${hasDelayed ? "has-delayed" : ""} ${isToday ? "is-today" : ""}`} key={key}>
                {date ? <time>{date.getDate()}</time> : null}
                <div className="calendar-day-tasks">
                  {dayTasks.slice(0, 3).map((task) => (
                    <span className={`calendar-task-chip priority-${task.priority}`} key={task.id}>{task.title}</span>
                  ))}
                  {dayTasks.length > 3 ? <span className="calendar-more">+{dayTasks.length - 3}</span> : null}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <aside className="calendar-side-stack">
        <section className="panel">
          <div className="panel-title-row"><h2>이번 주 마감</h2><span className="count-badge">{thisWeekTasks.length}개</span></div>
          <DueTaskList empty="이번 주 마감 없음" tasks={thisWeekTasks} />
        </section>
        <section className="panel">
          <div className="panel-title-row"><h2>지연 업무</h2><span className="count-badge danger-count">{delayedTasks.length}개</span></div>
          <DueTaskList empty="지연 없음" tasks={delayedTasks} />
        </section>
        <section className="panel">
          <div className="panel-title-row"><h2>날짜별 업무</h2><span className="count-badge">{Object.keys(tasksByDate).length}일</span></div>
          <div className="calendar-list dense-calendar-list">
            {Object.entries(tasksByDate).map(([date, items]) => (
              <article className={`calendar-row ${items.some(isDelayed) ? "is-delayed" : ""}`} key={date}>
                <time>{date}</time>
                <strong>{items.length}개</strong>
                <div className="calendar-row-items">{items.slice(0, 2).map((task) => <span key={task.id}>{task.title}</span>)}</div>
              </article>
            ))}
          </div>
        </section>
      </aside>
    </section>
  );
}

function DueTaskList({ empty, tasks }: { empty: string; tasks: ProjectTask[] }) {
  if (tasks.length === 0) return <div className="empty-state">{empty}</div>;
  return (
    <div className="calendar-list">
      {tasks.map((task) => (
        <article className={`calendar-row ${isDelayed(task) ? "is-delayed" : ""}`} key={task.id}>
          <time>{task.due_date}</time>
          <strong>{task.title}</strong>
          <span className="meta-pill status-navy">{taskStatusLabels[task.status]}</span>
          <span className={`meta-pill priority-${task.priority}`}>{taskPriorityLabels[task.priority]}</span>
        </article>
      ))}
    </div>
  );
}

function LogPanel({ deleteLog, editingLogId, isLogFormVisible, isSavingLog, logForm, logs, setLogForm, showNewLogForm, startEditLog, onCancel, onHide, onSubmit }: { deleteLog: (log: WorkLogItem) => Promise<void>; editingLogId: string | null; isLogFormVisible: boolean; isSavingLog: boolean; logForm: WorkLogForm; logs: WorkLogItem[]; setLogForm: (form: WorkLogForm) => void; showNewLogForm: () => void; startEditLog: (log: WorkLogItem) => void; onCancel: () => void; onHide: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<WorkType | "all">("all");
  const titleInput = useRef<HTMLInputElement>(null);
  const sortedLogs = useMemo(() => [...logs].sort((a, b) => b.log_date.localeCompare(a.log_date) || b.updated_at.localeCompare(a.updated_at)), [logs]);
  const filteredLogs = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return sortedLogs
      .filter((log) => typeFilter === "all" || log.work_type === typeFilter)
      .filter((log) => {
        if (!normalizedQuery) return true;
        return [log.title, log.content, log.decisions, log.collaborators, log.next_actions, log.blockers]
          .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
      });
  }, [query, sortedLogs, typeFilter]);

  useEffect(() => {
    if (isLogFormVisible) titleInput.current?.focus();
  }, [editingLogId, isLogFormVisible]);

  return (
    <section className="log-dashboard timeline-first-log-dashboard">
      <section className="panel log-timeline-panel">
        <div className="panel-title-row">
          <h2>타임라인</h2>
          <div className="form-actions compact-actions">
            <span className="count-badge">{filteredLogs.length} / {logs.length}개</span>
            {!isLogFormVisible ? <button className="primary-button" disabled={isSavingLog} type="button" onClick={showNewLogForm}>{editingLogId ? "편집 양식 열기" : "로그 추가"}</button> : null}
          </div>
        </div>
        <div className="list-toolbar work-log-filter-toolbar" aria-label="업무 로그 필터">
          <label>검색<input name="work-log-q" placeholder="제목, 내용, 결정, 블로커" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label>유형<select aria-label="업무 로그 유형 필터" name="work-log-type" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as WorkType | "all")}><option value="all">전체</option>{Object.entries(workTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        {logs.length === 0 ? <div className="empty-state">로그 없음</div> : null}
        {logs.length > 0 && filteredLogs.length === 0 ? <div className="empty-state">조건에 맞는 업무 로그가 없습니다.</div> : null}
        <div className="log-timeline">
          {filteredLogs.map((log) => (
            <article className="log-timeline-item" key={log.id}>
              <time>{log.log_date}</time>
              <div>
                <div className="jira-card-topline">
                  <span className="meta-pill status-navy">{workTypeLabels[log.work_type]}</span>
                  <span className="meta-pill">{log.duration_minutes}분</span>
                </div>
                <strong>{log.title}</strong>
                <small>{log.next_actions || "다음 액션 없음"}</small>
                <details className="log-detail-toggle">
                  <summary>상세</summary>
                  <dl>
                    <div><dt>수행 내용</dt><dd>{log.content || "-"}</dd></div>
                    <div><dt>판단/결정</dt><dd>{log.decisions || "-"}</dd></div>
                    <div><dt>협의 대상</dt><dd>{log.collaborators || "-"}</dd></div>
                    <div><dt>다음 액션</dt><dd>{log.next_actions || "-"}</dd></div>
                    <div><dt>블로커</dt><dd>{log.blockers || "-"}</dd></div>
                    <div><dt>소요 시간</dt><dd>{log.duration_minutes}분</dd></div>
                  </dl>
                </details>
                <div className="form-actions compact-actions"><button className="secondary-button" disabled={isSavingLog} type="button" onClick={() => startEditLog(log)}>수정</button><button className="danger-button" disabled={isSavingLog} type="button" onClick={() => void deleteLog(log)}>삭제</button></div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {isLogFormVisible ? (
        <section className="panel log-form-panel">
          <div className="panel-title-row">
            <h2>{editingLogId ? "로그 수정" : "로그 추가"}</h2>
            <div className="form-actions compact-actions">
              <button className="secondary-button" disabled={isSavingLog} type="button" onClick={onHide}>양식 숨기기</button>
              {editingLogId ? <button className="secondary-button" disabled={isSavingLog} type="button" onClick={onCancel}>편집 취소</button> : <span className="meta-pill">필수: 제목</span>}
            </div>
          </div>
          <form className="stacked-form compact-form quick-capture-form work-log-form" onSubmit={onSubmit}>
            <div className="form-grid two-columns">
              <label>업무명<input ref={titleInput} disabled={isSavingLog} placeholder="예: 주간 리포트 자동화" value={logForm.title} onChange={(event) => setLogForm({ ...logForm, title: event.target.value })} /></label>
              <label>수행일<input disabled={isSavingLog} type="date" value={logForm.log_date} onChange={(event) => setLogForm({ ...logForm, log_date: event.target.value })} /></label>
            </div>
            <div className="form-grid two-columns">
              <label>유형<select disabled={isSavingLog} value={logForm.work_type} onChange={(event) => setLogForm({ ...logForm, work_type: event.target.value as WorkType })}>{Object.entries(workTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label>수행 내용<textarea disabled={isSavingLog} placeholder="실제로 한 일" value={logForm.content} onChange={(event) => setLogForm({ ...logForm, content: event.target.value })} /></label>
            </div>
            <details className="quick-advanced-fields work-log-detail-fields">
              <summary>상세 입력</summary>
              <div className="form-grid two-columns">
                <label>결정 사항<textarea disabled={isSavingLog} placeholder="판단/결정" value={logForm.decisions} onChange={(event) => setLogForm({ ...logForm, decisions: event.target.value })} /></label>
                <label>협업자<input disabled={isSavingLog} placeholder="예: PM, 운영팀" value={logForm.collaborators} onChange={(event) => setLogForm({ ...logForm, collaborators: event.target.value })} /></label>
              </div>
              <div className="form-grid two-columns">
                <label>다음 액션<textarea disabled={isSavingLog} placeholder="다음에 할 일" value={logForm.next_actions} onChange={(event) => setLogForm({ ...logForm, next_actions: event.target.value })} /></label>
                <label>블로커<textarea disabled={isSavingLog} placeholder="막힌 점" value={logForm.blockers} onChange={(event) => setLogForm({ ...logForm, blockers: event.target.value })} /></label>
              </div>
              <div className="form-grid two-columns">
                <label>소요(분)<input disabled={isSavingLog} min="0" type="number" value={logForm.duration_minutes} onChange={(event) => setLogForm({ ...logForm, duration_minutes: event.target.value })} /></label>
              </div>
            </details>
            <div className="form-actions"><button type="submit" disabled={isSavingLog}>{isSavingLog ? "저장 중" : editingLogId ? "수정 저장" : "로그 추가"}</button></div>
          </form>
        </section>
      ) : null}
    </section>
  );
}

function outcomeMetric(outcome: ProjectOutcome) {
  if (!outcome.metric_name) return "-";
  if (!outcome.metric_value) return outcome.metric_name;
  return `${outcome.metric_name} ${outcome.metric_value}${outcome.metric_unit}`;
}

function outcomeEvidence(outcome: ProjectOutcome, logs: WorkLogItem[]) {
  if (outcome.evidence_work_log_ids.length === 0) return "-";
  return outcome.evidence_work_log_ids.map((id) => {
    const log = logs.find((item) => item.id === id);
    return log ? `${log.log_date} ${log.title}` : `연결 로그(${id.slice(0, 8)})`;
  }).join(", ");
}

function OutcomePanel({
  deleteOutcome,
  editingOutcomeId,
  isSavingOutcome,
  isOutcomeFormVisible,
  onToggleForm,
  stage,
  onStageChange,
  hasDraft,
  logs,
  outcomeForm,
  outcomes,
  setOutcomeForm,
  startEditOutcome,
  tasks,
  onApplyCandidate,
  onCancel,
  onSubmit
}: {
  deleteOutcome: (outcome: ProjectOutcome) => Promise<void>;
  editingOutcomeId: string | null;
  isSavingOutcome: boolean;
  isOutcomeFormVisible: boolean;
  onToggleForm: () => void;
  stage: OutcomeStage;
  onStageChange: (stage: OutcomeStage) => void;
  hasDraft: boolean;
  logs: WorkLogItem[];
  outcomeForm: OutcomeForm;
  outcomes: ProjectOutcome[];
  setOutcomeForm: (form: OutcomeForm) => void;
  startEditOutcome: (outcome: ProjectOutcome) => void;
  tasks: ProjectTask[];
  onApplyCandidate: (candidate: OutcomeCandidate) => void;
  onCancel: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const titleInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (isOutcomeFormVisible) titleInput.current?.focus();
  }, [isOutcomeFormVisible, editingOutcomeId]);
  const sortedOutcomes = [...outcomes].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const sortedLogs = [...logs].sort((a, b) => b.log_date.localeCompare(a.log_date));
  const outcomeCandidates = buildOutcomeCandidates(logs, tasks, outcomes);
  const visibleOutcomes = sortedOutcomes.filter((outcome) => outcome.resume_ready === (stage === "confirmed"));
  const confirmedCount = outcomes.filter((outcome) => outcome.resume_ready).length;
  const documentEvidence = outcomes.find((outcome) => outcome.id === editingOutcomeId)?.evidence_document_ids ?? [];
  const selectedIds = outcomeForm.evidence_work_log_ids;
  const missingIds = selectedIds.filter((id) => !logs.some((log) => log.id === id));
  const canConfirm = selectedIds.some((id) => logs.some((log) => log.id === id)) || documentEvidence.length > 0;
  const query = evidenceQuery.trim().toLocaleLowerCase();
  const visibleLogs = sortedLogs.filter((log) => (!selectedOnly || selectedIds.includes(log.id))
    && [log.title, log.content, log.log_date, log.decisions, log.collaborators, log.next_actions, log.blockers].some((value) => value.toLocaleLowerCase().includes(query)));
  const changeForm = (updates: Partial<OutcomeForm>) => setOutcomeForm({ ...outcomeForm, ...updates, resume_ready: false });

  return (
    <section className={styles.outcomeWorkspace} aria-busy={isSavingOutcome}>
      <div className={styles.outcomeHeader}>
        <h2>성과</h2>
        <button className="secondary-button" type="button" onClick={onToggleForm} disabled={isSavingOutcome} aria-expanded={isOutcomeFormVisible} aria-controls="outcome-review-form">
          {isOutcomeFormVisible ? "목록으로" : hasDraft ? "작성 계속" : "성과 추가"}
        </button>
      </div>
      <div className={styles.outcomeStages} role="group" aria-label="성과 단계">
        {([
          ["candidates", "후보", outcomeCandidates.length],
          ["review", "검토 중", outcomes.length - confirmedCount],
          ["confirmed", "확정", confirmedCount]
        ] as const).map(([value, label, count]) => <button key={value} type="button" aria-pressed={stage === value} disabled={isSavingOutcome} onClick={() => onStageChange(value)}>{label}<span>{count}</span></button>)}
      </div>

      {isOutcomeFormVisible && (
        <section className={styles.outcomeEditor} id="outcome-review-form">
          <div className={styles.outcomeHeader}><h3>{editingOutcomeId ? "성과 수정" : "성과 검토"}</h3><button className="secondary-button" type="button" onClick={onCancel} disabled={isSavingOutcome}>작성 취소</button></div>
          <form onSubmit={onSubmit}>
            <fieldset disabled={isSavingOutcome} className={styles.outcomeFields}>
              <label>개선 항목<input ref={titleInput} required maxLength={180} value={outcomeForm.title} onChange={(event) => changeForm({ title: event.target.value })} /></label>
              <div className={styles.outcomePair}>
                <label>개선 전<textarea aria-label="개선 전" value={outcomeForm.before_state} onChange={(event) => changeForm({ before_state: event.target.value })} /></label>
                <label>개선 후<textarea aria-label="개선 후" value={outcomeForm.after_state} onChange={(event) => changeForm({ after_state: event.target.value })} /></label>
              </div>
              <div className={styles.outcomePair}>
                <label>유형<select aria-label="성과 유형" value={outcomeForm.outcome_type} onChange={(event) => changeForm({ outcome_type: event.target.value as OutcomeType, metric_value: event.target.value === "qualitative" ? "" : outcomeForm.metric_value })}>{Object.entries(outcomeTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>측정 지표<input value={outcomeForm.metric_name} onChange={(event) => changeForm({ metric_name: event.target.value })} /></label>
              </div>
              {outcomeForm.outcome_type === "quantitative" ? <div className={styles.outcomePair}>
                <label>수치<input required inputMode="decimal" value={outcomeForm.metric_value} onChange={(event) => changeForm({ metric_value: event.target.value })} /></label>
                <label>단위<input value={outcomeForm.metric_unit} onChange={(event) => changeForm({ metric_unit: event.target.value })} /></label>
              </div> : null}

              <fieldset className={styles.evidencePicker}>
                <legend>근거 로그 <span>{selectedIds.length}개 선택</span></legend>
                <div className={styles.evidenceToolbar}>
                  <input type="search" aria-label="근거 로그 검색" placeholder="제목·내용·날짜 검색" value={evidenceQuery} onChange={(event) => setEvidenceQuery(event.target.value)} />
                  <label className={styles.outcomeCheck}><input type="checkbox" aria-label="선택한 근거만" checked={selectedOnly} onChange={(event) => setSelectedOnly(event.target.checked)} />선택한 근거만</label>
                </div>
                <div className={styles.evidenceList}>
                  {visibleLogs.length === 0 ? <div className="empty-state">{logs.length === 0 ? "연결할 업무 로그가 없습니다." : "조건에 맞는 근거가 없습니다."}</div> : null}
                  {visibleLogs.map((log) => <div className={styles.evidenceItem} key={log.id}>
                    <label className={styles.outcomeCheck}>
                      <input type="checkbox" aria-label={`근거 선택: ${log.title}`} checked={selectedIds.includes(log.id)} onChange={(event) => changeForm({ evidence_work_log_ids: event.target.checked ? [...selectedIds, log.id] : selectedIds.filter((id) => id !== log.id) })} />
                      <span><strong>{log.title}</strong><small>{log.log_date} · {workTypeLabels[log.work_type]}</small></span>
                    </label>
                    <details><summary>근거 내용</summary><dl>
                      <div><dt>수행 내용</dt><dd>{log.content || "-"}</dd></div>
                      {([ ["결정 사항", log.decisions], ["협업자", log.collaborators], ["다음 액션", log.next_actions], ["블로커", log.blockers] ] as const).filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                    </dl></details>
                  </div>)}
                </div>
                {missingIds.map((id) => <label key={id} className={styles.outcomeCheck}><input type="checkbox" checked onChange={() => changeForm({ evidence_work_log_ids: selectedIds.filter((value) => value !== id) })} />조회되지 않은 근거 ({id.slice(0, 8)})</label>)}
              </fieldset>
              {documentEvidence.length > 0 ? <details><summary>기존 문서 근거 {documentEvidence.length}개</summary><ul>{documentEvidence.map((id) => <li key={id}>{id}</li>)}</ul></details> : null}
              <label className={styles.outcomeCheck}><input type="checkbox" checked={outcomeForm.resume_ready} disabled={!canConfirm && !outcomeForm.resume_ready} onChange={(event) => setOutcomeForm({ ...outcomeForm, resume_ready: event.target.checked })} />근거를 확인했으며 이력서 반영을 확정합니다</label>
              {!canConfirm ? <p className={styles.outcomeHint}>근거 미연결 · 검토 중으로만 저장 가능</p> : null}
              <div className={styles.outcomeActions}><button className="primary-button" type="submit">{isSavingOutcome ? "저장 중" : outcomeForm.resume_ready ? "확정 저장" : "검토 저장"}</button></div>
            </fieldset>
          </form>
        </section>
      )}

      {!isOutcomeFormVisible && stage === "candidates" ? <section aria-label="성과 후보">
        {outcomeCandidates.length === 0 ? <div className="empty-state">근거 로그 기반 후보 없음</div> : null}
        <div className={styles.outcomeList}>
          {outcomeCandidates.map((candidate) => <article className={styles.outcomeRow} key={candidate.id}>
            <div className={styles.outcomeHeader}><strong>{candidate.title}</strong><span className="meta-pill">{candidate.source === "task" ? "완료 업무" : "업무 로그"}</span></div>
            <p>{candidate.after_state}</p>
            <div className={styles.outcomeHeader}><small>근거 로그 {candidate.evidence_work_log_ids.length}개</small><button className="secondary-button" type="button" disabled={isSavingOutcome} onClick={() => onApplyCandidate(candidate)}>검토 시작</button></div>
          </article>)}
        </div>
      </section> : null}

      {!isOutcomeFormVisible && stage !== "candidates" ? <section className={styles.outcomeList} aria-label={stage === "confirmed" ? "확정 성과" : "검토 중 성과"}>
        {visibleOutcomes.length === 0 ? <div className="empty-state">{stage === "confirmed" ? "확정 성과 없음" : "검토 중 성과 없음"}</div> : null}
        {visibleOutcomes.map((outcome) => <article className={styles.outcomeRow} key={outcome.id}>
          <div className={styles.outcomeHeader}><strong>{outcome.title}</strong><span className="meta-pill">{outcome.resume_ready ? "이력서 반영 확정" : "검토 중"}</span></div>
          <p>{outcome.after_state || "개선 후 내용 없음"}</p>
          <div className={styles.outcomeHeader}><small>{outcomeTypeLabels[outcome.outcome_type]} · {outcomeMetric(outcome)} · 근거 로그 {outcome.evidence_work_log_ids.length}개</small><div className={styles.outcomeActions}>
            <button className="secondary-button" type="button" disabled={isSavingOutcome} onClick={() => startEditOutcome(outcome)}>검토·수정</button>
            <button className="danger-button" type="button" disabled={isSavingOutcome} onClick={() => void deleteOutcome(outcome)}>삭제</button>
          </div></div>
          <details><summary>성과 근거</summary><p>{outcomeEvidence(outcome, logs)}</p>{outcome.before_state ? <p>개선 전: {outcome.before_state}</p> : null}{outcome.evidence_document_ids.length ? <p>문서 근거 {outcome.evidence_document_ids.length}개</p> : null}</details>
        </article>)}
      </section> : null}
    </section>
  );
}
