import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildBranchNetwork, branchColor } from "../lib/branch-network.mjs";

const graph = readFileSync(new URL("../app/projects/[projectId]/BranchActivityGraph.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/branches/page.tsx", import.meta.url), "utf8");
const proxy = readFileSync(new URL("../app/api/projects/[projectId]/branch-activity/route.ts", import.meta.url), "utf8");
const header = readFileSync(new URL("../app/components/AppHeader.tsx", import.meta.url), "utf8");


test("branch dashboard compares work branches without mutating project state", () => {
  assert.match(page, /브랜치 그래프/);
  assert.match(graph, /ahead_by/);
  assert.match(graph, /behind_by/);
  assert.match(graph, /브랜치 병합 네트워크/);
  assert.match(graph, /branchLine/);
  assert.match(graph, /branchLabel/);
  assert.match(graph, /buildBranchNetwork/);
  assert.doesNotMatch(graph, /polyline/);
  assert.doesNotMatch(graph, /method:\s*"PATCH"/);
  assert.doesNotMatch(graph, /method:\s*"POST"/);
});

const commit = (sha, parents = [], committed_at = "2026-09-01T00:00:00Z") => ({ sha, parents, committed_at, message: sha, url: `https://github.com/test/repo/commit/${sha}` });
const branch = (name, head_sha, commits, is_default = false) => ({ name, head_sha, commits, is_default, history_truncated: false });

test("network deduplicates shared history and renders only real merge parents", () => {
  const root = commit("root");
  const main = commit("main", ["root"]);
  const work = commit("work", ["root"]);
  const merge = commit("merge", ["main", "work"]);
  const graph = buildBranchNetwork([branch("main", "merge", [merge, main, work, root], true), branch("feat/work", "work", [work, root])]);
  assert.equal(graph.nodes.length, 4);
  assert.deepEqual(graph.edges.map(({ from, to }) => `${from}:${to}`).sort(), ["main:merge", "root:main", "root:work", "work:merge"]);
  assert.notEqual(graph.nodes.find((node) => node.sha === "work").y, graph.nodes.find((node) => node.sha === "merge").y);
  for (const label of graph.labels) assert.equal(label.x, graph.nodes.find((node) => node.sha === label.sha).x);
});

test("shared heads keep distinct nonoverlapping labels on the same commit", () => {
  const head = commit("same");
  const graph = buildBranchNetwork([branch("main", "same", [head], true), branch("release", "same", [head])]);
  assert.equal(graph.nodes.length, 1);
  assert.equal(graph.labels[0].x, graph.labels[1].x);
  assert.ok(Math.abs(graph.labels[0].y - graph.labels[1].y) >= 26);
  assert.equal(graph.incomplete, false);
});

test("missing ancestry is bounded, never replaced with a fabricated merge", () => {
  const graph = buildBranchNetwork([branch("main", "head", [commit("head", ["outside"])], true)]);
  assert.equal(graph.edges.length, 0);
  assert.deepEqual(graph.nodes[0].missingParents, ["outside"]);
  assert.equal(graph.incomplete, true);
});

test("parent ordering wins over skewed commit clocks and colors stay stable", () => {
  const commits = [commit("child", ["parent"], "2020"), commit("parent", [], "2030")];
  const graph = buildBranchNetwork([branch("main", "child", commits, true)]);
  assert.deepEqual(graph.nodes.map((node) => node.sha), ["parent", "child"]);
  assert.equal(branchColor("feat/work"), branchColor("feat/work"));
  assert.deepEqual(buildBranchNetwork([]).nodes, []);
});

test("all supported branch heads have distinct colors and permutation-stable layout", () => {
  const branches = Array.from({ length: 13 }, (_, index) => branch(index === 0 ? "main" : `feat/${index}`, `head${index}`, [commit(`head${index}`)], index === 0));
  const graph = buildBranchNetwork(branches);
  assert.equal(new Set(graph.labels.map((label) => label.color)).size, 13);
  assert.deepEqual(graph, buildBranchNetwork([...branches].reverse()));
});


test("branch activity is available through an authenticated project proxy", () => {
  assert.match(proxy, /proxyBackend/);
  assert.match(proxy, /branch-activity/);
  assert.match(header, /href="\/branches"/);
  assert.match(header, />브랜치 그래프</);
});
