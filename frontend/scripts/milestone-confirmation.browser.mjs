import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const { chromium } = await import(process.env.WORKTRACE_PLAYWRIGHT_PATH || "playwright");
const base = process.env.WORKTRACE_BROWSER_URL || "http://127.0.0.1:3100";
const output = process.env.WORKTRACE_BROWSER_OUTPUT || "/tmp/worktrace-confirmation-qa";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.WORKTRACE_CHROME_PATH ? { executablePath: process.env.WORKTRACE_CHROME_PATH } : {}) });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const stamp = "2026-09-18T00:00:00Z";
const project = { id: "p0", title: "worktrace", status: "in_progress", service_status: "operating", total_tasks: 1, completed_tasks: 1, remaining_tasks: 0, milestone_count: 1, progress_basis: "milestone", progress_percent: 100, derived_task_count: 0 };
const milestone = { id: "m0", project_id: "p0", title: "릴리스 수용 확인", acceptance_criteria: "로그인과 저장 흐름 직접 확인", total_tasks: 1, completed_tasks: 1, progress_percent: 100, weight: 100, derived_task_count: 0 };
let completion = { status: "planned", version: 0, context_fingerprint: "a".repeat(64), is_stale: false, can_confirm: true, block_reasons: [], history: [] };
let pending = [], conflict = false, failEvidence = false, loseResponse = false, aiCalls = 0;
const requests = new Map();
const evidence = () => ({ milestone_id: "m0", acceptance_criteria: milestone.acceptance_criteria, total_wbs: 1, completed_wbs: pending.length ? 0 : 1, pending_wbs: pending, validation_wbs: null, evidence_count: 0, recent_evidence: [], completion });
await page.route("**/api/**", async (route) => {
  const request = route.request(), pathname = new URL(request.url()).pathname;
  let result = [];
  if (pathname.endsWith("/validation")) {
    const payload = request.postDataJSON();
    if (conflict) return route.fulfill({ status: 409, json: { detail: "최신 근거를 확인하세요." } });
    if (requests.has(payload.request_id)) assert.deepEqual(payload, requests.get(payload.request_id));
    else {
      assert.equal(payload.expected_version, completion.version);
      assert.equal(payload.expected_context_fingerprint, completion.context_fingerprint);
      assert.ok(payload.reason);
      if (payload.status === "done") assert.ok(payload.evidence_note);
      requests.set(payload.request_id, payload);
      completion = { ...completion, status: payload.status, version: completion.version + 1, is_stale: false,
        history: [{ id: payload.request_id, status: payload.status, version: completion.version + 1, reason: payload.reason,
          evidence_note: payload.evidence_note, actor_owner_id: "test-owner", confirmed_at: stamp, context_fingerprint: completion.context_fingerprint }, ...completion.history] };
    }
    if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: "저장 응답 유실" } }); }
    result = evidence();
  } else if (pathname.endsWith("/evidence")) {
    if (failEvidence) return route.fulfill({ status: 503, json: { detail: "근거 조회 실패" } });
    result = evidence();
  } else if (pathname === "/api/projects") result = [project];
  else if (pathname.endsWith("/milestones")) result = [milestone];
  else if (pathname.startsWith("/api/ai/")) {
    if (request.method() === "POST") aiCalls++;
    return route.fulfill({ status: 503, json: { detail: "AI unavailable" } });
  }
  return route.fulfill({ json: result });
});
const row = () => page.locator("article").filter({ hasText: milestone.title });
const reason = () => row().getByLabel("사유", { exact: true });
const note = () => row().getByLabel("Evidence 메모", { exact: true });
const save = () => row().getByRole("button", { name: "완료 확인 저장", exact: true });
const refresh = async () => {
  const response = page.waitForResponse((res) => res.url().endsWith("/evidence"));
  await row().getByRole("button", { name: "근거 새로고침", exact: true }).last().click();
  await response;
  await page.waitForTimeout(100);
};
const openForm = async () => {
  const summary = row().locator("summary").filter({ hasText: "수동 완료 확인" });
  if (!(await summary.evaluate((element) => element.parentElement.open))) await summary.click();
};
try {
  await page.goto(`${base}/verifications`);
  await row().getByText("계획 · v0", { exact: true }).waitFor();
  await openForm();
  await reason().fill("성취 기준 수동 검토 완료");
  await note().fill("로그인·저장 시나리오 직접 수행 결과 확인");
  await save().dblclick();
  await row().getByText("완료 · v1", { exact: true }).waitFor();
  assert.equal(requests.size, 1);
  assert.equal(aiCalls, 0);
  await openForm();
  await row().locator("summary").filter({ hasText: "최근 확인 이력" }).click();
  await row().getByText(/Asia\/Seoul · test-owner/).waitFor();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const boxes = await row().getByRole("button").evaluateAll((elements) => elements.filter((el) => el.getClientRects().length).map((el) => {
      const { x, y, width, height } = el.getBoundingClientRect(); return { x, y, width, height };
    }));
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      assert.ok(a.x + a.width <= b.x + 1 || b.x + b.width <= a.x + 1 || a.y + a.height <= b.y + 1 || b.y + b.height <= a.y + 1, "buttons overlap");
    }
    await page.screenshot({ path: path.join(output, `confirmation-${width}.png`), fullPage: true });
  }
  completion = { ...completion, context_fingerprint: "b".repeat(64), is_stale: true };
  await refresh();
  await row().getByText("완료 · v1 · 재확인 필요", { exact: true }).waitFor();
  await reason().fill("새 기준 검토 초안");
  await note().fill("변경 근거 메모");
  conflict = true;
  await save().click();
  await row().getByRole("alert").waitFor();
  assert.equal(await save().isDisabled(), true);
  failEvidence = true;
  await refresh();
  assert.equal(await save().isDisabled(), true);
  assert.equal(await reason().inputValue(), "새 기준 검토 초안");
  failEvidence = false; conflict = false;
  await refresh();
  assert.equal(await reason().inputValue(), "새 기준 검토 초안");
  assert.equal(await row().getByRole("alert").count(), 0);
  await openForm();
  loseResponse = true;
  await save().click();
  const retry = row().getByRole("button", { name: "같은 완료 확인 다시 시도", exact: true });
  await retry.waitFor();
  assert.equal(await reason().isDisabled(), true);
  assert.equal(await note().isDisabled(), true);
  const savedCount = requests.size;
  await row().getByRole("button", { name: "AI 검토", exact: true }).click();
  await row().getByRole("alert").filter({ hasText: "AI" }).waitFor();
  assert.equal(await reason().isDisabled(), true);
  assert.equal(await note().isDisabled(), true);
  assert.equal(await retry.isDisabled(), false);
  await retry.click();
  await retry.waitFor({ state: "hidden" });
  await row().getByText("완료 · v2", { exact: true }).waitFor();
  assert.equal(requests.size, savedCount);
  await openForm();
  await reason().fill("추가 확인을 위해 재개");
  await row().getByRole("button", { name: "다시 계획으로 열기", exact: true }).click();
  await row().getByText("계획 · v3", { exact: true }).waitFor();
  pending = [{ id: "t0", title: "미완료 업무", status: "planned", priority: "medium" }];
  completion = { ...completion, can_confirm: false, block_reasons: ["미완료 계획 WBS가 있습니다."] };
  await refresh();
  await openForm();
  await reason().fill("차단 확인"); await note().fill("차단 테스트");
  assert.equal(await save().isDisabled(), true);
  assert.equal(completion.history.length, 3);
  assert.equal(aiCalls, 1);
  assert.deepEqual(errors, []);
  console.log("PASS: manual confirmation without AI; 4 responsive widths, history, stale context, conflict/read-failure draft retention, exact lost-response retry, reopen, pending-WBS gate");
} catch (error) {
  console.error(await row().locator("textarea").evaluateAll((elements) => elements.map((el) => ({ html: el.outerHTML, label: el.parentElement.outerHTML }))));
  console.error(await page.locator("body").innerText());
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
