import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
const read = path => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("recorded completion timestamps and bounded commit results have literal labels", () => {
  assert.match(read("app/page.tsx"), /이번 주 완료 처리한 업무/);
  assert.match(read("app/page.tsx"), /완료 처리일 \(한국 시간\)/);
  assert.match(read("app/page.tsx"), /recordedCompletionsThisWeek\(/);
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
  assert.match(evidence, /진행 계획 승인/);
  assert.match(evidence, /progress_plan_status === "approved"/);
  assert.match(evidence, /project\.derived_task_count === undefined/);
  assert.match(evidence, /사용자 지정 · WBS 완료율과 별도/);
  assert.match(read("app/projects/[projectId]/page.tsx"), /<ProgressEvidence project={project} \/>/);
});

test("project plan review is inline and guarded by explicit approval", () => {
  const page = read("app/projects/[projectId]/page.tsx");
  const panel = read("app/projects/[projectId]/ProjectPlanPanel.tsx");
  const route = read("app/api/projects/[projectId]/plan/route.ts");
  assert.match(page, /<ProjectPlanPanel projectId={projectId} onApproved={refreshPlanningData} \/>/);
  assert.match(panel, /policy: ProgressPlanPolicy/);
  assert.match(panel, /expected_version: snapshot\.version/);
  assert.match(panel, /expected_context_fingerprint: snapshot\.context_fingerprint/);
  assert.match(panel, /request_id: makeRequestId\(\)/);
  assert.match(panel, /exclusion_reason: excludedTasks\.length > 0 \? exclusionReason\.trim\(\) : ""/);
  assert.match(panel, /excludedTasks\.length > 0 && !exclusionReason\.trim\(\)/);
  assert.match(panel, /snapshot\.derived_task_count > 0 && !reviewedDerived/);
  assert.match(panel, /setPending\(body\)/);
  assert.match(panel, /response\.status === 409/);
  assert.match(panel, /setReviewedDerived\(false\)/);
  assert.match(panel, /<details className=\{styles\.reviewDetails\}>/);
  assert.match(panel, /snapshot\.history\.slice\(0, 20\)/);
  assert.doesNotMatch(page, /tab.*plan|계획 승인 탭/);
  assert.match(route, /proxyBackend\(request, `\/projects\/\$\{encodePathSegment\(projectId\)\}\/plan`\)/);
});
