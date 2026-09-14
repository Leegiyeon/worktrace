import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
const read = path => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("modified timestamps and bounded commit results have literal labels", () => {
  assert.match(read("app/page.tsx"), /이번 주 갱신된 완료 업무/);
  assert.match(read("app/page.tsx"), /<th>수정일<\/th>/);
  assert.doesNotMatch(read("app/page.tsx"), /<th>완료일<\/th>/);
  assert.match(read("app/projects/[projectId]/page.tsx"), /조회된 커밋 근거/);
});

test("model self-assessed confidence is not displayed as measured reliability", () => {
  for (const path of ["app/page.tsx", "app/goals/page.tsx", "app/insights/page.tsx", "app/verifications/page.tsx"]) {
    assert.doesNotMatch(read(path), /신뢰도\s*\{|Math\.round\([^)]*confidence\s*\*\s*100/);
  }
});

test("project detail exposes count provenance and keeps project status separate", () => {
  const evidence = read("app/projects/ProgressEvidence.tsx");
  assert.match(evidence, /자동 구성 WBS/);
  assert.match(evidence, /project\.derived_task_count === undefined/);
  assert.match(evidence, /사용자 지정 · WBS 완료율과 별도/);
  assert.match(read("app/projects/[projectId]/page.tsx"), /<ProgressEvidence project={project} \/>/);
});
