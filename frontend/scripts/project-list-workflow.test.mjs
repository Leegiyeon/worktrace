import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/projects/page.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/projects/page.module.css", import.meta.url), "utf8");

test("projects page is list-first with one compact context summary", () => {
  assert.match(page, /import styles from "\.\/page\.module\.css"/);
  assert.match(page, /className=\{`page-shell project-page \$\{styles\.shell\}`\}/);
  assert.match(page, /<h1>프로젝트<\/h1>/);
  assert.match(page, /className=\{styles\.context\} aria-live="polite"/);
  assert.doesNotMatch(page, /summary-grid dashboard-metrics/);
  assert.doesNotMatch(page, /metric-card/);
  assert.doesNotMatch(page, /<table className="data-table dense-task-table">/);
  assert.match(page, /<section className=\{styles\.listPanel\}>/);
  assert.doesNotMatch(page, /panel project-table-panel/);
});

test("project creation is opened from the header and preserves failed input", () => {
  assert.match(page, /aria-controls="project-create-panel"/);
  assert.match(page, /aria-expanded=\{isCreateOpen\}/);
  assert.match(page, /\{isCreateOpen \? \(/);
  assert.match(page, /<section className=\{styles\.createPanel\} id="project-create-panel">/);
  assert.match(page, /function cancelCreate\(\)/);
  assert.match(page, /setSaveErrorMessage\(error instanceof Error/);
  const saveFailureBlock = page.slice(page.indexOf("} catch (error) {"), page.indexOf("} finally {", page.indexOf("} catch (error) {")));
  assert.doesNotMatch(saveFailureBlock, /setForm\(initialForm\)/);
  assert.match(page, /const createdProject = \(await response\.json\(\)\) as ProjectSummary/);
  assert.match(page, /router\.push\(`\/projects\/\$\{createdProject\.id\}`\)/);
  assert.doesNotMatch(page, /await loadProjects\(\)/);
});

test("project list filters and sorts the existing dataset with stable URL query names", () => {
  assert.match(page, /type ProjectSort = "updated_desc" \| "title_asc" \| "progress_desc" \| "remaining_desc"/);
  assert.match(page, /type StatusFilter = "all" \| ProjectStatus/);
  assert.match(page, /setQuery\(readProjectListSearchParam\(params, "q"\)\)/);
  assert.match(page, /setStatusFilter\(readProjectListSearchParam\(params, "status"\)\)/);
  assert.match(page, /setSort\(readProjectListSearchParam\(params, "sort"\)\)/);
  assert.match(page, /window\.addEventListener\("popstate", applyUrlFilters\)/);
  assert.match(page, /params\.get\(name\)/);
  assert.match(page, /params\.set\("q", trimmedQuery\)/);
  assert.match(page, /params\.set\("status", statusFilter\)/);
  assert.match(page, /params\.set\("sort", sort\)/);
  assert.match(page, /window\.history\.replaceState/);
  assert.match(page, /<input name="q"/);
  assert.match(page, /<select name="status"/);
  assert.match(page, /<select name="sort"/);
  assert.match(page, /프로젝트 목록 필터/);
  assert.match(page, /프로젝트 상태 필터/);
  assert.match(page, /프로젝트 정렬/);
});

test("projects page separates loading, load error retry, true empty, and filtered empty", () => {
  assert.match(page, /loadErrorMessage/);
  assert.match(page, /saveErrorMessage/);
  assert.match(page, /!isLoading && !loadErrorMessage \? <span>진행/);
  assert.match(page, /role="alert"/);
  assert.match(page, /onClick=\{\(\) => loadProjects\(\)\}>다시 시도/);
  assert.match(page, /role="status">프로젝트를 불러오는 중입니다\./);
  assert.match(page, /표시할 프로젝트가 없습니다\./);
  assert.match(page, /조건에 맞는 프로젝트가 없습니다\./);
});

test("project rows stay responsive without card nesting or hidden title/status columns", () => {
  assert.match(page, /<article className=\{styles\.projectRow\}/);
  assert.match(page, /className=\{styles\.projectTitle\}/);
  assert.match(page, /status-navy/);
  assert.match(css, /\.projectRow\s*\{[\s\S]*grid-template-columns:\s*minmax\(220px, 1fr\) auto minmax\(150px, 0\.3fr\) minmax\(82px, auto\)/);
  assert.match(css, /@media \(max-width:\s*900px\)[\s\S]*\.projectRow\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) auto/);
  assert.match(css, /@media \(max-width:\s*520px\)[\s\S]*\.projectRow\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) auto/);
  assert.doesNotMatch(css, /\.progressCell,\s*\.counts\s*\{\s*justify-items: start/);
  assert.match(css, /@media \(max-width:\s*520px\)[\s\S]*\.controls\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  assert.doesNotMatch(css, /display:\s*none/);
});
