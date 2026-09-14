import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ModuleKind, transpileModule } from "typescript";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const dashboardPage = read("app/page.tsx");
const projectsPage = read("app/projects/page.tsx");
const detailPage = read("app/projects/[projectId]/page.tsx");
const globals = read("app/globals.css");
const helper = read("app/projects/progress-display.ts");
const compiledHelper = transpileModule(helper, { compilerOptions: { module: ModuleKind.ESNext } }).outputText;
const { projectProgressDisplay, scopedProjectAverage, wbsActivityCounts } = await import(`data:text/javascript;base64,${Buffer.from(compiledHelper).toString("base64")}`);

test("progress values distinguish an unscoped project from a real zero", () => {
  assert.equal(projectProgressDisplay({ progress_basis: "unscoped", progress_percent: 0 }).percent, null);
  assert.equal(projectProgressDisplay({ progress_basis: "wbs", progress_percent: 0 }).label, "0%");
  assert.equal(scopedProjectAverage([]).label, "산정 전");
  assert.equal(scopedProjectAverage([{ progress_basis: "unscoped", progress_percent: 0 }]).label, "산정 전");
  assert.deepEqual(scopedProjectAverage([
    { progress_basis: "wbs", progress_percent: 60 },
    { progress_basis: "milestone", progress_percent: 100 },
    { progress_basis: "unscoped", progress_percent: 0 }
  ]), { label: "80%", percent: 80, isScoped: true, scopedProjects: 2 });
});

test("adding reference activities does not increase counted WBS", () => {
  const counted = [{ counts_toward_progress: true }, { counts_toward_progress: true }];
  assert.deepEqual(wbsActivityCounts([...counted, { counts_toward_progress: false }]), {
    allActivities: 3, countedWbs: 2, referenceActivities: 1
  });
  assert.deepEqual(wbsActivityCounts([]), { allActivities: 0, countedWbs: 0, referenceActivities: 0 });
});

test("progress helper keeps unscoped projects out of averages", () => {
  assert.match(helper, /project\.progress_basis === "unscoped"/);
  assert.match(helper, /label: "산정 전"/);
  assert.match(helper, /const scopedProjects = projects\.filter\(\(project\) => projectProgressDisplay\(project\)\.isScoped\)/);
  assert.match(helper, /scopedProjects\.reduce\(\(sum, project\) => sum \+ project\.progress_percent, 0\) \/ scopedProjects\.length/);
});

test("dashboard distinguishes all activities from counted WBS", () => {
  assert.match(dashboardPage, /wbsActivityCounts\(allTasks\)/);
  assert.match(dashboardPage, /<span>잔여 WBS<\/span><strong>\{dashboard\.remainingTasks\}<\/strong>/);
  assert.match(dashboardPage, /평균 진척 \{dashboard\.averageProgress\.label\}/);
  assert.match(dashboardPage, /tasksUnavailable \? "-" : `산정 \$\{dashboard\.activityCounts\.countedWbs\} \/ 전체 \$\{dashboard\.activityCounts\.allActivities\}`/);
  assert.match(dashboardPage, /이슈 \{tasksUnavailable \? "-" : issueCount\}/);
  assert.doesNotMatch(dashboardPage, /projects\.reduce\(\(sum, project\) => sum \+ project\.progress_percent/);
});

test("project list and detail share progress display instead of treating unscoped as zero", () => {
  assert.match(projectsPage, /scopedProjectAverage\(projects\)/);
  assert.match(projectsPage, /projectProgressDisplay\(project\)/);
  assert.match(detailPage, /projectProgressDisplay\(project\)\.label/);
  assert.match(detailPage, /projectProgressDisplay\(project\)\.percent === null/);
  assert.doesNotMatch(projectsPage, /dashboard\.averageProgress === null/);
});

test("task status UI does not fabricate item-level percentages", () => {
  assert.doesNotMatch(detailPage, /function taskProgress/);
  assert.doesNotMatch(detailPage, /if \(task\.status === "in_progress"\) return 50/);
  assert.doesNotMatch(detailPage, /if \(task\.status === "on_hold"\) return 10/);
  assert.doesNotMatch(detailPage, /<th>진행률<\/th>/);
  assert.match(detailPage, /task\.counts_toward_progress \? "산정 WBS" : "참고 활동"/);
});

test("WBS form exposes existing progress scope and milestone API fields", () => {
  assert.match(detailPage, /fetch\(`\/api\/projects\/\$\{projectId\}\/milestones`, \{ cache: "no-store" \}\)\.catch\(\(\) => null\)/);
  assert.match(detailPage, /milestonesResponse\?\.ok/);
  assert.match(detailPage, /milestone_id: task\.milestone_id \?\? ""/);
  assert.match(detailPage, /counts_toward_progress: task\.counts_toward_progress/);
  assert.match(detailPage, /milestone_id: taskForm\.milestone_id \|\| null/);
  assert.match(detailPage, /selectedMilestoneMissing/);
  assert.match(detailPage, /type="checkbox"/);
  assert.match(detailPage, /checked=\{taskForm\.counts_toward_progress\}/);
  assert.match(globals, /\.checkbox-row input\[type="checkbox"\]/);
});
