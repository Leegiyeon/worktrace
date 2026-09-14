import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const detailPage = read("app/projects/[projectId]/page.tsx");
const detailStyles = read("app/projects/[projectId]/page.module.css");

test("work log form is hidden until an explicit add or edit action and can hide without clearing draft", () => {
  assert.match(detailPage, /const \[isLogFormVisible, setIsLogFormVisible\] = useState\(false\)/);
  const reopen = detailPage.slice(detailPage.indexOf("function showNewLogForm"), detailPage.indexOf("function hideLogForm"));
  assert.match(reopen, /setIsLogFormVisible\(true\)/);
  assert.doesNotMatch(reopen, /setEditingLogId\(null\)/);
  assert.match(detailPage, /function hideLogForm\(\) \{\s*setIsLogFormVisible\(false\);\s*\}/);
  assert.match(detailPage, /function cancelLogForm\(\)[\s\S]*?setLogForm\(createInitialWorkLogForm\(\)\)[\s\S]*?setIsLogFormVisible\(false\)/);
  assert.match(detailPage, /setEditingLogId\(log\.id\)[\s\S]*?setLogForm\([\s\S]*?blockers: log\.blockers[\s\S]*?setIsLogFormVisible\(true\)[\s\S]*?setActiveDetailTab\("logs"\)/);
  assert.match(detailPage, /!isLogFormVisible \? <button className="primary-button" disabled=\{isSavingLog\} type="button" onClick=\{showNewLogForm\}/);
  assert.match(detailPage, /\{isLogFormVisible \? \(\s*<section className="panel log-form-panel">/);
  assert.match(detailPage, /onHide=\{hideLogForm\}/);
  assert.match(detailPage, /titleInput\.current\?\.focus\(\)/);
});

test("work log save uses the API response locally and preserves failed input", () => {
  assert.match(detailPage, /const savedLog = \(await response\.json\(\)\) as WorkLogItem/);
  assert.match(detailPage, /setWorkLogs\(\(current\) => editingLogId[\s\S]*?current\.map\(\(log\) => log\.id === savedLog\.id \? savedLog : log\)[\s\S]*?: \[\.\.\.current, savedLog\]/);
  assert.match(detailPage, /setIsLogFormVisible\(false\)[\s\S]*?setSuccessMessage\(success\)/);
  const saveCatch = detailPage.slice(detailPage.indexOf("async function handleSaveLog"), detailPage.indexOf("function startEditLog"));
  assert.doesNotMatch(saveCatch, /await loadProject\(\)/);
  assert.doesNotMatch(saveCatch.slice(saveCatch.indexOf("} catch (error) {")), /setLogForm\(createInitialWorkLogForm\(\)\)/);
});

test("work log timeline is first, filtered, chronological, and does not substitute task or duplicate project badges", () => {
  assert.match(detailPage, /<section className="log-dashboard timeline-first-log-dashboard">\s*<section className="panel log-timeline-panel">/);
  assert.match(detailPage, /const sortedLogs = useMemo\(\(\) => \[\.\.\.logs\]\.sort\(\(a, b\) => b\.log_date\.localeCompare\(a\.log_date\)/);
  assert.match(detailPage, /const \[query, setQuery\] = useState\(""\)/);
  assert.match(detailPage, /const \[typeFilter, setTypeFilter\] = useState<WorkType \| "all">\("all"\)/);
  assert.match(detailPage, /className="list-toolbar work-log-filter-toolbar" aria-label="업무 로그 필터"/);
  assert.match(detailPage, /name="work-log-q"/);
  assert.match(detailPage, /name="work-log-type"/);
  assert.match(detailPage, /조건에 맞는 업무 로그가 없습니다\./);
  assert.match(detailPage, /<strong>\{log\.title\}<\/strong>/);
  assert.doesNotMatch(detailPage, /linkedWorkTitle/);
  assert.doesNotMatch(detailPage, /log\.project_title \|\| projectTitle/);
});

test("work log quick entry keeps core fields visible and detailed fields in disclosure", () => {
  assert.match(detailPage, /className="stacked-form compact-form quick-capture-form work-log-form"/);
  assert.match(detailPage, /업무명<input ref=\{titleInput\}/);
  assert.match(detailPage, /수행일<input disabled=\{isSavingLog\} type="date"/);
  assert.match(detailPage, /유형<select disabled=\{isSavingLog\}/);
  assert.match(detailPage, /수행 내용<textarea disabled=\{isSavingLog\}/);
  assert.match(detailPage, /<details className="quick-advanced-fields work-log-detail-fields">/);
  for (const field of ["decisions", "collaborators", "next_actions", "blockers", "duration_minutes"]) {
    assert.match(detailPage, new RegExp(`logForm\\.${field}`));
  }
  assert.match(detailPage, /<div><dt>소요 시간<\/dt><dd>\{log\.duration_minutes\}분<\/dd><\/div>/);
});

test("work log timeline layout is scoped and mobile readable", () => {
  assert.match(detailStyles, /\.projectDetailPage :global\(\.timeline-first-log-dashboard\) \{[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(detailStyles, /\.projectDetailPage :global\(\.timeline-first-log-dashboard \.log-timeline-panel\),[\s\S]*?grid-column: 1 \/ -1/);
  assert.match(detailStyles, /\.projectDetailPage :global\(\.work-log-filter-toolbar\) \{[\s\S]*?grid-template-columns: minmax\(220px, 1fr\) minmax\(180px, 0\.32fr\)/);
  assert.match(detailStyles, /@media \(max-width: 720px\)[\s\S]*\.projectDetailPage :global\(\.work-log-filter-toolbar\),[\s\S]*?grid-template-columns: 1fr/);
  assert.match(detailStyles, /\.projectDetailPage :global\(\.log-timeline-item small\) \{[\s\S]*?white-space: normal/);
});
