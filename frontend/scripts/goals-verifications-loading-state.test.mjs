import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("unscoped goals have no zero-percent progress bar", () => {
  const source = readFileSync(new URL("../app/goals/page.tsx", import.meta.url), "utf8");
  assert.match(source, /progress\.percent !== null \? <div className="overview-bars"/);
  assert.doesNotMatch(source, /progress\.percent \?\? 0/);
});

const goalsSource = readFileSync(new URL("../app/goals/page.tsx", import.meta.url), "utf8");
const verificationsSource = readFileSync(new URL("../app/verifications/page.tsx", import.meta.url), "utf8");

test("goals distinguish milestone load failures from empty milestone lists", () => {
  assert.match(goalsSource, /milestoneErrors/);
  assert.match(goalsSource, /retryProjectMilestones/);
  assert.match(goalsSource, /마일스톤 다시 불러오기/);
  assert.match(goalsSource, /!milestoneError && project\.milestones\.length === 0/);
});

test("goals expose individual evidence and review retry instead of global empty fallbacks", () => {
  assert.match(goalsSource, /evidenceErrors/);
  assert.match(goalsSource, /reviewErrors/);
  assert.match(goalsSource, /function loadMilestoneEvidence/);
  assert.match(goalsSource, /근거 다시 불러오기/);
  assert.match(goalsSource, /AI 검토 다시 실행/);
});

test("verification center has loading, empty, project retry, and item retry states", () => {
  assert.match(verificationsSource, /const \[isLoading, setIsLoading\]/);
  assert.match(verificationsSource, /loadVerificationData/);
  assert.match(verificationsSource, /검증 데이터를 불러오는 중입니다/);
  assert.match(verificationsSource, /projects\.length === 0 \? <section className="empty-state">프로젝트가 없습니다/);
  assert.match(verificationsSource, /retryMilestones/);
  assert.match(verificationsSource, /retryStoredReviews/);
  assert.match(verificationsSource, /actionErrors/);
  assert.match(verificationsSource, /다시 시도/);
});

test("verification center does not show empty milestones when milestone loading failed", () => {
  assert.match(verificationsSource, /!milestoneError && project\.milestones\.length === 0/);
  assert.match(verificationsSource, /마일스톤 다시 불러오기/);
  assert.match(verificationsSource, /AI 검토 다시 불러오기/);
});

test("project load failures have retry controls and shared unscoped progress display", () => {
  assert.match(goalsSource, /loadGoalData/);
  assert.match(goalsSource, /loadErrorMessage/);
  assert.match(goalsSource, /scopedProjectAverage/);
  assert.match(goalsSource, /projectProgressDisplay/);
  assert.match(verificationsSource, /loadError/);
  assert.match(verificationsSource, /projectProgressDisplay/);
  assert.doesNotMatch(goalsSource, /function projectProgressLabel/);
});

test("verification batch AI actions stay disabled until milestone and review lookups recover", () => {
  assert.match(verificationsSource, /countsUnavailable/);
  assert.match(verificationsSource, /AI 검토 조회 보류/);
  assert.match(verificationsSource, /disabled=\{batchWorkingProjectId !== null \|\| countsUnavailable \|\| neededCount === 0\}/);
  assert.match(verificationsSource, /조회 복구 필요/);
});
