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
const reportsPage = read("app/reports/page.tsx");
const readme = read("../README.md");

test("global logo always links back to dashboard", () => {
  assert.match(layoutPage, /<AppLogo \/>/);
  assert.match(logoComponent, /href="\/"/);
  assert.match(logoComponent, /대시보드로 이동/);
  assert.match(globals, /\.app-logo/);
});

test("top-level work surfaces keep concise guidance subtitles", () => {
  for (const [name, source] of Object.entries({ dashboardPage, projectsPage, detailPage, reportsPage })) {
    assert.match(source, /className="page-subtitle"/, `${name} should include a compact page subtitle`);
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

test("UI polish styles preserve accessible alignment and focus affordances", () => {
  assert.match(globals, /\.stacked-form > button/);
  assert.match(globals, /\.form-actions\s*\{/);
  assert.match(globals, /focus-visible/);
  assert.match(globals, /\.task-form-panel/);
  assert.match(globals, /\.data-table tbody tr:hover/);
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
