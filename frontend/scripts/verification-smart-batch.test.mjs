import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("default batch review skips current AI reviews while force mode stays explicit", () => {
  assert.match(source, /async function reviewProject\(project: ProjectWithMilestones, force = false\)/);
  assert.match(source, /function needsReview/);
  assert.match(source, /if \(!force && !needsReview\(currentReview\)\)/);
  assert.match(source, /skippedCurrent \+= 1/);
  assert.match(source, /필요 항목 검토/);
  assert.match(source, /전체 강제 재검토/);
  assert.match(source, /reviewProject\(project, true\)/);
});

test("verified milestones remain excluded from AI calls even in force mode", () => {
  const batchStart = source.indexOf("async function reviewProject");
  const batchEnd = source.indexOf("async function changeValidation", batchStart);
  const batchSource = source.slice(batchStart, batchEnd);
  const doneGate = batchSource.indexOf("isConfirmedCompletion(milestoneEvidence)");
  const aiCall = batchSource.indexOf("await requestReview", doneGate);

  assert.ok(doneGate >= 0, "completion gate should exist");
  assert.ok(aiCall > doneGate, "AI call must happen only after the persisted completion gate");
});

test("completion helper ignores stale done state and legacy validation WBS", () => {
  assert.match(source, /function isConfirmedCompletion\(evidence: EvidenceSummary \| undefined\)/);
  assert.match(source, /completion\.status === "done" && !completion\.is_stale/);
  assert.doesNotMatch(source, /validation_wbs\?\.status === "done"/);
});

test("needed batch count matches smart AI review work", () => {
  assert.match(source, /neededCount = project\.milestones\.filter\(\(milestone\) => !isConfirmedCompletion\(evidence\[milestone\.id\]\) && needsReview\(reviews\[milestone\.id\]\)\)\.length/);
});
