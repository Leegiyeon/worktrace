import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/projects/[projectId]/page.tsx", import.meta.url), "utf8");
const save = page.slice(page.indexOf("  async function handleSaveOutcome"), page.indexOf("  function startEditOutcome"));

test("outcome edits preserve document evidence and consume the saved response", () => {
  assert.doesNotMatch(save, /evidence_document_ids: \[\]/);
  assert.match(save, /evidence_document_ids: existingOutcome\?\.evidence_document_ids \?\? \[\]/);
  assert.match(save, /await response.json\(\)/);
  assert.match(save, /setOutcomes/);
  assert.doesNotMatch(save, /await loadProject\(\)/);
});

test("outcomes separate candidate, review and confirmed views without automatic confirmation", () => {
  assert.match(page, /type OutcomeStage = "candidates" \| "review" \| "confirmed"/);
  assert.match(page, /isOutcomeFormVisible &&/);
  assert.match(page, /aria-label="성과 단계"/);
  assert.match(page, /근거를 확인했으며 이력서 반영을 확정합니다/);
  assert.match(save, /outcomeForm.resume_ready &&/);
  assert.match(page, /const changeForm[\s\S]*?resume_ready: false/);
  assert.match(page, /disabled={!canConfirm && !outcomeForm.resume_ready}/);
});

test("evidence selection is searchable with content inspection, not a multiple select", () => {
  assert.match(page, /aria-label="근거 로그 검색"/);
  assert.match(page, /aria-label="선택한 근거만"/);
  assert.match(page, /aria-label={`근거 선택: \$\{log.title\}`}/);
  assert.match(page, /<summary>근거 내용<\/summary>/);
  assert.doesNotMatch(page, /<select multiple value={outcomeForm/);
  assert.match(page, /<fieldset disabled={isSavingOutcome}/);
});

test("changing reviewed records protects drafts and failed saves retain input", () => {
  assert.match(page, /function confirmOutcomeReplacement/);
  assert.match(page, /if \(!confirmOutcomeReplacement\(\)\) return/);
  assert.ok(save.indexOf("if (!response.ok)") < save.indexOf("setOutcomeForm(createInitialOutcomeForm())"));
});

test("outcomes and career do not render empty collections before loading completes", () => {
  assert.match(page, /isLoading \? <div role="status">성과를 불러오는 중/);
  assert.match(page, /isLoading \? <div role="status">경력 자산을 불러오는 중/);
});
