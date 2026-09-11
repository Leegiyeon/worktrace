import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const globals = read("app/globals.css");
const layoutPage = read("app/layout.tsx");
const logoComponent = read("app/components/AppLogo.tsx");
const headerComponent = read("app/components/AppHeader.tsx");
const dashboardPage = read("app/page.tsx");
const projectsPage = read("app/projects/page.tsx");
const detailPage = read("app/projects/[projectId]/page.tsx");
const careerPanel = read("app/projects/[projectId]/CareerPanel.tsx");
const reportsPage = read("app/reports/page.tsx");
const readme = read("../README.md");

test("global logo always links back to dashboard", () => {
  assert.match(layoutPage, /<AppHeader/);
  assert.match(headerComponent, /<AppLogo \/>/);
  assert.match(logoComponent, /href="\/"/);
  assert.match(logoComponent, /대시보드로 이동/);
  assert.match(globals, /\.app-logo/);
});

test("global header exposes compact product navigation", () => {
  assert.match(layoutPage, /<AppHeader/);
  assert.match(headerComponent, /className="app-header-inner"/);
  assert.match(headerComponent, /className="app-nav"/);
  for (const label of ["대시보드", "프로젝트", "리포트"]) {
    assert.match(headerComponent, new RegExp(label));
  }
  assert.match(globals, /\.app-nav/);
  assert.match(headerComponent, /aria-current/);
  assert.match(globals, /\.app-nav a\[aria-current="page"\]/);
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

test("shared typography and control tokens keep form surfaces consistent", () => {
  for (const token of ["--font-sans", "--font-mono", "--control-height", "--compact-control-height", "--page-gutter"]) {
    assert.match(globals, new RegExp(token));
  }
  assert.match(globals, /input::placeholder/);
  assert.match(globals, /input:disabled/);
  assert.match(globals, /select\[multiple\]/);
  assert.match(globals, /\.data-table select/);
  assert.doesNotMatch(globals, /font-family:\s*Arial/);
});

test("responsive grids preserve useful intermediate layouts before stacking", () => {
  assert.match(globals, /\.summary-grid\s*\{[\s\S]*?repeat\(auto-fit,\s*minmax\(min\(100%,\s*190px\),\s*1fr\)\)/);
  assert.match(globals, /\.task-board\s*\{[\s\S]*?repeat\(auto-fit,\s*minmax\(min\(100%,\s*230px\),\s*1fr\)\)/);
  assert.match(globals, /@media \(max-width:\s*1100px\)[\s\S]*?\.dashboard-grid[\s\S]*?"capture attention"/);
  assert.match(globals, /@media \(max-width:\s*900px\)[\s\S]*?\.form-grid\.three-columns[\s\S]*?repeat\(2/);
  assert.match(globals, /@media \(max-width:\s*640px\)[\s\S]*?\.form-grid\.two-columns[\s\S]*?grid-template-columns:\s*1fr/);
  assert.match(globals, /\.board-layout\s*\{[\s\S]*?grid-template-columns:\s*1fr/);
  assert.match(detailPage, /className="panel task-form-panel"/);
  assert.match(detailPage, /className="primary-button"[^>]*>업무 추가/);
  assert.match(careerPanel, /className="primary-button"/);
});

test("shared surfaces keep controls, panels, and responsive regions aligned", () => {
  assert.match(globals, /\/\* Shared layout normalization \*\//);
  assert.match(globals, /\.panel-title-row\s*\{[\s\S]*?min-height:\s*var\(--control-height\)/);
  assert.match(globals, /button,[\s\S]*?height:\s*var\(--control-height\)/);
  assert.match(globals, /input,[\s\S]*?height:\s*var\(--control-height\)/);
  assert.match(globals, /\.summary-grid,[\s\S]*?align-items:\s*stretch/);
  assert.match(globals, /@media \(max-width:\s*760px\)[\s\S]*?\.app-header-inner[\s\S]*?grid-template-columns:\s*auto minmax\(0,\s*1fr\)/);
  assert.match(globals, /@media \(max-width:\s*480px\)[\s\S]*?\.project-quick-actions > \*/);
  assert.match(globals, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.match(reportsPage, /className="report-evidence-grid"/);
  assert.match(globals, /\.report-evidence-grid\s*\{[\s\S]*?grid-template-areas/);
  assert.doesNotMatch(reportsPage, /className="dashboard-grid"/);
  assert.match(globals, /\.delayed-panel \.dense-list-row b/);
  assert.match(globals, /@media \(max-width:\s*760px\)[\s\S]*?\.calendar-month-panel[\s\S]*?display:\s*none/);
});

test("partial data failures stay distinct from valid empty states and can be retried", () => {
  for (const source of [dashboardPage, detailPage]) {
    assert.match(source, /loadFailures/);
    assert.match(source, /className="alert error data-load-alert" role="alert"/);
    assert.match(source, /다시 시도/);
  }
  assert.match(dashboardPage, /tasksUnavailable \? "-"/);
  assert.match(detailPage, /loadFailures\.includes\("logs"\) \? "-"/);
  assert.match(globals, /\.data-load-alert/);
});

test("mutations and copy actions expose accessible success status", () => {
  for (const source of [dashboardPage, projectsPage, detailPage, careerPanel, reportsPage]) {
    assert.match(source, /role="status"/);
    assert.match(source, /aria-live="polite"/);
  }
  for (const source of [dashboardPage, projectsPage, detailPage, careerPanel, reportsPage]) {
    assert.match(source, /role="alert"/);
  }
});

test("project tabs and inline task status controls have accessible names", () => {
  assert.match(detailPage, /aria-controls={`panel-\$\{tab\.id\}`}/);
  assert.match(detailPage, /role="tabpanel"/);
  assert.match(detailPage, /aria-labelledby="tab-overview"/);
  assert.match(detailPage, /aria-label={`\$\{task\.title\} 상태 변경`}/);
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
