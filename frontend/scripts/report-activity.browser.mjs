import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { readFile } from "node:fs/promises";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-report-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
let posts = 0, holdNext = false, failNext = false, legacy = false, held;
let failList = false, failDetail = false, holdDetail = false, heldDetail, loseDeleteResponse = false;
const snapshots = new Map();
const requestIds = [];
function responseFor(request, number) {
  return {
    ...request, markdown: `# 기록 ${request.end_date} / 요청 ${number}`, work_logs: [], projects: [], remaining_tasks: [], delayed_tasks: [], monthly_performance_candidates: [],
    progress_candidates: [{ project_id: "p0", project_title: "worktrace", provenance: "계획 재승인 필요", as_of: stamp, reason: "현재 승인 범위 변경" }],
    ...(legacy ? {} : { activity: {
      schema_version: "1", as_of: stamp, timezone: "Asia/Seoul", start_at: "2026-09-14T00:00:00+09:00", end_exclusive: "2026-09-19T00:00:00+09:00", fingerprint: "abc12345".repeat(8),
      transitions: Array.from({ length: 12 }, (_, index) => ({ id: `event-${index}`, project_id: "p0", project_title: "worktrace", task_id: `task-${index}`, task_title: index === 0 ? "<img src=x onerror=alert(1)> 사용자 원문" : `상태 변경 업무 ${index}`, previous_status: "planned", next_status: "done", current_status: "in_progress", source: "user", reason: "인수 검토 완료 후 후속 작업 재개", changed_at: stamp, status_version: 2 })),
      current_tasks: ["approved", "unapproved", "stale"].map((status, index) => ({ id: `current-${index}`, project_id: "p0", project_title: "worktrace", title: index === 0 ? "긴업무제목".repeat(24) : `현재 업무 ${index}`, status: "in_progress", due_date: "2026-09-20", source_provider: null, progress_plan_status: status, progress_plan_version: 2 })),
      issues: [{ id: "log-0", project_id: null, project_title: "", title: "권한 요청 기록", blockers: "외부 권한 대기", log_date: "2026-09-18", updated_at: stamp }],
      outcomes: [{ id: "outcome-0", project_id: "p0", project_title: "worktrace", title: "확인한 정량 성과", outcome_type: "quantitative", before_state: "이전", after_state: "이후", metric_name: "오류", metric_value: "0", metric_unit: "건", updated_at: stamp, evidence_work_log_ids: ["evidence-0"], evidence_document_ids: [] }],
    } }),
  };
}
await page.route("**/api/reports/snapshots**", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const id = url.pathname.split("/")[4];
  if (request.method() === "DELETE") {
    const exists = snapshots.has(id);
    snapshots.delete(id);
    if (loseDeleteResponse) { loseDeleteResponse = false; return route.fulfill({ status: 503, json: { detail: "삭제 응답 유실" } }); }
    if (!exists) return route.fulfill({ status: 404, json: { detail: "보관본 없음" } });
    return route.fulfill({ status: 204 });
  }
  if (request.method() === "GET" && id) {
    const json = snapshots.get(id);
    if (!json) return route.fulfill({ status: 404, json: { detail: "보관본 없음" } });
    if (failDetail) { failDetail = false; return route.fulfill({ status: 503, json: { detail: "보관본 조회 실패" } }); }
    if (holdDetail) {
      holdDetail = false;
      await new Promise((resolve) => { heldDetail = async () => { await route.fulfill({ json }); resolve(); }; });
      return;
    }
    return route.fulfill({ json });
  }
  if (request.method() === "GET") {
    if (failList) { failList = false; return route.fulfill({ status: 503, json: { detail: "보관함 조회 실패" } }); }
    const limit = Number(url.searchParams.get("limit") || 20), offset = Number(url.searchParams.get("offset") || 0);
    const all = [...snapshots.values()].reverse();
    const items = all.slice(offset, offset + limit).map(({ report, ...metadata }) => metadata);
    return route.fulfill({ json: { items, total: all.length, limit, offset } });
  }
  const number = ++posts;
  const body = request.postDataJSON();
  requestIds.push(body.request_id);
  let json = [...snapshots.values()].find((row) => row.request_id === body.request_id);
  if (!json) {
    json = { ...body, id: `snapshot-${number}`, as_of: stamp, created_at: "2026-09-18T00:01:00Z", fingerprint: "abc12345".repeat(8), schema_version: "1", report: responseFor(body, number) };
    snapshots.set(json.id, json);
  }
  if (holdNext) {
    holdNext = false;
    await new Promise((resolve) => { held = async () => { await route.fulfill({ json }); resolve(); }; });
    return;
  }
  if (failNext) { failNext = false; return route.fulfill({ status: 503, json: { detail: "리포트 조회 실패" } }); }
  await new Promise((resolve) => setTimeout(resolve, 80));
  return route.fulfill({ json });
});
const generate = () => page.getByRole("button", { name: "생성·보관", exact: true });
const result = () => page.locator(".markdown-output");
const waitResult = async (text) => { await page.waitForFunction((expected) => document.querySelector(".markdown-output")?.textContent === expected, text); };
const end = () => page.getByLabel("종료일", { exact: true });
try {
  await page.goto(`${base}/reports`);
  await page.getByLabel("시작일", { exact: true }).fill("2026-09-14");
  await end().fill("2026-09-18");
  await generate().dblclick();
  await waitResult("# 기록 2026-09-18 / 요청 1");
  assert.equal(posts, 1);
  const activity = page.getByRole("region", { name: "기간 실제 활동 기록", exact: true });
  await activity.waitFor();
  assert.equal(await activity.locator("img").count(), 0);
  await activity.getByText("상태 변경 업무 11", { exact: true }).scrollIntoViewIfNeeded();
  await activity.getByText("보관 당시 진행", { exact: true }).first().waitFor();
  assert.deepEqual(await page.getByRole("region", { name: "리포트 지표", exact: true }).locator("strong").allTextContents(), ["12", "1", "3", "1"]);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => scrollTo(0, 0));
    await activity.evaluate((element) => element.querySelectorAll("div").forEach((row) => { if (row.scrollHeight > row.clientHeight) row.scrollTop = 0; }));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `page overflow ${width}`);
    const controls = await page.locator(".report-controls input,.report-controls select,.report-controls button").evaluateAll((elements) => elements.map((element) => {
      const { x, y, width, height } = element.getBoundingClientRect(); return { x, y, width, height };
    }));
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i], b = controls[j];
      assert.ok(a.x + a.width <= b.x + 1 || b.x + b.width <= a.x + 1 || a.y + a.height <= b.y + 1 || b.y + b.height <= a.y + 1, "filter controls overlap");
    }
    await page.screenshot({ path: path.join(output, `report-${width}.png`), fullPage: true });
  }
  await page.getByRole("button", { name: "Markdown 복사" }).click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "# 기록 2026-09-18 / 요청 1");

  holdNext = true;
  await end().fill("2026-09-17");
  await generate().click();
  await page.waitForTimeout(100);
  assert.ok(held);
  await end().fill("2026-09-18");
  await generate().click();
  await waitResult("# 기록 2026-09-18 / 요청 3");
  await held(); held = null;
  await page.waitForTimeout(100);
  assert.equal(await result().innerText(), "# 기록 2026-09-18 / 요청 3");

  holdNext = true;
  await end().fill("2026-09-16");
  await generate().click();
  await page.waitForTimeout(100);
  await end().fill("2026-09-15");
  await end().fill("2026-09-16");
  await generate().click();
  await waitResult("# 기록 2026-09-16 / 요청 4");
  assert.equal(requestIds[3], requestIds[4], "uncertain A request keeps its key after A/B/A");
  await held(); held = null;
  await page.waitForTimeout(100);
  assert.equal(await result().innerText(), "# 기록 2026-09-16 / 요청 4");

  failNext = true;
  await generate().click();
  await page.getByRole("alert").waitFor();
  assert.equal(await result().count(), 0);
  await generate().click();
  await waitResult("# 기록 2026-09-16 / 요청 6");
  assert.equal(requestIds[5], requestIds[6], "lost response retry must not create another saved version");
  legacy = true;
  await generate().click();
  await waitResult("# 기록 2026-09-16 / 요청 8");
  assert.deepEqual(await page.getByRole("region", { name: "리포트 지표", exact: true }).locator("strong").allTextContents(), Array(4).fill("기준 미확인"));
  const downloadPending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Markdown 다운로드", exact: true }).click();
  const download = await downloadPending;
  assert.equal(await readFile(await download.path(), "utf8"), "# 기록 2026-09-16 / 요청 8");
  assert.ok(download.suggestedFilename().endsWith(".md"));

  legacy = false;
  snapshots.clear();
  for (let index = 0; index < 22; index++) {
    const body = { report_type: "weekly", start_date: "2026-09-14", end_date: "2026-09-18" };
    const report = responseFor(body, index);
    report.markdown = `# archive ${index}\n\n저장된 원문`;
    snapshots.set(`archive-${index}`, { ...body, id: `archive-${index}`, request_id: `request-${index}`, as_of: stamp, created_at: "2026-09-18T00:01:00Z", fingerprint: "abc12345".repeat(8), schema_version: "1", report });
  }
  const archiveTab = () => page.getByRole("navigation", { name: "리포트 보기" }).getByText("보관함", { exact: true });
  const newTab = () => page.getByRole("navigation", { name: "리포트 보기" }).getByText("새 리포트", { exact: true });
  const archiveRegion = () => page.getByRole("region", { name: "보관 리포트 목록", exact: true });
  const rows = () => archiveRegion().getByRole("list").getByRole("button");
  failList = true;
  await archiveTab().click();
  await page.getByRole("alert").filter({ hasText: "보관함 조회 실패" }).waitFor();
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await rows().first().waitFor();
  assert.equal(await rows().count(), 20);
  await rows().first().click();
  await waitResult("# archive 21\n\n저장된 원문");
  await page.getByRole("button", { name: "Markdown 복사", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "복사했습니다" }).waitFor();
  const postsBeforeArchive = posts;
  holdDetail = true;
  await rows().nth(1).click();
  await page.waitForTimeout(100);
  await rows().nth(2).click();
  await waitResult("# archive 19\n\n저장된 원문");
  assert.equal(await page.getByRole("status").filter({ hasText: "복사했습니다" }).count(), 0, "copy feedback belongs to the previously selected snapshot");
  await heldDetail(); heldDetail = null;
  await page.waitForTimeout(100);
  assert.equal(await result().innerText(), "# archive 19\n\n저장된 원문");
  failDetail = true;
  await rows().nth(3).click();
  await page.getByRole("alert").filter({ hasText: "보관본 조회 실패" }).waitFor();
  assert.equal(await result().count(), 0, "failed selection must not relabel older detail");
  await rows().nth(3).click();
  await waitResult("# archive 18\n\n저장된 원문");
  assert.equal(posts, postsBeforeArchive, "opening saved content must not generate new reports");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => scrollTo(0, 0));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `archive overflow ${width}`);
    await page.screenshot({ path: path.join(output, `archive-${width}.png`), fullPage: true });
  }

  const remove = () => page.getByRole("button", { name: "보관 리포트 삭제", exact: true });
  page.once("dialog", (dialog) => dialog.dismiss());
  await remove().click();
  assert.equal(snapshots.size, 22);
  loseDeleteResponse = true;
  page.once("dialog", (dialog) => dialog.accept());
  await remove().click();
  await page.getByRole("alert").filter({ hasText: "삭제 응답 유실" }).waitFor();
  page.once("dialog", (dialog) => dialog.accept());
  await remove().click();
  await page.waitForFunction(() => !document.querySelector(".markdown-output"));
  assert.equal(snapshots.size, 21);
  await page.getByRole("button", { name: "다음", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('[aria-label="보관 리포트 목록"] [role="list"] button').length === 1);
  await rows().first().click();
  await waitResult("# archive 0\n\n저장된 원문");
  page.once("dialog", (dialog) => dialog.accept());
  await remove().click();
  await page.waitForFunction(() => document.querySelectorAll('[aria-label="보관 리포트 목록"] [role="list"] button').length === 20);
  assert.equal(await page.getByRole("button", { name: "이전", exact: true }).isDisabled(), true);

  await newTab().click();
  holdNext = true;
  await generate().click();
  await page.waitForTimeout(100);
  await archiveTab().click();
  await rows().filter({ hasText: "2026-09-14 ~ 2026-09-18" }).first().click();
  await waitResult("# archive 21\n\n저장된 원문");
  await held(); held = null;
  await page.waitForTimeout(100);
  await archiveRegion().waitFor();
  assert.equal(await result().innerText(), "# archive 21\n\n저장된 원문", "late generation cannot replace selected archive or switch tabs");
  assert.deepEqual(errors, []);
  console.log("PASS: report/archive at 4 widths, exact copy/download, idempotent retry, stale generation/detail suppression, list/detail recovery, delete cancellation and lost-response recovery, last-page deletion");
} catch (error) {
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
