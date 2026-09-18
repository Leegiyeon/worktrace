import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-plan-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
let tasks = [0, 1, 2, 3].map((index) => ({ id: `t${index}`, project_id: "p0", title: `계획 업무 ${index + 1}`, description: "명시적으로 관리할 업무", status: index < 2 ? "done" : "planned", milestone_id: index < 2 ? "m0" : "m1", counts_toward_progress: true, source_provider: null, source_key: null, priority: "medium", status_version: 1, due_date: null, completed_at: null, created_at: stamp, updated_at: stamp }));
const milestones = [0, 1].map((index) => ({ id: `m${index}`, project_id: "p0", title: `마일스톤 ${index + 1}`, weight: 50, total_tasks: 2, completed_tasks: index === 0 ? 2 : 0, derived_task_count: 0, progress_percent: index === 0 ? 100 : 0 }));
let plan = { version: 0, status: "unapproved", policy: "wbs", context_fingerprint: "a".repeat(64), total_tasks: 4, derived_task_count: 0, tasks, milestones, excluded_tasks: [], policy_errors: { wbs: [], milestone: [] }, history: [] };
const project = () => ({ id: "p0", title: "worktrace", description: "승인 계획 기반 진척 관리", role: "개발", status: "in_progress", service_status: "operating", total_tasks: 4, completed_tasks: 2, remaining_tasks: 2, milestone_count: 2, derived_task_count: plan.derived_task_count, progress_plan_status: plan.status, progress_plan_version: plan.version, progress_basis: plan.status === "approved" ? plan.policy : "unscoped", progress_percent: plan.status === "approved" ? 50 : null, updated_at: stamp });
let conflict = false, failRead = false, loseResponse = false, posts = 0;
const requests = new Map();
await page.route("**/api/**", async (route) => {
  const request = route.request(), pathname = new URL(request.url()).pathname;
  let result = [];
  if (pathname.endsWith("/plan")) {
    if (request.method() === "POST") {
      posts++;
      const body = request.postDataJSON();
      assert.equal(typeof body.exclusion_reason, "string");
      assert.match(body.request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
      if (conflict) return route.fulfill({ status: 409, json: { detail: { code: "PROJECT_PLAN_VERSION_CONFLICT", message: "계획 변경을 확인하세요." } } });
      if (requests.has(body.request_id)) assert.deepEqual(body, requests.get(body.request_id));
      else {
        assert.equal(body.expected_version, plan.version);
        assert.equal(body.expected_context_fingerprint, plan.context_fingerprint);
        assert.ok(body.reason.trim());
        if (plan.derived_task_count) assert.equal(body.reviewed_derived, true);
        if (plan.excluded_tasks.length) assert.ok(body.exclusion_reason.trim());
        requests.set(body.request_id, body);
        plan = { ...plan, version: plan.version + 1, status: "approved", policy: body.policy,
          history: [{ id: body.request_id, version: plan.version + 1, policy: body.policy, reason: body.reason,
            exclusion_reason: body.exclusion_reason, reviewed_derived: body.reviewed_derived, approved_at: stamp, actor_owner_id: "test-owner" }, ...plan.history] };
      }
      if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: "저장 응답 유실" } }); }
    } else if (failRead) return route.fulfill({ status: 503, json: { detail: "계획 조회 실패" } });
    result = plan;
  } else if (pathname === "/api/projects") result = [project()];
  else if (pathname === "/api/projects/p0") result = project();
  else if (pathname.endsWith("/tasks")) result = tasks;
  else if (pathname.endsWith("/milestones")) result = milestones;
  else if (pathname.endsWith("/lifecycle")) result = { ...project(), lifecycle_version: 0, pending_task_count: 2, history: [] };
  else if (pathname.endsWith("/repository") || pathname.endsWith("/github-status")) result = null;
  return route.fulfill({ json: result });
});
const region = () => page.getByRole("region", { name: "진행 계획 승인", exact: true });
const reason = () => region().getByLabel("승인 사유", { exact: true });
const exclusion = () => region().getByLabel("제외 사유", { exact: true });
const save = () => region().getByRole("button", { name: "진행 계획 승인", exact: true });
const openPlan = async () => {
  const disclosure = region().locator("details").first();
  if (await disclosure.count() && !(await disclosure.evaluate((element) => element.open))) await disclosure.locator("summary").first().click();
};
const refresh = async () => {
  const response = page.waitForResponse((res) => res.url().endsWith("/plan") && res.request().method() === "GET");
  await region().getByRole("button", { name: "최신 계획 다시 불러오기", exact: true }).click();
  await response;
  await page.waitForTimeout(100);
};
try {
  await page.goto(`${base}/projects/p0`);
  await region().getByText("미승인", { exact: true }).waitFor();
  await page.getByText("계획 미승인", { exact: true }).first().waitFor();
  await openPlan();
  await reason().fill("기본 WBS 산정 범위 확인");
  await save().dblclick();
  await region().getByRole("status").filter({ hasText: "승인했습니다" }).waitFor();
  assert.equal(posts, 1);
  assert.equal(plan.version, 1);
  assert.equal([...requests.values()][0].exclusion_reason, "");

  tasks = tasks.map((task, index) => index === 0 ? { ...task, source_provider: "derived-github", source_key: "commit-milestone:m0" } : task);
  tasks.push({ ...tasks[3], id: "reference", title: "다음 릴리스 범위의 참고 업무", counts_toward_progress: false });
  plan = { ...plan, status: "stale", context_fingerprint: "b".repeat(64), tasks, derived_task_count: 1, excluded_tasks: [{ id: "reference", title: "다음 릴리스 범위의 참고 업무" }] };
  await refresh();
  await openPlan();
  await region().getByText("재승인 필요", { exact: true }).waitFor();
  await page.getByText("계획 재승인 필요", { exact: true }).first().waitFor();
  await reason().fill("변경된 범위 확인");
  assert.equal(await save().isDisabled(), true);
  await exclusion().fill("후속 릴리스로 범위를 구분함");
  assert.equal(await save().isDisabled(), true);
  await region().getByRole("checkbox").check();
  await region().getByLabel("산정 정책", { exact: true }).selectOption("milestone");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const checkboxLayout = await region().getByRole("checkbox").evaluate((element) => {
      const box = element.getBoundingClientRect();
      const label = element.closest("label");
      const text = label.querySelector("span").getBoundingClientRect();
      return { width: box.width, textWidth: text.width, right: text.right, parentRight: label.getBoundingClientRect().right };
    });
    assert.ok(checkboxLayout.width <= 24 && checkboxLayout.textWidth > 100, "checkbox crowds its label");
    assert.ok(checkboxLayout.right <= checkboxLayout.parentRight + 1, "checkbox label is clipped");
    if (width >= 1000) {
      const planBox = await region().boundingBox();
      const dueBox = await page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "이번 주 마감", exact: true }) }).boundingBox();
      const previewBox = await region().getByLabel("산정 WBS 미리보기", { exact: true }).boundingBox();
      const formBox = await region().locator("form").boundingBox();
      const progressBox = await page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "진척", exact: true }) }).boundingBox();
      assert.ok(planBox.width > width * 0.75, "approval review is squeezed into a summary column");
      assert.ok(dueBox.height < 600, "approval review stretches unrelated summary panels");
      assert.ok(formBox.x >= previewBox.x + previewBox.width, "desktop approval form must sit beside its preview");
      assert.ok(planBox.y < progressBox.y, "approval review leaves a sparse summary row above it");
    }
    await page.screenshot({ path: path.join(output, `plan-${width}.png`), fullPage: true });
    const controls = await region().locator("input,textarea,select,button").evaluateAll((elements) => elements.filter((el) => el.getClientRects().length).map((el) => {
      const { x, y, width, height } = el.getBoundingClientRect(); return { x, y, width, height };
    }));
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i], b = controls[j];
      assert.ok(a.x + a.width <= b.x + 1 || b.x + b.width <= a.x + 1 || a.y + a.height <= b.y + 1 || b.y + b.height <= a.y + 1, "controls overlap");
    }
  }
  conflict = true;
  await save().click();
  await region().getByRole("alert").waitFor();
  assert.equal(await save().isDisabled(), true);
  failRead = true;
  await refresh();
  assert.equal(await save().isDisabled(), true);
  assert.equal(await reason().inputValue(), "변경된 범위 확인");
  failRead = false; conflict = false;
  await refresh();
  await openPlan();
  assert.equal(await reason().inputValue(), "변경된 범위 확인");
  assert.equal(await exclusion().inputValue(), "후속 릴리스로 범위를 구분함");
  await region().getByRole("checkbox").check();
  loseResponse = true;
  await save().click();
  const retry = region().getByRole("button", { name: "동일 요청 다시 확인", exact: true });
  await retry.waitFor();
  assert.equal(await reason().isDisabled(), true);
  assert.equal(plan.version, 2);
  failRead = true;
  await refresh();
  assert.equal(await reason().isDisabled(), true);
  await retry.click();
  await retry.waitFor({ state: "hidden" });
  await region().getByRole("status").filter({ hasText: "승인했습니다" }).waitFor();
  assert.equal(plan.version, 2);
  assert.equal(requests.size, 2);
  failRead = false;
  await openPlan();
  await region().getByRole("button", { name: "승인 이력", exact: true }).click();
  await region().getByText("변경된 범위 확인", { exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log("PASS: approval scope/policy/acknowledgement, 4 responsive widths, conflict + failed reload draft retention, 503 exact replay, history and null exclusion protection");
} catch (error) {
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
