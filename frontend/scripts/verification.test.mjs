import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("verification center supports project-wide AI review without auto-completing milestones", () => {
  assert.match(source, /async function reviewProject\(project: ProjectWithMilestones, force = false\)/);
  assert.match(source, /필요 항목 검토/);
  assert.match(source, /전체 강제 재검토/);
  assert.match(source, /isConfirmedCompletion\(milestoneEvidence\)/);
  assert.match(source, /await requestReview\(project\.id, milestone\.id\)/);
  assert.match(source, /reviewed \+= 1/);
  assert.match(source, /failed \+= 1/);

  const batchStart = source.indexOf("async function reviewProject");
  const batchEnd = source.indexOf("async function changeValidation", batchStart);
  const batchSource = source.slice(batchStart, batchEnd);
  assert.doesNotMatch(batchSource, /method:\s*"PATCH"/);
  assert.doesNotMatch(batchSource, /changeValidation\(/);
});

test("batch review keeps explicit user confirmation as the only completion path", () => {
  assert.match(source, /type CompletionState/);
  assert.match(source, /completion\.status === "done" && !completion\.is_stale/);
  assert.match(source, /수동 완료 확인/);
  assert.match(source, /Evidence 메모/);
  assert.match(source, /검증 완료 유지/);
  assert.match(source, /일부 마일스톤 \$\{failed\}건은 검토하지 못했습니다/);
});

test("manual confirmation sends optimistic completion contract without requiring AI", () => {
  assert.match(source, /expected_version: completion\.version/);
  assert.match(source, /expected_context_fingerprint: completion\.context_fingerprint/);
  assert.match(source, /request_id: draft\.request_id/);
  assert.match(source, /reason,/);
  assert.match(source, /evidence_note: status === "done" \? evidenceNote : ""/);
  assert.match(source, /status === "done" && !evidenceNote/);
  assert.match(source, /!completion\.can_confirm/);
  assert.match(source, /\(currentConfirmed && !doneRetryPending\) \|\| \(!pendingRequest && \(!completion\.can_confirm/);
  assert.match(source, /Boolean\(pendingRequest\) && !doneRetryPending/);
  assert.doesNotMatch(source, /reviewResult\?\.verdict === "ready_candidate" && validation && !isStale/);
});

test("manual confirmation success does not clear AI advisory or refetch projects", () => {
  const mutationStart = source.indexOf("async function changeValidation");
  const mutationEnd = source.indexOf("const evidenceBusy", mutationStart);
  const mutationSource = source.slice(mutationStart, mutationEnd);

  assert.match(mutationSource, /setEvidence\(\(current\) => \(\{ \.\.\.current, \[milestoneId\]: payload \}\)\)/);
  assert.match(mutationSource, /setMessage\(status === "done"/);
  assert.doesNotMatch(mutationSource, /setReviews/);
  assert.doesNotMatch(mutationSource, /refreshProjects/);
  assert.doesNotMatch(source, /async function refreshProjects/);
});
