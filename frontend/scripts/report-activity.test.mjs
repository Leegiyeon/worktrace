import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const reportsPage = read("app/reports/page.tsx");
const reportActivity = read("app/reports/ReportActivity.tsx");
const reportActivityCss = read("app/reports/ReportActivity.module.css");
const reportTypes = read("app/reports/types.ts");

test("automatic reports accept optional activity payload with provenance fields", () => {
  for (const field of ["schema_version", "as_of", "timezone", "start_at", "end_exclusive", "fingerprint"]) {
    assert.match(reportTypes, new RegExp(`${field}:`));
    assert.match(reportActivity, new RegExp(`activity\\.${field}`));
  }
  for (const collection of ["transitions", "current_tasks", "issues", "outcomes"]) {
    assert.match(reportTypes, new RegExp(`${collection}:`));
    assert.match(reportActivity, new RegExp(`activity\\.${collection}`));
  }
  assert.match(reportTypes, /activity\?: ReportActivity/);
  assert.match(reportActivity, /title=\{activity\.fingerprint\}/);
  assert.match(reportActivity, /내용해시 <code>\{shortId\(activity\.fingerprint\)\}<\/code>/);
  assert.match(reportActivity, /<code>\{activity\.fingerprint\}<\/code>/);
  assert.match(reportActivity, /스키마 \{activity\.schema_version\}/);
});

test("report activity labels use actual period records without inferred completion wording", () => {
  for (const label of ["기간 내 상태 변경", "기록된 막힘", "기간 내 수정된 확인 성과", "현재 잔여 WBS"]) {
    assert.match(reportActivity, new RegExp(label));
    assert.match(reportsPage, new RegExp(label));
  }
  assert.doesNotMatch(reportActivity, /고유 완료|해결됨|완료 추정|period.?end|기간 종료/i);
  assert.match(reportActivity, /planStatusLabels/);
  assert.match(reportActivity, /unapproved: "계획 미승인"/);
  assert.match(reportActivity, /수정 \{formatDateTime\(outcome\.updated_at, timezone\)\}/);
  assert.match(reportActivity, /현재 \{taskStatusLabel\(item\.current_status\)\}/);
  assert.doesNotMatch(reportActivity, /현재 진행 \{taskStatusLabel\(item\.current_status\)\}/);
  assert.match(reportActivity, /milestone_validation: "과거 자동 검증"/);
  assert.match(reportActivity, /종료 미포함/);
});

test("report activity links records to existing project tabs only when project id exists and uses Korean evidence refs", () => {
  assert.match(reportActivity, /\/projects\/\$\{projectId\}\?tab=\$\{tab\}/);
  assert.match(reportActivity, /if \(!projectId\) return null/);
  assert.doesNotMatch(reportActivity, /: "\/projects"/);
  assert.match(reportActivity, /tab="tasks"/);
  assert.match(reportActivity, /tab="logs"/);
  assert.match(reportActivity, /tab="outcomes"/);
  assert.match(reportActivity, /<EvidenceRef label="상태근거" value=\{item\.id\} \/>/);
  assert.match(reportActivity, /<EvidenceRef label="업무로그" value=\{issue\.id\} \/>/);
  assert.match(reportActivity, /<EvidenceRefList label="로그근거" values=\{outcome\.evidence_work_log_ids\} \/>/);
  assert.match(reportActivity, /<EvidenceRefList label="문서근거" values=\{outcome\.evidence_document_ids\} \/>/);
  assert.doesNotMatch(reportActivity, />status |task \{|worklog |logs \{|docs \{/);
  assert.match(reportActivity, /function EvidenceRef/);
  assert.match(reportActivity, /title=\{value\}/);
  assert.match(reportActivity, /function EvidenceRefList/);
  assert.match(reportActivity, /title=\{values\.join\(", "\)\}/);
});

test("report activity localizes raw status and hides leftover metrics for qualitative outcomes", () => {
  assert.match(reportActivity, /import \{ outcomeTypeLabels, taskStatusLabels \}/);
  assert.match(reportActivity, /taskStatusLabel\(task\.status\)/);
  assert.match(reportActivity, /taskStatusLabel\(item\.next_status\)/);
  assert.match(reportActivity, /outcomeTypeLabel\(outcome\.outcome_type\)/);
  assert.match(reportActivity, /isQuantitativeOutcome\(outcome\) \? <span className="meta-pill">/);
  assert.doesNotMatch(reportActivity, /\{outcome\.outcome_type\}<\/span>/);
});

test("report lists are bounded by scroll containers instead of silently slicing rows", () => {
  assert.doesNotMatch(reportsPage, /\.slice\(0,\s*(?:6|8|10)\)/);
  assert.doesNotMatch(reportActivity, /\.slice\(0,/);
  assert.match(reportActivityCss, /max-height:\s*360px/);
  assert.match(reportActivityCss, /overflow:\s*auto/);
  assert.match(reportActivityCss, /\.activityPanel\s*\{/);
  assert.match(reportActivityCss, /\.record\s*\{[\s\S]*?border-top:\s*1px solid var\(--border\)/);
  assert.doesNotMatch(reportActivityCss, /\.record\s*\{[\s\S]*?border:\s*1px solid var\(--border\)/);
  assert.doesNotMatch(reportActivityCss, /\.record\s*\{[\s\S]*?background:\s*var\(--surface\)/);
});

test("report generation invalidates stale responses and allows a newer filter request", () => {
  assert.match(reportsPage, /latestRequestRef/);
  assert.match(reportsPage, /busyRequestRef/);
  assert.match(reportsPage, /busyRequestRef\.current\?\.filterKey === requestFilterKey && busyRequestRef\.current\.sequence === latestRequestRef\.current\.sequence/);
  assert.match(reportsPage, /latestRequestRef\.current = \{ sequence: latestRequestRef\.current\.sequence \+ 1, filterKey: reportFilterKey\(\) \}/);
  assert.match(reportsPage, /setReport\(null\)/);
  assert.match(reportsPage, /loadingFilterKey === currentFilterKey/);
  assert.match(reportsPage, /latestRequestRef\.current\.sequence !== requestSequence \|\| latestRequestRef\.current\.filterKey !== requestFilterKey/);
});

test("legacy responses without activity show unknown metrics instead of zero counts", () => {
  assert.match(reportsPage, /if \(!report\.activity\) return \{ transitions: "기준 미확인", issues: "기준 미확인", currentTasks: "기준 미확인", outcomes: "기준 미확인" \}/);
  assert.doesNotMatch(reportsPage, /report\.activity\?\.transitions\.length \?\? 0/);
});

test("markdown copy and current WBS progress surfaces remain available", () => {
  assert.match(reportsPage, /Markdown 복사/);
  assert.match(reportsPage, /report\.markdown/);
  assert.match(reportsPage, /현재 WBS 진척/);
  assert.match(reportsPage, /report\.progress_candidates/);
});
