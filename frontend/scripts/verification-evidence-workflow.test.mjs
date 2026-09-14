import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/verifications/page.module.css", import.meta.url), "utf8");

test("completion review restores actual evidence and validation state before AI actions", () => {
  assert.match(source, /<h1>완료 검토<\/h1>/);
  assert.match(source, /selectedProjectId/);
  assert.match(source, /defaultProjectId/);
  assert.match(source, /project\.status !== "done"/);
  assert.match(source, /project\.status === "done" \? `\[완료\] \$\{project\.title\}`/);
  assert.match(source, /loadEvidenceForProject/);
  assert.match(source, /\/api\/projects\/\$\{project\.id\}\/milestones\/\$\{milestone\.id\}\/evidence/);
  assert.match(source, /validationStateLabel/);
  assert.match(source, /확인 완료/);
  assert.match(source, /확인 대기/);
  assert.match(source, /검토 필요/);
  assert.match(source, /근거 다시 불러오기/);
});

test("evidence view exposes criteria pending WBS and safe recent links without confidence percentages", () => {
  assert.match(source, /pending_wbs/);
  assert.match(source, /recent_evidence/);
  assert.match(source, /milestoneProgressDisplay/);
  assert.doesNotMatch(source, /derived_task_count[\s\S]*?\?\? 0/);
  assert.match(source, /isSafeEvidenceUrl/);
  assert.match(source, /parsed\.protocol === "http:" \|\| parsed\.protocol === "https:"/);
  assert.match(source, /formatDate\(item\.occurred_at\)/);
  assert.doesNotMatch(source, /신뢰도 \{Math\.round\(reviewResult\.confidence \* 100\)\}%/);
  assert.doesNotMatch(source, /confidence \* 100/);
});

test("mutation controls lock during work and forced review is explicit advanced action", () => {
  assert.match(source, /const controlsLocked = Boolean/);
  assert.match(source, /<fieldset className=\{styles\.lockableArea\} disabled=\{controlsLocked\}>/);
  assert.match(source, /<summary>고급<\/summary>/);
  assert.match(source, /전체 강제 재검토/);
  assert.match(source, /reviewProject\(project, true\)/);
});

test("scoped CSS covers compact responsive verification layout", () => {
  assert.match(css, /\.summaryGrid/);
  assert.match(css, /\.milestoneRow/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /@media \(max-width: 360px\)/);
});
