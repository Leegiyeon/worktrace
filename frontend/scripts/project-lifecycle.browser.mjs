import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-lifecycle-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
let lifecycle = { status: "done", service_status: "unknown", development_ended_on: null, lifecycle_version: 0, lifecycle_confirmed_at: null, pending_task_count: 1, history: [] };
const project = () => ({ id: "p0", title: "emanual", description: "", objective: "", success_criteria: "", ...lifecycle, role: "개발", total_tasks: 1, completed_tasks: 0, remaining_tasks: 1, milestone_count: 0, progress_basis: "wbs", progress_percent: 0, derived_task_count: 0, updated_at: stamp });
const tasks = [{ id: "t0", project_id: "p0", title: "인수 기록 정리", description: "", status: "planned", priority: "medium", due_date: null, milestone_id: null, counts_toward_progress: true, created_at: stamp, updated_at: stamp }];
let failRead = false, conflictWrite = false, loseResponse = false;
let lastRequest, failedRequest;
const replay = new Map();
await page.route("**/api/**", async (route) => {
  const request = route.request(), pathname = new URL(request.url()).pathname;
  let result = [];
  if (pathname === "/api/projects/p0/lifecycle") {
    if (request.method() === "GET") {
      if (failRead) return route.fulfill({ status: 503, json: { detail: "상태 조회 실패" } });
    } else {
      lastRequest = request.postDataJSON();
      if (conflictWrite) return route.fulfill({ status: 409, json: { detail: "다른 화면에서 상태가 변경되었습니다." } });
      if (!replay.has(lastRequest.request_id)) {
        assert.equal(lastRequest.expected_version, lifecycle.lifecycle_version);
        lifecycle = { ...lifecycle, status: lastRequest.status, service_status: lastRequest.service_status, development_ended_on: lastRequest.development_ended_on, lifecycle_version: lifecycle.lifecycle_version + 1, lifecycle_confirmed_at: stamp, history: [{ id: lastRequest.request_id, previous_status: lifecycle.status, previous_service_status: lifecycle.service_status, ...lastRequest, confirmed_at: stamp, actor_owner_id: "test-owner" }, ...lifecycle.history] };
        replay.set(lastRequest.request_id, lastRequest);
      } else assert.deepEqual(lastRequest, replay.get(lastRequest.request_id));
      if (loseResponse) { loseResponse = false; failedRequest = lastRequest; return route.fulfill({ status: 503, json: { detail: "저장 응답 유실" } }); }
    }
    result = lifecycle;
  } else if (pathname === "/api/projects") result = [project()];
  else if (pathname === "/api/projects/p0") result = project();
  else if (pathname.endsWith("/tasks")) result = tasks;
  else if (pathname.endsWith("/repository") || pathname.endsWith("/github-status")) result = null;
  return route.fulfill({ json: result });
});
const panel = () => page.getByRole("region", { name: "개발 및 운영 상태 확인" });
const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
try {
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/projects/p0`);
    await panel().getByRole("button", { name: "상태 확인·변경" }).click();
    await panel().getByLabel("서비스 상태", { exact: true }).selectOption("operating");
    await panel().getByLabel("확인·변경 사유").fill("개발이 종료되었으며 서비스 운영 중임을 본인이 확인");
    assert.equal(await panel().getByRole("button", { name: "상태 확인 저장" }).isDisabled(), true);
    await panel().getByLabel("미완료 업무 처리 사유").fill("인수 기록은 별도 업무로 유지");
    await noOverflow();
    assert.equal(await panel().getByRole("button", { name: "확인 이력" }).isDisabled(), true);
    const buttons = await panel().locator("button:visible").all();
    const boxes = await Promise.all(buttons.map((button) => button.boundingBox()));
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
    }
    await page.screenshot({ path: path.join(output, `lifecycle-${width}.png`), fullPage: true });
  }
  await page.getByRole("tab", { name: "WBS · 이슈" }).click();
  await page.getByRole("tab", { name: "현황", exact: true }).click();
  assert.equal(await panel().getByLabel("미완료 업무 처리 사유").inputValue(), "인수 기록은 별도 업무로 유지");
  loseResponse = true;
  await panel().getByRole("button", { name: "상태 확인 저장" }).click();
  await panel().getByRole("alert").filter({ hasText: "저장 응답 유실" }).waitFor();
  assert.equal(lifecycle.history.length, 1);
  assert.equal(await panel().getByLabel("서비스 상태", { exact: true }).isDisabled(), true);
  await page.getByRole("tab", { name: "WBS · 이슈" }).click();
  await page.getByRole("tab", { name: "현황", exact: true }).click();
  await panel().getByRole("button", { name: "동일 요청 다시 확인" }).click();
  await panel().getByRole("status").filter({ hasText: "확인을 기록" }).waitFor();
  assert.deepEqual(lastRequest, failedRequest);
  assert.equal(lastRequest.development_ended_on, null);
  assert.equal(lifecycle.history.length, 1);
  assert.equal(tasks[0].status, "planned");
  await panel().getByRole("button", { name: "확인 이력" }).click();
  await panel().getByRole("heading", { name: "최근 확인 1건" }).waitFor();
  await panel().getByRole("button", { name: "상태 확인·변경" }).click();
  await panel().getByLabel("개발 단계", { exact: true }).selectOption("in_progress");
  await panel().getByLabel("확인·변경 사유").fill("추가 인수 요청으로 개발 재개");
  conflictWrite = true;
  await panel().getByRole("button", { name: "상태 확인 저장" }).click();
  await panel().getByRole("alert").filter({ hasText: "다른 화면" }).waitFor();
  assert.equal(await panel().getByRole("button", { name: "상태 확인 저장" }).isDisabled(), true);
  lifecycle = { ...lifecycle, service_status: "retired", lifecycle_version: lifecycle.lifecycle_version + 1 };
  conflictWrite = false; failRead = true;
  await panel().getByRole("button", { name: "최신 상태 다시 확인" }).click();
  await panel().getByRole("alert").filter({ hasText: "상태 조회 실패" }).waitFor();
  failRead = false;
  await panel().getByRole("button", { name: "최신 상태 다시 확인" }).click();
  await panel().getByRole("alert").waitFor({ state: "hidden" });
  await panel().getByRole("status").filter({ hasText: "상태 이력 조회 중" }).waitFor({ state: "hidden" });
  assert.equal(await panel().getByLabel("확인·변경 사유").inputValue(), "추가 인수 요청으로 개발 재개");
  assert.equal(await panel().getByLabel("서비스 상태", { exact: true }).inputValue(), "retired");
  await panel().getByLabel("개발 단계", { exact: true }).selectOption("in_progress");
  await panel().getByRole("button", { name: "상태 확인 저장" }).click();
  await panel().getByRole("status").filter({ hasText: "확인을 기록" }).waitFor();
  assert.equal(lastRequest.expected_version, 2);
  assert.equal(lifecycle.status, "in_progress");
  assert.equal(lifecycle.development_ended_on, null);
  assert.equal(lifecycle.history.length, 2);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const pathname of ["/", "/projects"]) {
      await page.goto(`${base}${pathname}`);
      await page.getByText("emanual", { exact: true }).first().waitFor();
      await noOverflow();
      if (pathname === "/projects") {
        const badges = await page.locator("[class*='projectRow'] .meta-pill").all();
        const boxes = await Promise.all(badges.map((badge) => badge.boundingBox()));
        for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i], b = boxes[j];
          assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y, "Project state badges must not overlap");
        }
      }
      await page.screenshot({ path: path.join(output, `${pathname === "/" ? "dashboard" : "projects"}-${width}.png`), fullPage: true });
    }
  }
  assert.deepEqual(errors, []);
  console.log("PASS: lifecycle + dashboard/list at 4 viewports, button geometry, unknown legacy state, reason guard, tab draft retention, exact lost-response retry, history, reopen, conflict/read recovery, WBS unchanged");
} catch (error) {
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
