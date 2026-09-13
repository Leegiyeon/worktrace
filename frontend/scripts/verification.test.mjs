import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("verification center supports project-wide AI review without auto-completing milestones", () => {
  assert.match(source, /async function reviewProject\(project: ProjectWithMilestones\)/);
  assert.match(source, /AI 전체 검토/);
  assert.match(source, /validation_wbs\?\.status === "done"/);
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
  assert.match(source, /window\.confirm\("성취 기준과 Evidence를 직접 확인했습니다/);
  assert.match(source, /reviewResult\?\.verdict === "ready_candidate"/);
  assert.match(source, /성취 기준 확인 · 검증 완료/);
  assert.match(source, /검증 완료 유지/);
  assert.match(source, /일부 마일스톤 \$\{failed\}건은 검토하지 못했습니다/);
});
