import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ModuleKind, transpileModule } from "typescript";

const source = readFileSync(new URL("../app/projects/task-completion.ts", import.meta.url), "utf8");
const compiled = transpileModule(source, { compilerOptions: { module: ModuleKind.ESNext } }).outputText;
const { recordedCompletionsThisWeek, completionDateLabel } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const task = (id, completed_at, overrides = {}) => ({ id, status: "done", completed_at, source_provider: null, updated_at: "2026-09-18T00:00:00Z", ...overrides });

test("weekly completions use Monday in Korea, not modified dates or inferred evidence", () => {
  const tasks = [
    task("before", "2026-09-13T14:59:59Z"),
    task("boundary", "2026-09-13T15:00:00Z"),
    task("latest", "2026-09-18T00:00:00Z"),
    task("future", "2026-09-19T00:00:00Z"),
    task("unknown", null), task("invalid", "not a date"),
    task("reopened", "2026-09-18T00:00:00Z", { status: "in_progress" }),
    task("derived", "2026-09-18T00:00:00Z", { source_provider: "derived-github" }),
    task("old-api", "2026-09-18T00:00:00Z", { source_provider: undefined }),
  ];
  assert.deepEqual(recordedCompletionsThisWeek(tasks, new Date("2026-09-18T00:00:00Z")).map(t => t.id), ["latest", "boundary"]);
  assert.equal(tasks[0].id, "before");
});

test("completion labels never fabricate missing dates", () => {
  assert.equal(completionDateLabel(null), "미확인");
  assert.equal(completionDateLabel("invalid"), "미확인");
  assert.match(completionDateLabel("2026-09-13T15:00:00Z"), /2026.*09.*14/);
});
