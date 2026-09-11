"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, use, useCallback, useEffect, useMemo, useState } from "react";

import { parseApiErrorMessage } from "../../reports/api-error";
import { CareerPanel } from "./CareerPanel";
import type {
  CareerAsset,
  CareerTargetRole,
  GitHubCommit,
  ProjectOutcome,
  ProjectStatus,
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
  taskPriorityLabels,
  taskStatusLabels,
  workTypeLabels
} from "../types";

type PageProps = {
  params: Promise<{ projectId: string }>;
};

type DetailTab = "overview" | "tasks" | "logs" | "outcomes" | "career";
type TaskViewMode = "board" | "list" | "calendar";
type DetailLoadFailure = "logs" | "outcomes" | "career" | "commits";

type TaskForm = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string;
};

type ProjectForm = {
  title: string;
  description: string;
  role: string;
  status: ProjectStatus;
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
  { id: "logs", label: "업무 로그" },
  { id: "outcomes", label: "성과" },
  { id: "career", label: "경력 자산" }
];

const taskStatusOrder: TaskStatus[] = ["planned", "in_progress", "done", "on_hold"];
const priorityOrder: Record<TaskPriority, number> = { high: 1, medium: 2, low: 3 };
const initialTaskForm: TaskForm = {
  title: "",
  description: "",
  status: "planned",
  priority: "medium",
  due_date: ""
};

