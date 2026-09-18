import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-task-history-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
let task = { id: "t0", project_id: "p0", title: "인수 기록 정리", description: "", status: "planned", priority: "medium", due_date: null, milestone_id: null, counts_toward_progress: true, source_provider: null, status_version: 1, completed_at: null, created_at: stamp, updated_at: stamp };
const project = { id: "p0", title: "worktrace", description: "", role: "개발", status: "in_progress", service_status: "operating", total_tasks: 1, completed_tasks: 0, remaining_tasks: 1, milestone_count: 0, progress_basis: "wbs", progress_percent: 0, derived_task_count: 0, updated_at: stamp };
let history = [];
let conflict = false, failHistory = false, loseResponse = false;
let lastRequest;
await page.route("**/api/**", async (route) => {
  const request = route.request(), pathname = new URL(request.url()).pathname;
  let result = [];
  if (pathname.endsWith("/tasks/t0/history")) {
    if (failHistory) return route.fulfill({ status: 503, json: { detail: "이력 조회 실패" } });
    result = { items: history, total: history.length };
  } else if (pathname.endsWith("/tasks/t0")) {
    lastRequest = request.postDataJSON();
    if (conflict) return route.fulfill({ status: 409, json: { detail: "다른 화면에서 상태가 변경되었습니다." } });
    assert.equal(lastRequest.expected_status_version, task.status_version);
    const changed = task.status !== lastRequest.status;
    const next = { ...task, ...lastRequest, status_version: task.status_version + Number(changed), completed_at: changed ? (lastRequest.status === "done" ? stamp : null) : task.completed_at };
    if (changed) history.unshift({ id: String(next.status_version), previous_status: task.status, status: next.status, source: "user", actor_owner_id: "test-owner", reason: lastRequest.status_reason || null, changed_at: stamp, status_version: next.status_version });
    task = next;
    if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: "저장 응답 유실" } }); }
    result = task;
  } else if (pathname === "/api/projects") result = [project];
  else if (pathname === "/api/projects/p0") result = project;
  else if (pathname.endsWith("/tasks")) result = [task];
  else if (pathname.endsWith("/lifecycle")) result = { ...project, lifecycle_version: 0, pending_task_count: 1, history: [] };
  else if (pathname.endsWith("/repository") || pathname.endsWith("/github-status")) result = null;
  else if (pathname === "/api/reports/snapshots" && request.method() === "GET") result = { items: [], total: 0, limit: 20, offset: 0 };
  else if (pathname === "/api/reports/snapshots") result = {
    id: "snapshot-0", request_id: request.postDataJSON().request_id, report_type: "weekly",
    start_date: "2026-09-14", end_date: "2026-09-18", as_of: stamp, created_at: stamp, fingerprint: "a".repeat(64), schema_version: "1",
    report: {
    report_type: "weekly", start_date: "2026-09-14", end_date: "2026-09-18", markdown: "# Current WBS", work_logs: [], projects: [], remaining_tasks: [], delayed_tasks: [], monthly_performance_candidates: [],
    progress_candidates: ["산정 전", "0%", "참고 63%", "기준 미확인"].map((label, index) => ({ project_id: String(index), project_title: `프로젝트 ${index + 1}`, provenance: label, as_of: stamp, reason: "현재 등록 WBS 기준" })),
    },
  };
  return route.fulfill({ json: result });
});
const form = () => page.locator(".task-form-panel");
const openEditor = async () => { await page.getByRole("button", { name: task.title, exact: true }).click(); };
const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
try {
  await page.goto(`${base}/projects/p0?tab=tasks&view=list`);
  await openEditor();
  await form().getByLabel("업무 상태", { exact: true }).selectOption("done");
  await form().getByLabel("상태 변경 사유 (선택)").fill("인수 내용 확인 완료");
  await form().getByRole("button", { name: "수정 저장" }).click();
  await form().waitFor({ state: "hidden" });
  assert.equal(task.status, "done");
  assert.equal(lastRequest.expected_status_version, 1);
  await openEditor();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await form().locator("details").evaluate((element) => { element.open = true; });
    await form().getByText("인수 내용 확인 완료", { exact: true }).waitFor();
    await noOverflow();
    await page.screenshot({ path: path.join(output, `task-history-${width}.png`), fullPage: true });
  }
  await form().getByLabel("항목명", { exact: true }).fill("초안 보존 확인");
  await form().getByLabel("업무 상태", { exact: true }).selectOption("in_progress");
  conflict = true;
  await form().getByRole("button", { name: "수정 저장" }).click();
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).waitFor();
  assert.equal(await form().getByRole("button", { name: "수정 저장" }).isDisabled(), true);
  task = { ...task, status: "on_hold", completed_at: null, status_version: 3 };
  conflict = false;
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).click();
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).waitFor({ state: "hidden" });
  assert.equal(await form().getByLabel("항목명", { exact: true }).inputValue(), "초안 보존 확인");
  assert.equal(await form().getByLabel("업무 상태", { exact: true }).inputValue(), "on_hold");
  await form().getByLabel("업무 상태", { exact: true }).selectOption("in_progress");
  loseResponse = true;
  await form().getByRole("button", { name: "수정 저장" }).click();
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).waitFor();
  assert.equal(task.status, "in_progress");
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).click();
  await page.getByRole("button", { name: "최신 업무 상태 확인" }).waitFor({ state: "hidden" });
  assert.equal(await form().getByLabel("업무 상태", { exact: true }).inputValue(), "in_progress");
  const totalBeforeRetry = history.length;
  await form().getByRole("button", { name: "수정 저장" }).click();
  await form().waitFor({ state: "hidden" });
  assert.equal(history.length, totalBeforeRetry);
  await openEditor();
  failHistory = true;
  await form().locator("summary").click();
  await form().getByRole("alert").waitFor();
  failHistory = false;
  await form().getByRole("button", { name: "이력 다시 조회" }).click();
  await form().getByRole("alert").waitFor({ state: "hidden" });
  await form().getByRole("button", { name: "편집 취소" }).click();
  await page.getByLabel(`${task.title} 상태 변경`).selectOption("done");
  await page.getByRole("status").filter({ hasText: "업무 상태 변경 완료" }).waitFor();
  assert.equal(lastRequest.expected_status_version, 4);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/reports`);
    await page.getByRole("button", { name: "생성·보관", exact: true }).click();
    await page.getByRole("heading", { name: "보관 당시 WBS 진척" }).waitFor();
    for (const label of ["산정 전", "0%", "참고 63%", "기준 미확인"]) await page.locator(".status-graph-panel").getByText(label, { exact: true }).waitFor();
    await noOverflow();
    await page.screenshot({ path: path.join(output, `report-${width}.png`), fullPage: true });
  }
  assert.deepEqual(errors, []);
  console.log("PASS: task history + report at 4 widths; versioned save, conflict draft retention, lost-response recovery, same-status retry, history failure retry, quick status change");
} catch (error) {
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
