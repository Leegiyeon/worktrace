import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const page = read("app/page.tsx");
const css = read("app/page.module.css");

test("textual metric values use compact type instead of numeric display size", () => {
  assert.match(read("app/insights/page.tsx"), /className="metric-text"/);
  assert.match(read("app/ui-overflow-fixes.css"), /\.metric-text \{ font-size: var\(--text-md\); word-break: keep-all/);
});

test("dashboard has one issue queue including overdue work", () => {
  assert.doesNotMatch(page, /className="panel delayed-panel"/);
  assert.match(page, /managementIssueLabel\(task\) === issueFilter/);
  assert.match(page, /aria-label="이슈 유형"/);
  assert.match(page, /tab=tasks&view=list/);
  assert.match(page, /tab=logs/);
  assert.doesNotMatch(page, /projects\.slice\(0, 5\)/);
});

test("dashboard issue titles wrap in a bounded single-column list", () => {
  assert.match(css, /attention-queue\) \{ grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /attention-row small\) \{ white-space: normal/);
  assert.match(css, /max-height: 300px/);
});

test("mobile navigation exposes every route without horizontal discovery", () => {
  const header = read("app/components/AppHeader.tsx");
  const shared = read("app/ui-overflow-fixes.css");
  assert.match(header, /aria-label="화면 이동"/);
  for (const route of ["/", "/projects", "/goals", "/verifications", "/branches", "/insights", "/reports"]) assert.ok(header.includes(`value="${route}"`));
  assert.match(shared, /app-header-actions \.app-nav \{ display: none/);
  assert.match(shared, /summary-grid\.dashboard-metrics \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
});