const initialProjectForm: ProjectForm = {
  title: "",
  description: "",
  role: "",
  status: "idea"
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

function taskProgress(task: ProjectTask) {
  if (task.status === "done") return 100;
  if (task.status === "in_progress") return 50;
  if (task.status === "on_hold") return 10;
  return 0;
}


function formatDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
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
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [taskViewMode, setTaskViewMode] = useState<TaskViewMode>("board");
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [workLogs, setWorkLogs] = useState<WorkLogItem[]>([]);
  const [outcomes, setOutcomes] = useState<ProjectOutcome[]>([]);
  const [careerAssets, setCareerAssets] = useState<CareerAsset[]>([]);
  const [repository, setRepository] = useState<RepositorySource | null>(null);
  const [commits, setCommits] = useState<GitHubCommit[]>([]);
  const [repositoryForm, setRepositoryForm] = useState({ repository_id: "", full_name: "", default_branch: "main" });
  const [projectForm, setProjectForm] = useState<ProjectForm>(initialProjectForm);
  const [taskForm, setTaskForm] = useState<TaskForm>(initialTaskForm);
  const [logForm, setLogForm] = useState<WorkLogForm>(() => createInitialWorkLogForm());
  const [outcomeForm, setOutcomeForm] = useState<OutcomeForm>(() => createInitialOutcomeForm());
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editingLogId, setEditingLogId] = useState<string | null>(null);
  const [editingOutcomeId, setEditingOutcomeId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingProject, setIsSavingProject] = useState(false);
  const [isSavingTask, setIsSavingTask] = useState(false);
  const [isSavingLog, setIsSavingLog] = useState(false);
  const [isSavingOutcome, setIsSavingOutcome] = useState(false);
  const [isGeneratingCareer, setIsGeneratingCareer] = useState(false);
  const [isSavingRepository, setIsSavingRepository] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loadFailures, setLoadFailures] = useState<DetailLoadFailure[]>([]);
  const [careerMessage, setCareerMessage] = useState("");

  const groupedTasks = useMemo(() => {
    return taskStatusOrder.map((status) => ({
      status,
      label: taskStatusLabels[status],
      items: sortTasks(tasks.filter((task) => task.status === status))
    }));
  }, [tasks]);

  const dashboard = useMemo(() => {
    const delayedTasks = tasks.filter(isDelayed);
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
    return { delayedTasks, dueTasks, latestOutcomes, quantitativeOutcomes, recentLogs, resumeReadyOutcomes, sortedTasks, thisWeekDueTasks };
  }, [outcomes, tasks, workLogs]);

  const loadProject = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const [projectResponse, tasksResponse, logsResponse, outcomesResponse, careerResponse, repositoryResponse, commitsResponse] = await Promise.all([
        fetch(`/api/projects/${projectId}`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/tasks`, { cache: "no-store" }),
        fetch(`/api/work-logs?project_id=${projectId}`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/outcomes`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/career-assets`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/repository`, { cache: "no-store" }),
        fetch(`/api/projects/${projectId}/commits`, { cache: "no-store" })
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
        role: nextProject.role,
        status: nextProject.status
      });
      setTasks((await tasksResponse.json()) as ProjectTask[]);
      const failures: DetailLoadFailure[] = [];
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
      setLoadFailures(failures);
    } catch (error) {
      setLoadFailures([]);
      setErrorMessage(error instanceof Error ? error.message : "프로젝트 상세를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

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

    const payload = { ...taskForm, due_date: taskForm.due_date || null };
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
      due_date: task.due_date ?? ""
    });
    setTaskViewMode("board");
    setActiveTab("tasks");
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
      setLogForm(createInitialWorkLogForm());
      setEditingLogId(null);
      await loadProject();
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
    setActiveTab("logs");
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
      }
      await loadProject();
      setSuccessMessage("업무 로그 삭제 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "업무 로그를 삭제하지 못했습니다.");
    }
  }

  async function handleSaveOutcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");
    if (!outcomeForm.title.trim()) {
      setErrorMessage("개선 항목을 입력하세요.");
      return;
    }
    if (outcomeForm.outcome_type === "quantitative" && !outcomeForm.metric_value.trim()) {
      setErrorMessage("정량 성과는 수치를 입력하세요.");
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
      evidence_document_ids: [],
      resume_ready: outcomeForm.resume_ready
    };
    const success = editingOutcomeId ? "성과 수정 완료" : "성과 추가 완료";

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
      setOutcomeForm(createInitialOutcomeForm());
      setEditingOutcomeId(null);
      await loadProject();
      setSuccessMessage(success);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "성과를 저장하지 못했습니다.");
    } finally {
      setIsSavingOutcome(false);
    }
  }

  function startEditOutcome(outcome: ProjectOutcome) {
    setSuccessMessage("");
    setEditingOutcomeId(outcome.id);
    setOutcomeForm({
      title: outcome.title,
      outcome_type: outcome.outcome_type,
      before_state: outcome.before_state,
      after_state: outcome.after_state,
      metric_name: outcome.metric_name,
      metric_value: outcome.metric_value ?? "",
      metric_unit: outcome.metric_unit,
      evidence_work_log_ids: outcome.evidence_work_log_ids,
      resume_ready: outcome.resume_ready
    });
    setActiveTab("outcomes");
  }

  function applyOutcomeCandidate(candidate: OutcomeCandidate) {
    setSuccessMessage("");
    setEditingOutcomeId(null);
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
    setActiveTab("outcomes");
  }

  async function deleteOutcome(outcome: ProjectOutcome) {
    if (!window.confirm("성과를 삭제할까요?")) return;
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
      }
      await loadProject();
      setSuccessMessage("성과 삭제 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "성과를 삭제하지 못했습니다.");
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
      setCareerMessage("경력 자산 생성 완료");
      await loadProject();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "경력 자산을 생성하지 못했습니다.");
    } finally {
      setIsGeneratingCareer(false);
    }
  }

  function handleCareerAssetUpdated(updatedAsset: CareerAsset) {
    setCareerAssets((current) => current.map((asset) => asset.id === updatedAsset.id ? updatedAsset : asset));
  }

  return (
    <main className="page-shell project-page project-detail-page">
      <div className="dashboard-topbar compact-topbar">
        <div>
          <Link className="text-link" href="/projects">← 프로젝트</Link>
          <h1>{project?.title ?? "프로젝트"}</h1>
        </div>
        {project ? (
          <div className="task-meta">
            <span className="meta-pill status-navy">{projectStatusLabels[project.status]}</span>
            <span className="meta-pill">진척 {project.progress_percent}%</span>
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
            일부 데이터를 불러오지 못했습니다: {loadFailures.map((failure) => ({ logs: "업무 로그", outcomes: "성과", career: "경력 자산", commits: "커밋 근거" })[failure]).join(", ")}.
          </span>
          <button className="secondary-button" disabled={isLoading} type="button" onClick={() => void loadProject()}>
            다시 시도
          </button>
        </div>
      ) : null}
      {successMessage ? <div aria-live="polite" className="alert success" role="status">{successMessage}</div> : null}

      {project ? (
        <>
          <section className="summary-grid dashboard-metrics" aria-label="프로젝트 지표">
            <div className="metric-card"><span>진척도</span><strong>{project.progress_percent}%</strong></div>
            <div className="metric-card"><span>잔여 WBS</span><strong>{project.remaining_tasks}</strong></div>
            <div className="metric-card"><span>커밋 근거</span><strong>{loadFailures.includes("commits") ? "-" : commits.length}</strong></div>
            <div className="metric-card"><span>성과</span><strong>{loadFailures.includes("outcomes") ? "-" : outcomes.length}</strong></div>
          </section>

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
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          {activeTab === "overview" ? (
            <section aria-labelledby="tab-overview" className="overview-dashboard" id="panel-overview" role="tabpanel">
              <section className="panel">
                <div className="panel-title-row"><h2>진척</h2><span className="count-badge">{projectStatusLabels[project.status]}</span></div>
                <div className="overview-bars">
                  <div><span>완료율</span><div className="progress-row-bar"><span style={{ width: `${project.progress_percent}%` }} /></div></div>
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
                  <div className="form-grid two-columns"><label>프로젝트명<input placeholder="프로젝트 이름" value={projectForm.title} onChange={(event) => setProjectForm({ ...projectForm, title: event.target.value })} /></label><label>상태<select value={projectForm.status} onChange={(event) => setProjectForm({ ...projectForm, status: event.target.value as ProjectStatus })}>{Object.entries(projectStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
                  <div className="form-grid two-columns"><label>역할<input placeholder="내 역할" value={projectForm.role} onChange={(event) => setProjectForm({ ...projectForm, role: event.target.value })} /></label><label>설명<textarea placeholder="핵심 목표 또는 범위" value={projectForm.description} onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })} /></label></div>
                  <div className="form-actions"><button type="submit" disabled={isSavingProject}>{isSavingProject ? "저장 중" : "수정 저장"}</button></div>
                  <div className="danger-zone"><span>삭제는 되돌릴 수 없습니다.</span><button className="danger-button" type="button" onClick={() => void handleDeleteProject()}>프로젝트 삭제</button></div>
                </form>
              </details>
            </section>
          ) : null}

          {activeTab === "tasks" ? (
            <section aria-labelledby="tab-tasks" className="task-workspace" id="panel-tasks" role="tabpanel">
              <div className="view-switcher" aria-label="업무 보기 방식">
                {(["board", "list", "calendar"] as TaskViewMode[]).map((mode) => (
                  <button
                    aria-pressed={taskViewMode === mode}
                    className={taskViewMode === mode ? "active" : ""}
                    key={mode}
                    type="button"
                    onClick={() => setTaskViewMode(mode)}
                  >
                    {{ board: "보드", list: "목록", calendar: "캘린더" }[mode]}
                  </button>
                ))}
              </div>
              {taskViewMode === "board" ? (
                <section className="board-layout">
                  <TaskFormPanel editingTaskId={editingTaskId} isSavingTask={isSavingTask} taskForm={taskForm} setTaskForm={setTaskForm} onSubmit={handleSaveTask} onCancel={() => { setEditingTaskId(null); setTaskForm(initialTaskForm); }} />
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
                <section className="panel"><TaskTable startEdit={startEdit} tasks={dashboard.sortedTasks} updateStatus={updateStatus} /></section>
              ) : null}
              {taskViewMode === "calendar" ? <CalendarPanel tasks={tasks} /> : null}
            </section>
          ) : null}

          {activeTab === "logs" ? (
            <div aria-labelledby="tab-logs" id="panel-logs" role="tabpanel">
              {loadFailures.includes("logs") ? <section className="panel"><div className="empty-state">업무 로그를 불러오지 못했습니다.</div></section> : <LogPanel deleteLog={deleteLog} editingLogId={editingLogId} isSavingLog={isSavingLog} logForm={logForm} logs={workLogs} projectTitle={project.title} setLogForm={setLogForm} startEditLog={startEditLog} tasks={tasks} onCancel={() => { setEditingLogId(null); setLogForm(createInitialWorkLogForm()); }} onSubmit={handleSaveLog} />}
            </div>
          ) : null}

          {activeTab === "outcomes" ? (
            <div aria-labelledby="tab-outcomes" id="panel-outcomes" role="tabpanel">
              {loadFailures.includes("outcomes") || loadFailures.includes("logs") ? <section className="panel"><div className="empty-state">성과와 근거 로그를 불러오지 못했습니다.</div></section> : <OutcomePanel deleteOutcome={deleteOutcome} editingOutcomeId={editingOutcomeId} isSavingOutcome={isSavingOutcome} logs={workLogs} outcomeForm={outcomeForm} outcomes={outcomes} quantitativeOutcomes={dashboard.quantitativeOutcomes} resumeReadyOutcomes={dashboard.resumeReadyOutcomes} setOutcomeForm={setOutcomeForm} startEditOutcome={startEditOutcome} tasks={tasks} onApplyCandidate={applyOutcomeCandidate} onCancel={() => { setEditingOutcomeId(null); setOutcomeForm(createInitialOutcomeForm()); }} onSubmit={handleSaveOutcome} />}
            </div>
          ) : null}

          {activeTab === "career" ? (
            <div aria-labelledby="tab-career" id="panel-career" role="tabpanel">
              {loadFailures.includes("career") ? <section className="panel"><div className="empty-state">경력 자산을 불러오지 못했습니다.</div></section> : <CareerPanel projectId={projectId} careerAssets={careerAssets} careerMessage={careerMessage} isGeneratingCareer={isGeneratingCareer} onAssetUpdated={handleCareerAssetUpdated} onGenerate={handleGenerateCareerAsset} />}
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

function TaskFormPanel({ editingTaskId, isSavingTask, taskForm, setTaskForm, onSubmit, onCancel }: { editingTaskId: string | null; isSavingTask: boolean; taskForm: TaskForm; setTaskForm: (form: TaskForm) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onCancel: () => void }) {
  return (
    <section className="panel task-form-panel">
      <div className="panel-title-row"><h2>{editingTaskId ? "WBS 항목 수정" : "WBS 항목 추가"}</h2>{editingTaskId ? <button className="secondary-button" type="button" onClick={onCancel}>취소</button> : <span className="meta-pill">필수: 항목명</span>}</div>
      <form className="stacked-form compact-form" onSubmit={onSubmit}>
        <div className="form-grid three-columns">
          <label>항목명<input placeholder="예: API 응답 시간 개선" value={taskForm.title} onChange={(event) => setTaskForm({ ...taskForm, title: event.target.value })} /></label>
          <label>상태<select value={taskForm.status} onChange={(event) => setTaskForm({ ...taskForm, status: event.target.value as TaskStatus })}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>우선순위<select value={taskForm.priority} onChange={(event) => setTaskForm({ ...taskForm, priority: event.target.value as TaskPriority })}>{Object.entries(taskPriorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        <div className="form-grid two-columns">
          <label>마감일<input type="date" value={taskForm.due_date} onChange={(event) => setTaskForm({ ...taskForm, due_date: event.target.value })} /></label>
          <label>설명<textarea placeholder="완료 기준 또는 참고 메모" value={taskForm.description} onChange={(event) => setTaskForm({ ...taskForm, description: event.target.value })} /></label>
        </div>
        <div className="form-actions"><button type="submit" disabled={isSavingTask}>{isSavingTask ? "저장 중" : editingTaskId ? "수정 저장" : "WBS 항목 추가"}</button></div>
      </form>
    </section>
  );
}

function TaskCard({ task, updateStatus, startEdit, deleteTask }: { task: ProjectTask; updateStatus: (task: ProjectTask, status: TaskStatus) => Promise<void>; startEdit: (task: ProjectTask) => void; deleteTask: (task: ProjectTask) => Promise<void> }) {
  const progress = taskProgress(task);

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
        <span className="meta-pill">진척 {progress}%</span>
      </div>
      <div className="mini-progress"><span style={{ width: `${progress}%` }} /></div>
      <select value={task.status} onChange={(event) => void updateStatus(task, event.target.value as TaskStatus)} aria-label={`${task.title} 상태 변경`}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <div className="form-actions compact-actions"><button className="secondary-button" type="button" onClick={() => startEdit(task)}>수정</button><button className="danger-button" type="button" onClick={() => void deleteTask(task)}>삭제</button></div>
    </article>
  );
}

function TaskTable({ tasks, updateStatus, startEdit }: { tasks: ProjectTask[]; updateStatus: (task: ProjectTask, status: TaskStatus) => Promise<void>; startEdit: (task: ProjectTask) => void }) {
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | "all">("all");
  const [issueFilter, setIssueFilter] = useState<"all" | "issue" | "normal">("all");
  const [sortKey, setSortKey] = useState<"due_date" | "priority" | "progress" | "created_at" | "status">("due_date");

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
        if (sortKey === "progress") return taskProgress(b) - taskProgress(a);
        if (sortKey === "created_at") return a.created_at.localeCompare(b.created_at);
        if (sortKey === "status") return taskStatusOrder.indexOf(a.status) - taskStatusOrder.indexOf(b.status);
        return (a.due_date ?? "9999-12-31").localeCompare(b.due_date ?? "9999-12-31");
      });
  }, [issueFilter, priorityFilter, sortKey, statusFilter, tasks]);

  return (
    <>
      <div className="panel-title-row table-section-title"><h2>WBS 목록</h2><span className="meta-pill">필터 · 정렬 · 상태 변경</span></div>
      <div className="list-toolbar" aria-label="WBS 필터와 정렬">
        <label>상태<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TaskStatus | "all")}><option value="all">전체</option>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>우선순위<select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value as TaskPriority | "all")}><option value="all">전체</option>{Object.entries(taskPriorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>이슈<select value={issueFilter} onChange={(event) => setIssueFilter(event.target.value as "all" | "issue" | "normal")}><option value="all">전체</option><option value="issue">관리 필요</option><option value="normal">정상</option></select></label>
        <label>정렬<select value={sortKey} onChange={(event) => setSortKey(event.target.value as "due_date" | "priority" | "progress" | "created_at" | "status")}><option value="due_date">마감일</option><option value="priority">우선순위</option><option value="progress">진행률</option><option value="created_at">시작일</option><option value="status">상태</option></select></label>
        <span className="count-badge">{filteredTasks.length}개</span>
      </div>
      {filteredTasks.length === 0 ? <div className="empty-state">WBS 항목 없음</div> : null}
      {filteredTasks.length > 0 ? (
        <div className="data-table-wrap">
          <table className="data-table dense-task-table">
            <thead><tr><th>WBS 항목</th><th>상태</th><th>우선순위</th><th>이슈</th><th>시작일</th><th>마감일</th><th>진행률</th></tr></thead>
            <tbody>{filteredTasks.map((task) => {
              const delayed = isDelayed(task);
              const progress = taskProgress(task);
              const issueLabel = delayed ? "기한 초과" : task.status === "on_hold" ? "보류" : task.status !== "done" && task.priority === "high" ? "우선 확인" : "정상";
              const hasIssue = issueLabel !== "정상";
              return <tr key={task.id}><td><button className="table-link-button" type="button" onClick={() => startEdit(task)}>{task.title}</button></td><td><select aria-label={`${task.title} 상태 변경`} value={task.status} onChange={(event) => void updateStatus(task, event.target.value as TaskStatus)}>{Object.entries(taskStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td><td><span className={`meta-pill priority-${task.priority}`}>{taskPriorityLabels[task.priority]}</span></td><td><span className={`meta-pill ${hasIssue ? "priority-high" : "priority-medium"}`}>{issueLabel}</span></td><td>{task.created_at.slice(0, 10)}</td><td>{task.due_date ?? "-"}</td><td><div className="table-progress"><div className="mini-progress"><span style={{ width: `${progress}%` }} /></div><b>{progress}%</b></div></td></tr>;
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

function linkedWorkTitle(log: WorkLogItem, tasks: ProjectTask[]) {
  const normalizedTitle = log.title.trim().toLowerCase();
  const matchedTask = tasks.find((task) => {
    const taskTitle = task.title.trim().toLowerCase();
    return taskTitle && (normalizedTitle.includes(taskTitle) || taskTitle.includes(normalizedTitle));
  });
  return matchedTask?.title ?? log.title;
}

function LogPanel({ deleteLog, editingLogId, isSavingLog, logForm, logs, projectTitle, setLogForm, startEditLog, tasks, onCancel, onSubmit }: { deleteLog: (log: WorkLogItem) => Promise<void>; editingLogId: string | null; isSavingLog: boolean; logForm: WorkLogForm; logs: WorkLogItem[]; projectTitle: string; setLogForm: (form: WorkLogForm) => void; startEditLog: (log: WorkLogItem) => void; tasks: ProjectTask[]; onCancel: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const sortedLogs = [...logs].sort((a, b) => b.log_date.localeCompare(a.log_date));

  return (
    <section className="log-dashboard">
      <section className="panel log-form-panel">
        <div className="panel-title-row"><h2>{editingLogId ? "로그 수정" : "로그 추가"}</h2>{editingLogId ? <button className="secondary-button" type="button" onClick={onCancel}>취소</button> : <span className="meta-pill">필수: 제목</span>}</div>
        <form className="stacked-form compact-form" onSubmit={onSubmit}>
          <div className="form-grid three-columns">
            <label>유형<select value={logForm.work_type} onChange={(event) => setLogForm({ ...logForm, work_type: event.target.value as WorkType })}>{Object.entries(workTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>수행일<input type="date" value={logForm.log_date} onChange={(event) => setLogForm({ ...logForm, log_date: event.target.value })} /></label>
            <label>소요(분)<input min="0" type="number" value={logForm.duration_minutes} onChange={(event) => setLogForm({ ...logForm, duration_minutes: event.target.value })} /></label>
          </div>
          <div className="form-grid two-columns">
            <label>업무명<input placeholder="예: 주간 리포트 자동화" value={logForm.title} onChange={(event) => setLogForm({ ...logForm, title: event.target.value })} /></label>
            <label>협업자<input placeholder="예: PM, 운영팀" value={logForm.collaborators} onChange={(event) => setLogForm({ ...logForm, collaborators: event.target.value })} /></label>
          </div>
          <div className="form-grid two-columns">
            <label>수행 내용<textarea placeholder="실제로 한 일" value={logForm.content} onChange={(event) => setLogForm({ ...logForm, content: event.target.value })} /></label>
            <label>결정 사항<textarea placeholder="판단/결정" value={logForm.decisions} onChange={(event) => setLogForm({ ...logForm, decisions: event.target.value })} /></label>
          </div>
          <div className="form-grid two-columns">
            <label>다음 액션<textarea placeholder="다음에 할 일" value={logForm.next_actions} onChange={(event) => setLogForm({ ...logForm, next_actions: event.target.value })} /></label>
            <label>블로커<textarea placeholder="막힌 점" value={logForm.blockers} onChange={(event) => setLogForm({ ...logForm, blockers: event.target.value })} /></label>
          </div>
          <div className="form-actions"><button type="submit" disabled={isSavingLog}>{isSavingLog ? "저장 중" : editingLogId ? "수정 저장" : "로그 추가"}</button></div>
        </form>
      </section>

      <section className="panel log-timeline-panel">
        <div className="panel-title-row"><h2>타임라인</h2><span className="count-badge">{sortedLogs.length}개</span></div>
        {sortedLogs.length === 0 ? <div className="empty-state">로그 없음</div> : null}
        <div className="log-timeline">
          {sortedLogs.map((log) => (
            <article className="log-timeline-item" key={log.id}>
              <time>{log.log_date}</time>
              <div>
                <div className="jira-card-topline">
                  <span className="meta-pill status-navy">{workTypeLabels[log.work_type]}</span>
                  <span className="meta-pill">{log.duration_minutes}분</span>
                  <span className="meta-pill">{log.project_title || projectTitle}</span>
                </div>
                <strong>{linkedWorkTitle(log, tasks)}</strong>
                <small>{log.next_actions || "다음 액션 없음"}</small>
                <details className="log-detail-toggle">
                  <summary>상세</summary>
                  <dl>
                    <div><dt>수행 내용</dt><dd>{log.content || "-"}</dd></div>
                    <div><dt>판단/결정</dt><dd>{log.decisions || "-"}</dd></div>
                    <div><dt>협의 대상</dt><dd>{log.collaborators || "-"}</dd></div>
                    <div><dt>다음 액션</dt><dd>{log.next_actions || "-"}</dd></div>
                    <div><dt>블로커</dt><dd>{log.blockers || "-"}</dd></div>
                  </dl>
                </details>
                <div className="form-actions compact-actions"><button className="secondary-button" type="button" onClick={() => startEditLog(log)}>수정</button><button className="danger-button" type="button" onClick={() => void deleteLog(log)}>삭제</button></div>
              </div>
            </article>
          ))}
        </div>
      </section>

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
  logs,
  outcomeForm,
  outcomes,
  quantitativeOutcomes,
  resumeReadyOutcomes,
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
  logs: WorkLogItem[];
  outcomeForm: OutcomeForm;
  outcomes: ProjectOutcome[];
  quantitativeOutcomes: number;
  resumeReadyOutcomes: number;
  setOutcomeForm: (form: OutcomeForm) => void;
  startEditOutcome: (outcome: ProjectOutcome) => void;
  tasks: ProjectTask[];
  onApplyCandidate: (candidate: OutcomeCandidate) => void;
  onCancel: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const sortedOutcomes = [...outcomes].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const sortedLogs = [...logs].sort((a, b) => b.log_date.localeCompare(a.log_date));
  const outcomeCandidates = buildOutcomeCandidates(logs, tasks, outcomes);

  return (
    <section className="outcome-dashboard">
      <section className="panel outcome-candidate-panel">
        <div className="panel-title-row">
          <h2>성과 후보</h2>
          <span className="count-badge">{outcomeCandidates.length}개</span>
        </div>
        {outcomeCandidates.length === 0 ? <div className="empty-state">근거 로그 기반 후보 없음</div> : null}
        {outcomeCandidates.length > 0 ? (
          <div className="outcome-candidate-grid">
            {outcomeCandidates.map((candidate) => (
              <article className="candidate-card outcome-candidate-card" key={candidate.id}>
                <div className="panel-title-row">
                  <strong>{candidate.title}</strong>
                  <span className="meta-pill">{candidate.source === "task" ? "완료 업무" : "업무 로그"}</span>
                </div>
                <p>{candidate.after_state || "저장된 근거를 성과로 정리합니다."}</p>
                <div className="outcome-candidate-facts">
                  <div><span>근거 로그</span><b>{candidate.evidence_work_log_ids.length}개</b></div>
                  <div><span>수치</span><b>사용자 입력</b></div>
                  <div><span>이력서</span><b>보류</b></div>
                </div>
                <div className="outcome-candidate-evidence">
                  {candidate.evidence.slice(0, 3).map((item) => <span key={item}>{item}</span>)}
                </div>
                <div className="form-actions compact-actions">
                  <button className="secondary-button" type="button" onClick={() => onApplyCandidate(candidate)}>양식에 적용</button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel log-form-panel outcome-form-panel">
        <div className="panel-title-row"><h2>{editingOutcomeId ? "성과 수정" : "성과 추가"}</h2>{editingOutcomeId ? <button className="secondary-button" type="button" onClick={onCancel}>취소</button> : <span className="meta-pill">필수: 개선 항목</span>}</div>
        <form className="stacked-form compact-form" onSubmit={onSubmit}>
          <div className="form-grid three-columns">
            <label>유형<select value={outcomeForm.outcome_type} onChange={(event) => setOutcomeForm({ ...outcomeForm, outcome_type: event.target.value as OutcomeType, metric_value: event.target.value === "qualitative" ? "" : outcomeForm.metric_value })}>{Object.entries(outcomeTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>측정 지표<input placeholder="예: 처리 시간" value={outcomeForm.metric_name} onChange={(event) => setOutcomeForm({ ...outcomeForm, metric_name: event.target.value })} /></label>
            <label>이력서 반영<select value={outcomeForm.resume_ready ? "yes" : "no"} onChange={(event) => setOutcomeForm({ ...outcomeForm, resume_ready: event.target.value === "yes" })}><option value="no">보류</option><option value="yes">가능</option></select></label>
          </div>
          <div className="form-grid three-columns">
            <label>개선 항목<input placeholder="예: 주간 현황 취합 자동화" value={outcomeForm.title} onChange={(event) => setOutcomeForm({ ...outcomeForm, title: event.target.value })} /></label>
            <label>수치<input disabled={outcomeForm.outcome_type === "qualitative"} inputMode="decimal" placeholder={outcomeForm.outcome_type === "quantitative" ? "사용자 확정값" : "정성 성과"} value={outcomeForm.metric_value} onChange={(event) => setOutcomeForm({ ...outcomeForm, metric_value: event.target.value })} /></label>
            <label>단위<input placeholder="예: 분, 건, %" value={outcomeForm.metric_unit} onChange={(event) => setOutcomeForm({ ...outcomeForm, metric_unit: event.target.value })} /></label>
          </div>
          <div className="form-grid two-columns">
            <label>개선 전<textarea placeholder="Before" value={outcomeForm.before_state} onChange={(event) => setOutcomeForm({ ...outcomeForm, before_state: event.target.value })} /></label>
            <label>개선 후<textarea placeholder="After" value={outcomeForm.after_state} onChange={(event) => setOutcomeForm({ ...outcomeForm, after_state: event.target.value })} /></label>
          </div>
          <label>근거 로그
            <select multiple value={outcomeForm.evidence_work_log_ids} onChange={(event) => setOutcomeForm({ ...outcomeForm, evidence_work_log_ids: Array.from(event.target.selectedOptions, (option) => option.value) })}>
              {sortedLogs.map((log) => <option key={log.id} value={log.id}>{log.log_date} · {workTypeLabels[log.work_type]} · {log.title}</option>)}
            </select>
          </label>
          <div className="form-actions"><button type="submit" disabled={isSavingOutcome}>{isSavingOutcome ? "저장 중" : editingOutcomeId ? "수정 저장" : "성과 추가"}</button></div>
        </form>
      </section>

      <section className="summary-grid inline outcome-metrics" aria-label="성과 지표">
        <div className="metric-card"><span>전체</span><strong>{outcomes.length}</strong></div>
        <div className="metric-card"><span>정량</span><strong>{quantitativeOutcomes}</strong></div>
        <div className="metric-card"><span>정성</span><strong>{outcomes.length - quantitativeOutcomes}</strong></div>
        <div className="metric-card"><span>이력서 가능</span><strong>{resumeReadyOutcomes}</strong></div>
      </section>

      <section className="outcome-card-grid">
        {sortedOutcomes.length === 0 ? <div className="empty-state">성과 없음</div> : null}
        {sortedOutcomes.map((outcome) => (
          <article className="candidate-card outcome-card" key={outcome.id}>
            <div className="panel-title-row"><strong>{outcome.title}</strong>{outcome.resume_ready ? <span className="meta-pill priority-medium">이력서 가능</span> : <span className="meta-pill">보류</span>}</div>
            <div className="outcome-facts">
              <div><span>Before</span><b>{outcome.before_state || "-"}</b></div>
              <div><span>After</span><b>{outcome.after_state || "-"}</b></div>
              <div><span>지표</span><b>{outcome.metric_name || "-"}</b></div>
              <div><span>수치</span><b>{outcome.metric_value ?? "-"}</b></div>
              <div><span>단위</span><b>{outcome.metric_unit || "-"}</b></div>
              <div><span>근거 로그</span><b>{outcomeEvidence(outcome, logs)}</b></div>
            </div>
            <div className="form-actions compact-actions"><button className="secondary-button" type="button" onClick={() => startEditOutcome(outcome)}>수정</button><button className="danger-button" type="button" onClick={() => void deleteOutcome(outcome)}>삭제</button></div>
          </article>
        ))}
      </section>

    </section>
  );
}
