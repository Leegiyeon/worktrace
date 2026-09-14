import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/branches/page.tsx", import.meta.url), "utf8");

test("branches page renders one selected-project graph instead of every project repository", () => {
  assert.match(page, /<h1>브랜치 그래프<\/h1>/);
  assert.match(page, /<label className=\{styles\.projectField\}>\s*<span>프로젝트<\/span>/);
  assert.match(page, /selectedProjectId/);
  assert.match(page, /\/api\/projects\/\$\{selectedProjectId\}\/repository/);
  assert.match(page, /<BranchActivityGraph/);
  assert.match(page, /projectName=\{selectedProject\.title\}/);
  assert.match(page, /repositoryName=\{repository\.full_name\}/);
  assert.doesNotMatch(page, /SelectedBranchActivityGraph/);
  assert.doesNotMatch(page, /progress_percent|프로젝트 진척/);
  assert.doesNotMatch(page, /Promise\.all/);
  assert.doesNotMatch(page, /projects\.map\(async/);
  assert.doesNotMatch(page, /dashboard-topbar|eyebrow|stacked-section/);
});

test("branches page separates fetch failure, disconnected, loading, and retry states", () => {
  assert.match(page, /AbortController/);
  assert.match(page, /selectedProjectIdRef/);
  assert.doesNotMatch(page, /setSelectedProjectId\(\([^)]*\)\s*=>/);
  assert.match(page, /role="status"/);
  assert.match(page, /repositoryError/);
  assert.match(page, /저장소 연결 정보를 불러오지 못했습니다\./);
  assert.match(page, /연결된 GitHub 저장소가 없습니다\./);
  assert.match(page, /다시 불러오기/);
});
