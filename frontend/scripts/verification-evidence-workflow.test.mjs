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
  assert.match(source, /completion: CompletionState/);
  assert.match(source, /defaultCompletion/);
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
  assert.match(source, /disabled=\{isLoading \|\| controlsLocked \|\| projects\.length === 0\}/);
  assert.match(source, /<summary>고급<\/summary>/);
  assert.match(source, /전체 강제 재검토/);
  assert.match(source, /reviewProject\(project, true\)/);
});

test("manual confirmation drafts survive errors and conflicts require refresh", () => {
  assert.match(source, /type ConfirmationDraft/);
  assert.match(source, /type ConfirmationRequestPayload/);
  assert.match(source, /confirmationDrafts/);
  assert.match(source, /conflictNeedsRefresh/);
  assert.match(source, /pending_request: ConfirmationRequestPayload \| null/);
  assert.match(source, /savingMilestonesRef/);
  assert.match(source, /response\.status === 409/);
  assert.match(source, /근거 새로고침 후 다시 저장/);
  assert.match(source, /pending_request: requestPayload/);
  assert.match(source, /pending_request: null/);
  assert.match(source, /getEvidence\(projectId, milestoneId, \{ resolveConfirmationDraft: true \}\)/);
  assert.match(source, /async function getEvidence\(projectId: string, milestoneId: string, options: \{ resolveConfirmationDraft\?: boolean \} = \{\}\)/);
  assert.match(source, /const reasonInputId = `confirmation-reason-\$\{milestone\.id\}`/);
  assert.match(source, /const evidenceNoteInputId = `confirmation-evidence-note-\$\{milestone\.id\}`/);
  assert.match(source, /value=\{draft\.reason\}/);
  assert.match(source, /value=\{draft\.evidence_note\}/);
  assert.match(source, /<label htmlFor=\{evidenceNoteInputId\}>/);
  assert.match(source, /id=\{evidenceNoteInputId\}/);
  assert.match(source, /disabled=\{confirmationEditLocked\}/);
  assert.match(source, /같은 완료 확인 다시 시도/);
  assert.match(source, /완료 확인 저장/);
  assert.doesNotMatch(source, />저장<\/button>/);
});

test("manual confirmation is disclosed and history shows actor with Seoul timestamp", () => {
  assert.match(source, /<details className=\{styles\.confirmationPanel\}/);
  assert.match(source, /className=\{styles\.confirmationSummary\}/);
  assert.match(source, /formatDateTimeSeoul\(entry\.confirmed_at\)/);
  assert.match(source, /entry\.actor_owner_id/);
  assert.match(source, /Asia\/Seoul/);
});

test("scoped CSS covers compact responsive verification layout", () => {
  assert.match(css, /\.summaryGrid/);
  assert.match(css, /\.milestoneRow/);
  assert.match(css, /\.confirmationPanel/);
  assert.match(css, /\.confirmationSummary/);
  assert.match(css, /\.historyDisclosure/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /@media \(max-width: 360px\)/);
});
