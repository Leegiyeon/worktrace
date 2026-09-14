import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const panel = read("app/projects/[projectId]/CareerPanel.tsx");
const styles = read("app/projects/[projectId]/CareerPanel.module.css");

test("career panel selects one generated version ordered by created_at", () => {
  assert.match(panel, /onGenerate: \(targetRole: CareerTargetRole\) => Promise<CareerAsset \| null>/);
  assert.match(panel, /function sortCareerAssets\(assets: CareerAsset\[\]\)[\s\S]*?b\.created_at\.localeCompare\(a\.created_at\)/);
  assert.match(panel, /const sortedAssets = useMemo\(\(\) => sortCareerAssets\(careerAssets\), \[careerAssets\]\)/);
  assert.match(panel, /const \[selectedAssetId, setSelectedAssetId\] = useState\(""\)/);
  assert.match(panel, /const selectedAsset = sortedAssets\.find\(\(asset\) => asset\.id === selectedAssetId\) \?\? sortedAssets\[0\] \?\? null/);
  assert.match(panel, /<select aria-label="버전" value=\{selectedAsset\?\.id \?\? ""\}/);
  assert.match(panel, /sortedAssets\.map\(\(asset, index\) => <option key=\{asset\.id\} value=\{asset\.id\}>\{versionLabel\(asset, index\)\}<\/option>\)/);
  assert.doesNotMatch(panel, /careerAssets\.map\(\(asset\)/);
  assert.doesNotMatch(panel, /summary-grid inline outcome-metrics/);
});

test("career panel protects dirty drafts on version switch and generation", () => {
  assert.match(panel, /function isDirtyDraft\(asset: CareerAsset \| null, draft: CareerDraft \| null\)/);
  assert.match(panel, /window\.confirm\("편집 중인 초안을 버릴까요\?"\)/);
  assert.match(panel, /function selectVersion\(assetId: string\)[\s\S]*?if \(!confirmDraftDiscard\(\)\) return;[\s\S]*?setSelectedAssetId\(assetId\)/);
  assert.match(panel, /function cancelEdit\(\)[\s\S]*?if \(!confirmDraftDiscard\(\)\) return;[\s\S]*?setEditingId\(null\)/);
  assert.match(panel, /async function generateAsset\(\)[\s\S]*?const generatedAsset = await onGenerate\(targetRole\);[\s\S]*?if \(!generatedAsset\) return;[\s\S]*?clearDraft\(\);[\s\S]*?setSelectedAssetId\(generatedAsset\.id\)/);
  const generateBody = panel.slice(panel.indexOf("async function generateAsset"), panel.indexOf("function startEdit"));
  assert.doesNotMatch(generateBody, /clearDraft\(\)[\s\S]*?await onGenerate\(targetRole\)/);
  assert.doesNotMatch(generateBody, /setSelectedAssetId\(""\)/);
});

test("career panel locks save state and keeps copy aligned with draft edits", () => {
  assert.match(panel, /const isBusy = isSaving \|\| isGeneratingCareer/);
  assert.match(panel, /<article className=\{styles\.careerResult\} aria-busy=\{isBusy\}>/);
  assert.match(panel, /<select aria-label="버전" value=\{selectedAsset\?\.id \?\? ""\}[\s\S]*?disabled=\{isBusy \|\| sortedAssets\.length === 0\}/);
  assert.match(panel, /<select aria-label="목표 역할" value=\{targetRole\}[\s\S]*?disabled=\{isBusy\}/);
  for (const label of ["수행 요약", "성과 요약", "이력서 문장", "경력기술서", "포트폴리오", "STAR 답변"]) {
    assert.match(panel, new RegExp(`<textarea aria-label="${label}" disabled=\\{isBusy\\}`));
  }
  assert.match(panel, /<button className="secondary-button" type="button" onClick=\{\(\) => void handleCopy\(selectedAsset\)\} disabled=\{isBusy\}>Markdown 복사<\/button>/);
  assert.match(panel, /navigator\.clipboard\.writeText\(careerCopyDraftText\(asset, isEditingSelected \? draft : null\)\)/);
  const saveCatch = panel.slice(panel.indexOf("async function handleSave"), panel.indexOf("async function handleCopy"));
  assert.doesNotMatch(saveCatch.slice(saveCatch.indexOf("} catch (error) {")), /setDraft\(null\)|setEditingId\(null\)/);
});

test("career panel has scoped responsive workflow styles", () => {
  assert.match(panel, /import styles from "\.\/CareerPanel\.module\.css"/);
  assert.match(panel, /<section className=\{styles\.careerWorkbench\}>/);
  assert.doesNotMatch(panel, /<section className=\{`panel \$\{styles\.careerWorkbench\}`\}>/);
  assert.match(styles, /\.workflowControls \{[\s\S]*?grid-template-areas: "version role generate"/);
  assert.match(styles, /@media \(max-width: 820px\)[\s\S]*?"version version"[\s\S]*?"role generate"/);
  assert.match(styles, /@media \(max-width: 360px\)[\s\S]*?"version"[\s\S]*?"role"[\s\S]*?"generate"/);
  assert.match(styles, /overflow-wrap: anywhere/);
  assert.doesNotMatch(styles, /font-size:\s*clamp\(|vw/);
});
