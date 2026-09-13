import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const graph = readFileSync(new URL("../app/projects/[projectId]/BranchActivityGraph.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/branches/page.tsx", import.meta.url), "utf8");
const proxy = readFileSync(new URL("../app/api/projects/[projectId]/branch-activity/route.ts", import.meta.url), "utf8");
const header = readFileSync(new URL("../app/components/AppHeader.tsx", import.meta.url), "utf8");


test("branch dashboard compares work branches without mutating project state", () => {
  assert.match(page, /브랜치 그래프/);
  assert.match(graph, /ahead_by/);
  assert.match(graph, /behind_by/);
  assert.match(graph, /최근 30일/);
  assert.match(graph, /polyline/);
  assert.doesNotMatch(graph, /method:\s*"PATCH"/);
  assert.doesNotMatch(graph, /method:\s*"POST"/);
});


test("branch activity is available through an authenticated project proxy", () => {
  assert.match(proxy, /proxyBackend/);
  assert.match(proxy, /branch-activity/);
  assert.match(header, /href="\/branches"/);
  assert.match(header, />브랜치 그래프</);
});
