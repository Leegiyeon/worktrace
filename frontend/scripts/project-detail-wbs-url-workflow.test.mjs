import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const detailPage = read("app/projects/[projectId]/page.tsx");
const detailStyles = read("app/projects/[projectId]/page.module.css");

test("project detail initializes tab, WBS view, filters, and sort from URL params", () => {
  assert.match(detailPage, /usePathname, useRouter, useSearchParams/);
  assert.match(detailPage, /const activeTab: DetailTab = isDetailTab\(tabParam\) \? tabParam : "overview"/);
  assert.match(detailPage, /const taskViewMode: TaskViewMode = isTaskViewMode\(viewParam\) \? viewParam : "list"/);
  for (const param of ["status", "priority", "issue", "sort"]) {
    assert.match(detailPage, new RegExp(`searchParams\\.get\\("${param}"\\)`));
  }
  assert.match(detailPage, /router\.push\(queryString \? `\$\{pathname\}\?\$\{queryString\}` : pathname, \{ scroll: false \}\)/);
  assert.match(detailPage, /onClick=\{\(\) => setTaskView\(mode\)\}/);
  assert.doesNotMatch(detailPage, /useState<TaskViewMode>/);
});

test("WBS form is request-only, hides without clearing draft, and edit reuses the same form", () => {
  assert.match(detailPage, /const \[isTaskFormVisible, setIsTaskFormVisible\] = useState\(false\)/);
  assert.match(detailPage, /function showNewTaskForm\(\)[\s\S]*?setIsTaskFormVisible\(true\)[\s\S]*?updateProjectDetailUrl\(\{ tab: "tasks" \}\)/);
  assert.match(detailPage, /function hideTaskForm\(\) \{\s*setIsTaskFormVisible\(false\);\s*\}/);
  assert.match(detailPage, /function cancelTaskForm\(\)[\s\S]*?setTaskForm\(initialTaskForm\)[\s\S]*?setIsTaskFormVisible\(false\)/);
  assert.match(detailPage, /setEditingTaskId\(task\.id\)[\s\S]*?setTaskForm\([\s\S]*?counts_toward_progress: task\.counts_toward_progress[\s\S]*?setIsTaskFormVisible\(true\)[\s\S]*?setActiveDetailTab\("tasks"\)/);
  assert.doesNotMatch(detailPage, /setTaskViewMode\("board"\)/);
  assert.match(detailPage, /isTaskFormVisible \? <TaskFormPanel/);
  assert.match(detailPage, /onHide=\{hideTaskForm\}/);
});

test("WBS create and edit preserve milestone and progress-scope metadata", () => {
  assert.match(detailPage, /const payload = \{ \.\.\.taskForm, due_date: taskForm\.due_date \|\| null, milestone_id: taskForm\.milestone_id \|\| null \}/);
  assert.match(detailPage, /milestone_id: task\.milestone_id \?\? ""/);
  assert.match(detailPage, /counts_toward_progress: task\.counts_toward_progress/);
  assert.match(detailPage, /checked=\{taskForm\.counts_toward_progress\}/);
  assert.match(detailPage, /disabled=\{milestonesUnavailable\}/);
  assert.match(detailPage, /selectedMilestoneMissing/);
});

test("mobile WBS list renders as readable rows instead of a seven-column overflow table", () => {
  for (const label of ["WBS 항목", "상태", "우선순위", "이슈", "산정", "시작일", "마감일"]) {
    assert.match(detailPage, new RegExp(`data-label="${label}"`));
  }
  assert.match(detailStyles, /@media \(max-width: 720px\)/);
  assert.match(detailStyles, /\.projectDetailPage :global\(\.task-workspace \.data-table-wrap\) \{[\s\S]*?overflow-x: visible/);
  assert.match(detailStyles, /\.projectDetailPage :global\(\.dense-task-table thead\) \{[\s\S]*?display: none/);
  assert.match(detailStyles, /content: attr\(data-label\)/);
  assert.match(detailStyles, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(detailPage, /titleInput\.current\?\.focus\(\)/);
  assert.match(detailPage, /조건에 맞는 WBS 항목이 없습니다/);
});
