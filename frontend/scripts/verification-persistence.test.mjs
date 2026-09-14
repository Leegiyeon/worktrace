import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("persisted milestone reviews are restored without changing validation state", () => {
  assert.match(source, /type StoredMilestoneReview/);
  assert.match(source, /async function loadLatestReviews/);
  assert.match(source, /\/api\/ai\/milestone-reviews\/\$\{project\.id\}/);
  assert.match(source, /setReviews\(storedReviews\.reviews\)/);
  assert.match(source, /setReviewLoadErrors\(storedReviews\.reviewErrors\)/);
  assert.match(source, /최근 AI 검토/);

  const restoreStart = source.indexOf("async function loadLatestReviews");
  const restoreEnd = source.indexOf("function verdictLabel", restoreStart);
  const restoreSource = source.slice(restoreStart, restoreEnd);
  assert.doesNotMatch(restoreSource, /method:\s*"PATCH"/);
  assert.doesNotMatch(restoreSource, /changeValidation\(/);
});
