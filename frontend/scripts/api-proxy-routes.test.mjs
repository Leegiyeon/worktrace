import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("backend proxy converts connection failures into a stable service error", () => {
  const backendProxy = read("app/api/backend.ts");

  assert.match(backendProxy, /try\s*\{/);
  assert.match(backendProxy, /catch\s*\{/);
  assert.match(backendProxy, /code: "BACKEND_UNAVAILABLE"/);
  assert.match(backendProxy, /\{ status: 502 \}/);
});

test("backend proxy preserves bodyless responses for delete and head requests", () => {
  const backendProxy = read("app/api/backend.ts");

  assert.match(backendProxy, /request\.method === "GET" \|\| request\.method === "HEAD" \? undefined/);
  assert.match(backendProxy, /request\.method === "HEAD" \|\| response\.status === 204 \? null/);
  assert.match(backendProxy, /new NextResponse\(body/);
});

test("work log detail proxy supports backend mutation methods", () => {
  const route = read("app/api/work-logs/[workLogId]/route.ts");

  assert.match(route, /export async function PATCH/);
  assert.match(route, /export async function DELETE/);
  assert.match(route, /`\/work-logs\/\$\{encodePathSegment\(workLogId\)\}`/);
});

test("project outcome detail proxy supports backend mutation methods", () => {
  const route = read("app/api/projects/[projectId]/outcomes/[outcomeId]/route.ts");

  assert.match(route, /export async function PATCH/);
  assert.match(route, /export async function DELETE/);
  assert.match(route, /`\/projects\/\$\{encodePathSegment\(projectId\)\}\/outcomes\/\$\{encodePathSegment\(outcomeId\)\}`/);
});

test("career asset detail proxy supports owner-scoped edits", () => {
  const route = read("app/api/projects/[projectId]/career-assets/[careerAssetId]/route.ts");

  assert.match(route, /export async function PATCH/);
  assert.match(route, /`\/projects\/\$\{encodePathSegment\(projectId\)\}\/career-assets\/\$\{encodePathSegment\(careerAssetId\)\}`/);
});

test("project task proxy routes preserve encoded collection and mutation paths", () => {
  const collectionRoute = read("app/api/projects/[projectId]/tasks/route.ts");
  const detailRoute = read("app/api/projects/[projectId]/tasks/[taskId]/route.ts");

  assert.match(collectionRoute, /export async function GET/);
  assert.match(collectionRoute, /export async function POST/);
  assert.match(collectionRoute, /`\/projects\/\$\{encodePathSegment\(projectId\)\}\/tasks`/);
  assert.match(detailRoute, /export async function PATCH/);
  assert.match(detailRoute, /export async function DELETE/);
  assert.match(detailRoute, /`\/projects\/\$\{encodePathSegment\(projectId\)\}\/tasks\/\$\{encodePathSegment\(taskId\)\}`/);
});

test("dashboard, report, AI draft, and career routes keep expected proxy methods", () => {
  const projectsRoute = read("app/api/projects/route.ts");
  const workLogsRoute = read("app/api/work-logs/route.ts");
  const autoReportRoute = read("app/api/reports/automatic/route.ts");
  const careerGenerateRoute = read("app/api/projects/[projectId]/career-assets/generate/route.ts");
  const draftRoute = read("app/api/ai/work-log-draft/route.ts");

  assert.match(projectsRoute, /export async function GET/);
  assert.match(projectsRoute, /export async function POST/);
  assert.match(projectsRoute, /proxyBackend\(request, "\/projects"\)/);
  assert.match(workLogsRoute, /export async function GET/);
  assert.match(workLogsRoute, /export async function POST/);
  assert.match(workLogsRoute, /proxyBackend\(request, "\/work-logs"\)/);
  assert.match(autoReportRoute, /export async function POST/);
  assert.match(autoReportRoute, /proxyBackend\(request, "\/reports\/automatic"\)/);
  assert.match(careerGenerateRoute, /export async function POST/);
  assert.match(careerGenerateRoute, /`\/projects\/\$\{encodePathSegment\(projectId\)\}\/career-assets\/generate`/);
  assert.match(draftRoute, /export async function POST/);
  assert.match(draftRoute, /proxyBackend\(request, "\/ai\/work-log-draft"\)/);
});
