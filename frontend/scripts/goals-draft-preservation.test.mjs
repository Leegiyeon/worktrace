import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../app/goals/page.tsx", import.meta.url), "utf8");

test("goal saves update only the saved project and preserve other dirty drafts", () => {
  assert.match(source, /function mergeProjectDrafts/);
  assert.match(source, /draftChanged\(currentDraft, project\)/);
  assert.match(source, /const savedProject = \(await response\.json\(\)\) as ProjectSummary/);
  assert.match(source, /setProjects\(\(current\) => current\.map\(\(item\) => item\.id === project\.id/);
  assert.doesNotMatch(source, /await load\(\);\n\s*setSuccessMessage/);
});

test("goal save completion does not clobber edits made while save is pending", () => {
  assert.match(source, /saveCompletedBeforeFurtherEdit/);
  assert.match(source, /currentDraft\?\.objective === draft\.objective/);
  assert.match(source, /currentDraft \?\? toProjectDraft\(savedProject\)/);
});

test("goal saves track per-project busy state and expose dirty unload guard", () => {
  assert.match(source, /savingProjects/);
  assert.match(source, /delete next\[project\.id\]/);
  assert.match(source, /dirtyProjectIds/);
  assert.match(source, /beforeunload/);
  assert.match(source, /저장 안 됨/);
});
