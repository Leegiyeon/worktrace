import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ModuleKind, transpileModule } from "typescript";

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const compiled = transpileModule(read("app/goals/goal-drafts.ts"), { compilerOptions: { module: ModuleKind.ESNext } }).outputText;
const { mergeProjectDrafts, acceptSavedDraft, draftChanged } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const a = { id: "a", objective: "목표 A", success_criteria: "기준 A" };
const b = { id: "b", objective: "목표 B", success_criteria: "기준 B" };
const initial = () => mergeProjectDrafts({ drafts: {}, baselines: {} }, [a, b]);

test("goal refresh preserves dirty projects and updates clean baselines", () => {
  const state = initial();
  state.drafts.a = { ...state.drafts.a, objective: "편집 중" };
  const merged = mergeProjectDrafts(state, [{ ...a, objective: "서버 갱신 A" }, { ...b, objective: "서버 갱신 B" }]);
  assert.equal(merged.drafts.a.objective, "편집 중");
  assert.equal(merged.drafts.b.objective, "서버 갱신 B");
  assert.equal(merged.baselines.a.objective, "서버 갱신 A");
  assert.equal(draftChanged(merged.drafts.b, merged.baselines.b), false);
});

test("goal saves affect only the saved project and accept trimmed server values", () => {
  const state = initial();
  state.drafts.a = { ...state.drafts.a, objective: " 변경 " };
  state.drafts.b = { ...state.drafts.b, objective: "B 초안" };
  const next = acceptSavedDraft(state, { ...a, objective: "변경" }, state.drafts.a);
  assert.equal(next.drafts.a.objective, "변경");
  assert.equal(next.drafts.b.objective, "B 초안");
  assert.equal(draftChanged(next.drafts.a, next.baselines.a), false);
  assert.equal(draftChanged(next.drafts.b, next.baselines.b), true);
});

test("goal save completion does not clobber edits made while save is pending", () => {
  const state = initial();
  const submitted = { ...state.drafts.a, objective: "제출" };
  state.drafts.a = { ...submitted, objective: "제출 후 편집" };
  const next = acceptSavedDraft(state, { ...a, ...submitted }, submitted);
  assert.equal(next.drafts.a.objective, "제출 후 편집");
  assert.equal(next.baselines.a.objective, "제출");
  assert.equal(draftChanged(next.drafts.a, next.baselines.a), true);
});

test("goal drafts survive route remounts without browser persistent storage", () => {
  const provider = read("app/components/GoalDraftProvider.tsx");
  const page = read("app/goals/page.tsx");
  assert.match(read("app/layout.tsx"), /<GoalDraftProvider>/);
  assert.match(page, /useGoalDrafts\(\)/);
  assert.match(page, /acceptSavedProject\(savedProject, draft\)/);
  assert.match(provider, /beforeunload/);
  assert.match(provider, /document\.addEventListener\("click", guardLink, true\)/);
  assert.doesNotMatch(provider, /localStorage|sessionStorage|pushState|history\.go/);
  assert.match(read("app/components/AppHeader.tsx"), /if \(confirmNavigation\(\)\) router\.push/);
  const logout = read("app/components/LogoutButton.tsx");
  assert.ok(logout.indexOf("confirmNavigation(true)") < logout.indexOf('fetch("/api/auth/logout"'));
  assert.match(logout, /if \(!response\.ok\) throw/);
  assert.match(logout, /clearDrafts\(\)/);
});
