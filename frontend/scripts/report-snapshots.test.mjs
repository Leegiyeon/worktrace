import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const reportsPage = read("app/reports/page.tsx");
const reportTypes = read("app/reports/types.ts");
const archiveCss = read("app/reports/ReportArchive.module.css");
const collectionRoute = read("app/api/reports/snapshots/route.ts");
const detailRoute = read("app/api/reports/snapshots/[snapshotId]/route.ts");

test("snapshot proxy routes preserve collection and encoded detail contracts", () => {
  assert.match(collectionRoute, /export async function GET/);
  assert.match(collectionRoute, /export async function POST/);
  assert.match(collectionRoute, /proxyBackend\(request, "\/reports\/snapshots"\)/);
  assert.match(detailRoute, /export async function GET/);
  assert.match(detailRoute, /export async function DELETE/);
  assert.match(detailRoute, /encodePathSegment\(snapshotId\)/);
  assert.match(detailRoute, /`\/reports\/snapshots\/\$\{encodePathSegment\(snapshotId\)\}`/);
});

test("snapshot types expose summary list and immutable detail payload", () => {
  for (const field of ["id", "request_id", "report_type", "start_date", "end_date", "as_of", "created_at", "fingerprint"]) {
    assert.match(reportTypes, new RegExp(`${field}:`));
  }
  assert.match(reportTypes, /schema_version: "1"/);
  assert.match(reportTypes, /export type ReportSnapshotDetail = ReportSnapshotSummary & \{\s+report: AutoReportResponse;/);
  assert.match(reportTypes, /export type ReportSnapshotListResponse = \{/);
  assert.match(reportTypes, /items: ReportSnapshotSummary\[\]/);
  assert.match(reportTypes, /total: number/);
  assert.match(reportTypes, /limit: number/);
  assert.match(reportTypes, /offset: number/);
});

test("generation posts snapshots with retained failed request ids and stale response guards", () => {
  assert.match(reportsPage, /fetch\("\/api\/reports\/snapshots", \{ method: "POST"/);
  assert.match(reportsPage, /body: JSON\.stringify\(payload\)/);
  assert.match(reportsPage, /request_id: makeRequestId\(\)/);
  assert.match(reportsPage, /failedSnapshotRequestsRef = useRef\(new Map<string, SnapshotRequestPayload>\(\)\)/);
  assert.match(reportsPage, /failedSnapshotRequestsRef\.current\.get\(requestFilterKey\)/);
  assert.match(reportsPage, /failedSnapshotRequestsRef\.current\.set\(requestFilterKey, payload\)/);
  assert.match(reportsPage, /failedSnapshotRequestsRef\.current\.delete\(requestFilterKey\)/);
  assert.match(reportsPage, /archiveLoadedOnceRef\.current = false;\s+if \(latestRequestRef\.current\.sequence !== requestSequence/);
  assert.match(reportsPage, /latestRequestRef\.current\.sequence !== requestSequence \|\| latestRequestRef\.current\.filterKey !== requestFilterKey/);
  assert.match(reportsPage, /busyRequestRef\.current\?\.filterKey === requestFilterKey/);
  assert.doesNotMatch(reportsPage, /\/api\/reports\/automatic/);
  assert.match(reportsPage, /생성·보관/);
});

test("archive tab uses bounded paginated list with distinct empty and failure states", () => {
  assert.match(reportsPage, /aria-pressed=\{activeTab === "new"\}/);
  assert.match(reportsPage, /onClick=\{\(\) => \{ setActiveTab\("archive"\); void loadArchive\(0\); \}\}/);
  assert.match(reportsPage, />새 리포트<\/button>/);
  assert.match(reportsPage, />보관함<\/button>/);
  assert.match(reportsPage, /aria-label="보관 리포트 목록"/);
  assert.match(reportsPage, /limit=\$\{archivePageSize\}&offset=\$\{offset\}/);
  assert.match(reportsPage, /보관함을 불러오지 못했습니다\./);
  assert.match(reportsPage, /보관 항목 없음/);
  assert.match(reportsPage, />이전<\/button>/);
  assert.match(reportsPage, />다음<\/button>/);
  assert.match(archiveCss, /max-height:\s*520px/);
  assert.match(archiveCss, /overflow:\s*auto/);
});

test("saved report view labels historical state and keeps markdown as raw text", () => {
  assert.match(reportsPage, /보관 당시 잔여 WBS/);
  assert.match(reportsPage, /보관 당시 WBS 진척/);
  assert.match(reportsPage, /조회 기준 \{formatDateTime\(snapshot\.as_of\)\}/);
  assert.match(reportsPage, /저장 시각 \{formatDateTime\(snapshot\.created_at\)\}/);
  assert.match(reportsPage, /저장 시각 \{formatDateTime\(item\.created_at\)\}/);
  assert.match(reportsPage, /aria-label=\{`\$\{reportPeriodLabel\} 보관 리포트 결과`\}/);
  assert.match(reportsPage, /<pre className="markdown-output">\{report\.markdown\}<\/pre>/);
  assert.doesNotMatch(reportsPage, /dangerouslySetInnerHTML/);
});

test("snapshot delete and markdown download are explicit and local to archive copy", () => {
  assert.match(reportsPage, /window\.confirm\("보관본만 영구 삭제할까요\? 원본 업무 기록과 프로젝트 데이터는 삭제되지 않습니다\."\)/);
  assert.match(reportsPage, /detailSequenceRef\.current \+= 1/);
  assert.match(reportsPage, /deleteBusyRef\.current/);
  assert.match(reportsPage, /deletedSnapshotIdsRef\.current\.has\(snapshot\.id\)/);
  assert.match(reportsPage, /fetch\(`\/api\/reports\/snapshots\/\$\{encodeURIComponent\(snapshot\.id\)\}`, \{ method: "DELETE" \}\)/);
  assert.match(reportsPage, /!response\.ok && response\.status !== 404/);
  assert.doesNotMatch(reportsPage, /이미 삭제되었거나 찾을 수 없는 보관 리포트입니다/);
  assert.match(reportsPage, /setSelectedSnapshot\(\(current\) => current\?\.id === snapshot\.id \? null : current\)/);
  assert.match(reportsPage, /setGeneratedSnapshot\(\(current\) => current\?\.id === snapshot\.id \? null : current\)/);
  assert.match(reportsPage, /remainingOnPage === 0 && archiveOffset > 0/);
  assert.match(reportsPage, /new Blob\(\[snapshot\.report\.markdown\], \{ type: "text\/markdown;charset=utf-8" \}\)/);
  assert.match(reportsPage, /URL\.createObjectURL\(blob\)/);
  assert.match(reportsPage, /URL\.revokeObjectURL\(url\)/);
  assert.match(reportsPage, /aria-label="Markdown 다운로드"/);
  assert.match(reportsPage, /Markdown 복사/);
});

test("copy and deletion feedback belong to their saved snapshot", () => {
  assert.match(reportsPage, /<SnapshotActions key=\{snapshot.id\}/);
  assert.match(reportsPage, /deleteError && deleteError.snapshotId === selectedSnapshot\?\.id/);
  assert.match(reportsPage, /deleteError && deleteError.snapshotId === generatedSnapshot\?\.id/);
  assert.match(reportsPage, /setDeleteError\(\{ snapshotId: snapshot.id/);
  assert.match(reportsPage, /async function loadSnapshot\(snapshot: ReportSnapshotSummary\) \{\s+if \(deleteBusyRef.current\) return;/);
});
