import { projectProgressDisplay } from "./progress-display";
import type { ProjectSummary } from "./types";

export function ProgressEvidence({ project }: { project: ProjectSummary }) {
  const progress = projectProgressDisplay(project);
  const formula = project.progress_plan_status === "unapproved"
    ? "계획 승인 필요"
    : project.progress_plan_status === "stale"
      ? "계획 재승인 필요"
      : project.progress_basis === "milestone"
        ? "마일스톤별 완료 비율 × 가중치의 합 / 전체 가중치 합"
        : project.progress_basis === "wbs"
          ? "산정 대상 완료 WBS / 산정 대상 전체 WBS × 100"
          : project.progress_plan_status === "approved"
            ? "산정 대상 WBS 없음"
            : "계획 승인 상태 미확인";
  return <details className="progress-evidence">
    <summary>수치 산정 근거</summary>
    <dl>
      <div><dt>산정 방식</dt><dd>{progress.basisLabel}</dd></div>
      <div><dt>진행 계획 승인</dt><dd>{project.progress_plan_status === "approved" ? `승인됨 · v${project.progress_plan_version ?? "?"}` : project.progress_plan_status === "stale" ? "재승인 필요" : project.progress_plan_status === "unapproved" ? "미승인" : "기준 미확인"}</dd></div>
      <div><dt>등록 WBS</dt><dd>완료 {project.completed_tasks} / 전체 {project.total_tasks} · 잔여 {project.remaining_tasks}</dd></div>
      <div><dt>자동 구성 WBS</dt><dd>{project.derived_task_count === undefined ? "출처 미확인" : `${project.derived_task_count}개`}</dd></div>
      <div><dt>계산식</dt><dd>{formula}</dd></div>
      <div><dt>프로젝트 상태</dt><dd>사용자 지정 · WBS 완료율과 별도</dd></div>
    </dl>
  </details>;
}
