import type { ProjectTask } from "./types";

export function recordedCompletionsThisWeek<T extends ProjectTask>(tasks: T[], now = new Date()): T[] {
  const koreaOffset = 9 * 60 * 60 * 1000;
  const monday = new Date(now.getTime() + koreaOffset);
  const daysSinceMonday = (monday.getUTCDay() + 6) % 7;
  monday.setUTCDate(monday.getUTCDate() - daysSinceMonday);
  monday.setUTCHours(0, 0, 0, 0);
  const start = monday.getTime() - koreaOffset;
  return tasks.filter((task) => {
    if (task.status !== "done" || !task.completed_at || task.source_provider === undefined || task.source_provider === "derived-github") return false;
    const completed = Date.parse(task.completed_at);
    return Number.isFinite(completed) && completed >= start && completed <= now.getTime();
  }).sort((a, b) => Date.parse(b.completed_at!) - Date.parse(a.completed_at!));
}

export function completionDateLabel(value: string | null | undefined): string {
  if (!value || !Number.isFinite(Date.parse(value))) return "미확인";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}
