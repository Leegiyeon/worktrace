import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("stale persisted reviews are visible but cannot complete validation", () => {
  assert.match(source, /is_stale: boolean/);
  assert.match(source, /AI 재검토가 필요합니다/);
  assert.match(source, /이전 판단/);
  assert.match(source, /reviewResult\?\.verdict === "ready_candidate" && validation && !isStale/);
});

test("project review summary counts only current AI reviews", () => {
  assert.match(source, /유효 AI 검토/);
  assert.match(source, /!isStoredReview\(review\) \|\| !review\.is_stale/);
});
