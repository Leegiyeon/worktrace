import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const globals = read("app/globals.css");
const layoutPage = read("app/layout.tsx");
const logoComponent = read("app/components/AppLogo.tsx");
const dashboardPage = read("app/page.tsx");
const projectsPage = read("app/projects/page.tsx");
const detailPage = read("app/projects/[projectId]/page.tsx");
const careerPanel = read("app/projects/[projectId]/CareerPanel.tsx");
const reportsPage = read("app/reports/page.tsx");
const readme = read("../README.md");

test("global logo always links back to dashboard", () => {
  assert.match(layoutPage, /<AppLogo \/>/);
  assert.match(logoComponent, /href="\/"/);
  assert.match(logoComponent, /대시보드로 이동/);
  assert.match(globals, /\.app-logo/);
});

test("global header exposes compact product navigation", () => {
  assert.match(layoutPage, /className="app-header-inner"/);
  assert.match(layoutPage, /className="app-nav"/);
  for (const label of ["대시보드", "프로젝트", "리포트"]) {
    assert.match(layoutPage, new RegExp(label));
  }
  assert.match(globals, /\.app-nav/);
});

test("top-level work surfaces prioritize commands and data over explanatory chrome", () => {
  for (const source of [dashboardPage, projectsPage, detailPage, reportsPage]) {
    assert.doesNotMatch(source, /className="section-kicker"/);
    assert.doesNotMatch(source, /className="page-subtitle"/);
  }
});

test("create and edit flows use explicit action labels", () => {
  assert.match(projectsPage, /프로젝트 생성/);
  assert.match(projectsPage, /프로젝트 추가/);
  assert.match(detailPage, /업무 추가/);
  assert.match(detailPage, /로그 추가/);
  assert.match(detailPage, /로그 수정/);
  assert.match(detailPage, /성과 추가/);
  assert.match(detailPage, /성과 수정/);
  assert.match(detailPage, /수정 저장/);
  assert.match(reportsPage, /리포트 생성/);
});

test("project logs tab exposes editable work-log evidence fields", () => {
  for (const label of ["결정 사항", "협업자", "다음 액션", "블로커"]) {
    assert.match(detailPage, new RegExp(label));
  }
  assert.match(detailPage, /handleSaveLog/);
  assert.match(detailPage, /startEditLog/);
  assert.match(detailPage, /deleteLog/);
  assert.match(detailPage, /\/api\/work-logs\/\$\{editingLogId\}/);
  assert.match(detailPage, /\/api\/work-logs\/\$\{log\.id\}/);
});

test("project outcomes tab exposes editable evidence-based outcome fields", () => {
  for (const label of ["개선 항목", "개선 전", "개선 후", "측정 지표", "근거 로그", "이력서 반영"]) {
    assert.match(detailPage, new RegExp(label));
  }
  assert.match(detailPage, /handleSaveOutcome/);
  assert.match(detailPage, /startEditOutcome/);
  assert.match(detailPage, /deleteOutcome/);
  assert.match(detailPage, /\/api\/projects\/\$\{projectId\}\/outcomes\/\$\{editingOutcomeId\}/);
  assert.match(detailPage, /\/api\/projects\/\$\{projectId\}\/outcomes\/\$\{outcome\.id\}/);
  assert.match(detailPage, /outcome_type === "quantitative" && !outcomeForm\.metric_value\.trim\(\)/);
});

test("daily workflow exposes an attention queue and project quick actions", () => {
  assert.match(dashboardPage, /지금 할 일/);
  assert.match(dashboardPage, /className="attention-queue"/);
  assert.match(detailPage, /className="project-quick-actions"/);
  for (const helper of ["openCreateTask", "openCreateLog", "openCreateOutcome"]) {
    assert.match(detailPage, new RegExp(`function ${helper}\\(\\)`));
  }
  for (const setter of ["setEditingTaskId", "setEditingLogId", "setEditingOutcomeId"]) {
    assert.match(detailPage, new RegExp(`${setter}\\(null\\)`));
  }
  assert.doesNotMatch(detailPage, /WBS 업로드/);
});

test("career assets can be reviewed, edited, saved, and copied", () => {
  for (const label of ["수행 요약", "성과 요약", "이력서 문장", "경력기술서", "포트폴리오", "STAR 답변"]) {
    assert.match(careerPanel, new RegExp(label));
  }
  assert.match(careerPanel, /handleSave/);
  assert.match(careerPanel, /method: "PATCH"/);
  assert.match(careerPanel, /수정 저장/);
  assert.match(careerPanel, /Markdown 복사/);
});

test("UI polish styles preserve accessible alignment and focus affordances", () => {
  assert.match(globals, /\.stacked-form > button/);
  assert.match(globals, /\.form-actions\s*\{/);
  assert.match(globals, /focus-visible/);
  assert.match(globals, /\.task-form-panel/);
  assert.match(globals, /\.data-table tbody tr:hover/);
  assert.match(dashboardPage, /className="quick-advanced-fields"/);
  assert.match(globals, /\.quick-advanced-fields/);
});

test("Apple-inspired frontend polish keeps shared tokens and documented route rhythm", () => {
  for (const token of ["--radius-lg", "--radius-md", "--control-height", "--shadow-soft"]) {
    assert.match(globals, new RegExp(token));
  }
  assert.match(globals, /-apple-system/);
  assert.match(globals, /\.compact-topbar/);
  assert.match(readme, /Frontend UI polish conventions/);
  for (const route of ["Dashboard", "Projects", "Reports"]) {
    assert.match(readme, new RegExp(route));
  }
  assert.match(readme, /frontend-only/);
});
