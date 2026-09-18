import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

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
await page.route("**/api/reports/automatic", async (route) => {
  const number = ++posts;
  const body = route.request().postDataJSON();
  const json = responseFor(body, number);
  if (holdNext) {
    holdNext = false;
    await new Promise((resolve) => { held = async () => { await route.fulfill({ json }); resolve(); }; });
    return;
  }
  if (failNext) { failNext = false; return route.fulfill({ status: 503, json: { detail: "리포트 조회 실패" } }); }
  await new Promise((resolve) => setTimeout(resolve, 80));
  return route.fulfill({ json });
});
const generate = () => page.getByRole("button", { name: "리포트 생성", exact: true });
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
  await activity.getByText("현재 진행", { exact: true }).first().waitFor();
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
  await waitResult("# 기록 2026-09-16 / 요청 5");
  await held(); held = null;
  await page.waitForTimeout(100);
  assert.equal(await result().innerText(), "# 기록 2026-09-16 / 요청 5");

  failNext = true;
  await generate().click();
  await page.getByRole("alert").waitFor();
  assert.equal(await result().count(), 0);
  await generate().click();
  await waitResult("# 기록 2026-09-16 / 요청 7");
  legacy = true;
  await generate().click();
  await waitResult("# 기록 2026-09-16 / 요청 8");
  assert.deepEqual(await page.getByRole("region", { name: "리포트 지표", exact: true }).locator("strong").allTextContents(), Array(4).fill("기준 미확인"));
  assert.deepEqual(errors, []);
  console.log("PASS: report records and counts, 4 widths, raw-text safety, exact Markdown copy, stale response suppression, A/B/A request recovery, failed regeneration and legacy unknown metrics");
} catch (error) {
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
