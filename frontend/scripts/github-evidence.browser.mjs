import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-evidence-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
const project = { id: "p0", title: "worktrace", description: "", objective: "신뢰할 수 있는 업무 이력", success_criteria: "명시적 채택", status: "in_progress", role: "개발", total_tasks: 1, completed_tasks: 0, remaining_tasks: 1, milestone_count: 0, progress_basis: "wbs", progress_percent: 0, derived_task_count: 0, updated_at: stamp };
const makeTask = (id, title) => ({ id, project_id: "p0", title, description: "", status: "planned", priority: "medium", due_date: null, milestone_id: null, counts_toward_progress: true, created_at: stamp, updated_at: stamp });
let tasks = [makeTask("t0", "기존 배포 검증 업무")];
let items = Array.from({ length: 23 }, (_, i) => ({ id: `i${i}`, number: i + 1, kind: i % 2 ? "pr" : "issue", title: i === 0 ? `긴 제목으로 정렬 검증 ${"연속문자".repeat(25)}` : `실제 근거 검토 ${i + 1}`, body: `<script>alert('not executable')</script>\n${"longbody".repeat(150)}`, url: i === 0 ? "javascript:alert(1)" : `https://github.com/example/repo/issues/${i + 1}`, external_state: "closed", source_updated_at: stamp, collected_at: stamp, review_status: "pending", version: 0, task_id: null, task_title: null, reviewed_at: null, source_changed: false }));
let failRead = false, failWrite = false, conflictWrite = false, failPlanning = false, loseResponse = false;
let lastRequest, failedRequest;
const replays = new Map();
await page.route("**/api/**", async (route) => {
  const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
  let result = [];
  if (pathname === "/api/projects/p0/github-items") {
    if (failRead) return route.fulfill({ status: 503, json: { detail: "근거 조회 실패" } });
    const filter = url.searchParams.get("review_status"), offset = Number(url.searchParams.get("offset"));
    const filtered = items.filter((item) => filter === "all" || item.review_status === filter);
    result = { items: filtered.slice(offset, offset + 20), total: filtered.length, counts: Object.fromEntries(["pending", "adopted", "ignored"].map((status) => [status, items.filter((item) => item.review_status === status).length])) };
  } else if (pathname.endsWith("/decision")) {
    lastRequest = request.postDataJSON();
    if (failWrite) { failedRequest = lastRequest; return route.fulfill({ status: 503, json: { detail: "저장 결과 확인 실패" } }); }
    if (conflictWrite) return route.fulfill({ status: 409, json: { detail: "원본이 변경되었습니다" } });
    const item = items.find((entry) => entry.id === pathname.split("/").at(-2));
    if (!replays.has(lastRequest.request_id)) {
      assert.equal(lastRequest.expected_version, item.version);
      assert.equal(lastRequest.expected_source_updated_at, item.source_updated_at);
      if (lastRequest.action === "create") {
        const task = { ...makeTask(`t${tasks.length}`, lastRequest.title), counts_toward_progress: lastRequest.counts_toward_progress };
        tasks.push(task); item.task_id = task.id; item.task_title = task.title; item.review_status = "adopted";
      } else if (lastRequest.action === "link") {
        const task = tasks.find((entry) => entry.id === lastRequest.task_id);
        item.task_id = task.id; item.task_title = task.title; item.review_status = "adopted";
      } else item.review_status = lastRequest.action === "ignore" ? "ignored" : "pending";
      item.version++; item.reviewed_at = stamp; replays.set(lastRequest.request_id, true);
    }
    result = item;
    if (loseResponse) { loseResponse = false; failedRequest = lastRequest; return route.fulfill({ status: 503, json: { detail: "응답 유실" } }); }
  } else if (pathname === "/api/projects") result = [project];
  else if (pathname === "/api/projects/p0") result = { ...project, total_tasks: tasks.filter((task) => task.counts_toward_progress).length };
  else if (pathname.endsWith("/tasks")) {
    if (failPlanning) return route.fulfill({ status: 503, json: { detail: "WBS 조회 실패" } });
    result = tasks;
  } else if (pathname.endsWith("/repository") || pathname.endsWith("/github-status")) result = null;
  return route.fulfill({ json: result });
});
const panel = () => page.locator("#panel-github");
const first = () => panel().getByRole("button", { name: /^Issue #1 / });
const filter = (name) => panel().getByRole("group", { name: "근거 검토 상태" }).getByRole("button", { name: new RegExp(`^${name}`) });
const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
try {
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/projects/p0?tab=github`);
    await first().click();
    await panel().getByText("수집된 본문", { exact: true }).click();
    await noOverflow();
    assert.equal(await panel().getByRole("link", { name: "GitHub 원본 보기" }).count(), 0);
    await page.screenshot({ path: path.join(output, `github-review-${width}.png`), fullPage: true });
    await page.screenshot({ path: path.join(output, `github-viewport-${width}.png`), fullPage: false });
    const buttons = await panel().locator("fieldset button").all();
    const boxes = await Promise.all(buttons.map((button) => button.boundingBox()));
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
    }
  }
  await panel().getByLabel("업무 제목").fill("사용자가 검토한 업무");
  await panel().getByLabel("진척도 산정에 포함").uncheck();
  await page.getByRole("tab", { name: "WBS · 이슈" }).click();
  await page.getByRole("tab", { name: "GitHub 근거" }).click();
  assert.equal(await panel().getByLabel("업무 제목").inputValue(), "사용자가 검토한 업무");
  failWrite = true;
  await panel().getByRole("button", { name: "예정 업무로 채택" }).click();
  await panel().getByRole("alert").filter({ hasText: "저장 결과 확인 실패" }).waitFor();
  assert.equal(await panel().getByLabel("업무 제목").isDisabled(), true);
  failWrite = false; failPlanning = true;
  await panel().getByRole("button", { name: "동일 요청 다시 확인" }).click();
  await panel().getByText(/저장은 완료했지만 WBS 현황/).waitFor();
  assert.deepEqual(lastRequest, failedRequest);
  assert.equal(tasks.length, 2); assert.equal(tasks[1].status, "planned"); assert.equal(tasks[1].counts_toward_progress, false);
  failPlanning = false;
  await panel().getByRole("button", { name: "현황 다시 조회" }).click();
  await panel().getByText(/저장은 완료했지만 WBS 현황/).waitFor({ state: "hidden" });
  await filter("업무 연결").click(); await first().click();
  await panel().getByRole("button", { name: "WBS 열기" }).click();
  await page.locator("#panel-tasks").waitFor();
  await page.getByRole("tab", { name: "GitHub 근거" }).click();
  await filter("검토 대기").click();
  await panel().getByRole("button", { name: /^PR #2 / }).click();
  await panel().getByLabel("기존 업무", { exact: true }).check();
  await panel().getByLabel("연결할 업무").selectOption("t0");
  conflictWrite = true;
  await panel().getByRole("button", { name: "선택 업무에 연결" }).click();
  await panel().getByRole("button", { name: "최신 원본 다시 확인" }).waitFor();
  assert.equal(await panel().getByRole("button", { name: "선택 업무에 연결" }).isDisabled(), true);
  conflictWrite = false;
  items[1].source_updated_at = "2026-09-18T01:00:00Z";
  await panel().getByRole("button", { name: "최신 원본 다시 확인" }).click();
  await panel().getByRole("button", { name: "선택 업무에 연결" }).click();
  await panel().getByRole("status").filter({ hasText: "업무에 근거" }).waitFor();
  assert.equal(lastRequest.expected_source_updated_at, items[1].source_updated_at);
  assert.equal(tasks.length, 2); assert.equal(tasks[0].status, "planned");
  await panel().getByRole("button", { name: /^Issue #3 / }).click();
  await panel().getByRole("button", { name: "검토 대상에서 제외" }).click();
  await filter("제외").click(); await panel().getByRole("button", { name: /^Issue #3 / }).click();
  await panel().getByRole("button", { name: "검토 대기로 복원" }).click();
  await panel().getByText("해당 상태의 Issue·PR이 없습니다.").waitFor();
  await filter("전체").click(); await panel().getByRole("button", { name: "다음", exact: true }).click();
  await panel().getByText("21-23 / 23").waitFor();
  failRead = true;
  await panel().getByRole("button", { name: "저장된 근거 새로고침" }).click();
  await panel().getByRole("alert").filter({ hasText: "근거 조회 실패" }).waitFor();
  failRead = false;
  await panel().getByRole("button", { name: "저장된 근거 새로고침" }).click();
  await panel().getByRole("alert").waitFor({ state: "hidden" });
  await filter("검토 대기").click();
  await panel().getByRole("button", { name: /^PR #4 / }).click();
  loseResponse = true;
  const taskCount = tasks.length;
  await panel().getByRole("button", { name: "예정 업무로 채택" }).click();
  await panel().getByRole("alert").filter({ hasText: "응답 유실" }).waitFor();
  assert.equal(tasks.length, taskCount + 1);
  await page.getByRole("tab", { name: "WBS · 이슈" }).click();
  failRead = true;
  await page.getByRole("tab", { name: "GitHub 근거" }).click();
  await panel().getByRole("alert").filter({ hasText: "근거 조회 실패" }).waitFor();
  failRead = false;
  await panel().getByRole("button", { name: "저장된 근거 새로고침" }).click();
  await panel().getByRole("button", { name: "동일 요청 다시 확인" }).click();
  await panel().getByRole("status").filter({ hasText: "업무에 근거" }).waitFor();
  assert.deepEqual(lastRequest, failedRequest);
  assert.equal(tasks.length, taskCount + 1);
  assert.deepEqual(errors, []);
  console.log("PASS: 4 viewports, overflow/button geometry, plain-text safety, draft retention, exact retry, lost response recovery, planning refresh failure, source conflict, create/link/ignore/restore, pagination, read retry");
} finally { await browser.close(); }
