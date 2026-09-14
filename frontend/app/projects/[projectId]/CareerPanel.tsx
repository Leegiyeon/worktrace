"use client";

import { useMemo, useState } from "react";

import { parseApiErrorMessage } from "../../reports/api-error";
import type { CareerAsset, CareerTargetRole } from "../types";
import styles from "./CareerPanel.module.css";

type CareerDraft = Pick<
  CareerAsset,
  "work_summary" | "outcome_summary" | "resume_bullets" | "career_description" | "portfolio_description" | "star_answer"
>;

type CareerPanelProps = {
  projectId: string;
  careerAssets: CareerAsset[];
  careerMessage: string;
  isGeneratingCareer: boolean;
  onGenerate: (targetRole: CareerTargetRole) => Promise<CareerAsset | null>;
  onAssetUpdated: (asset: CareerAsset) => void;
};

const careerTargetRoles: CareerTargetRole[] = ["IT기획", "PM", "AI서비스기획", "Backend", "DevOps"];

function createDraft(asset: CareerAsset): CareerDraft {
  return {
    work_summary: asset.work_summary,
    outcome_summary: asset.outcome_summary,
    resume_bullets: asset.resume_bullets,
    career_description: asset.career_description,
    portfolio_description: asset.portfolio_description,
    star_answer: asset.star_answer
  };
}

function buildMarkdown(asset: CareerAsset, draft: CareerDraft) {
  return [
    "## 근거 요약",
    asset.source_summary,
    "## 수행 요약",
    draft.work_summary,
    "## 성과 요약",
    draft.outcome_summary,
    "## 이력서 문장",
    draft.resume_bullets,
    "## 경력기술서",
    draft.career_description,
    "## 포트폴리오",
    draft.portfolio_description,
    "## STAR 답변",
    draft.star_answer
  ].join("\n\n");
}

function careerCopyText(asset: CareerAsset) {
  return asset.markdown || [asset.resume_bullets, asset.career_description, asset.portfolio_description, asset.star_answer].filter(Boolean).join("\n\n");
}

function careerCopyDraftText(asset: CareerAsset, draft: CareerDraft | null) {
  return draft ? buildMarkdown(asset, draft) : careerCopyText(asset);
}

function sortCareerAssets(assets: CareerAsset[]) {
  return [...assets].sort((a, b) => {
    const createdOrder = b.created_at.localeCompare(a.created_at);
    return createdOrder || b.id.localeCompare(a.id);
  });
}

function versionLabel(asset: CareerAsset, index: number) {
  const createdDate = asset.created_at.slice(0, 10);
  return `${index === 0 ? "최신" : `${index + 1}번째`} · ${createdDate} · ${asset.generation_method}`;
}

function isDirtyDraft(asset: CareerAsset | null, draft: CareerDraft | null) {
  if (!asset || !draft) return false;
  const baseline = createDraft(asset);
  return (Object.keys(baseline) as Array<keyof CareerDraft>).some((key) => baseline[key] !== draft[key]);
}

export function CareerPanel({
  projectId,
  careerAssets,
  careerMessage,
  isGeneratingCareer,
  onGenerate,
  onAssetUpdated
}: CareerPanelProps) {
  const [targetRole, setTargetRole] = useState<CareerTargetRole>("PM");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CareerDraft | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const sortedAssets = useMemo(() => sortCareerAssets(careerAssets), [careerAssets]);
  const selectedAsset = sortedAssets.find((asset) => asset.id === selectedAssetId) ?? sortedAssets[0] ?? null;
  const isEditingSelected = Boolean(selectedAsset && editingId === selectedAsset.id && draft);
  const hasDirtyDraft = isDirtyDraft(selectedAsset, isEditingSelected ? draft : null);
  const isBusy = isSaving || isGeneratingCareer;

  function confirmDraftDiscard() {
    return !hasDirtyDraft || window.confirm("편집 중인 초안을 버릴까요?");
  }

  function clearDraft() {
    setEditingId(null);
    setDraft(null);
  }

  function selectVersion(assetId: string) {
    if (isBusy || assetId === selectedAsset?.id) return;
    if (!confirmDraftDiscard()) return;
    clearDraft();
    setSelectedAssetId(assetId);
    setStatusMessage("");
    setErrorMessage("");
  }

  async function generateAsset() {
    if (isBusy) return;
    if (!confirmDraftDiscard()) return;
    setStatusMessage("");
    setErrorMessage("");
    const generatedAsset = await onGenerate(targetRole);
    if (!generatedAsset) return;
    clearDraft();
    setSelectedAssetId(generatedAsset.id);
  }

  function startEdit(asset: CareerAsset) {
    if (isBusy) return;
    setEditingId(asset.id);
    setDraft(createDraft(asset));
    setStatusMessage("");
    setErrorMessage("");
  }

  function cancelEdit() {
    if (isBusy) return;
    if (!confirmDraftDiscard()) return;
    setEditingId(null);
    setDraft(null);
    setErrorMessage("");
  }

  async function handleSave(asset: CareerAsset) {
    if (!draft || isGeneratingCareer) return;
    setIsSaving(true);
    setStatusMessage("");
    setErrorMessage("");
    try {
      const response = await fetch(`/api/projects/${projectId}/career-assets/${asset.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...draft, markdown: buildMarkdown(asset, draft) })
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(parseApiErrorMessage(detail, "경력 자산을 저장하지 못했습니다."));
      }
      const updatedAsset = (await response.json()) as CareerAsset;
      onAssetUpdated(updatedAsset);
      setSelectedAssetId(updatedAsset.id);
      setEditingId(null);
      setDraft(null);
      setStatusMessage("경력 자산 저장 완료");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "경력 자산을 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCopy(asset: CareerAsset) {
    setStatusMessage("");
    setErrorMessage("");
    try {
      await navigator.clipboard.writeText(careerCopyDraftText(asset, isEditingSelected ? draft : null));
      setStatusMessage("Markdown 복사 완료");
    } catch {
      setErrorMessage("클립보드에 복사하지 못했습니다.");
    }
  }

  return (
    <section className={styles.careerDashboard}>
      <section className={styles.careerWorkbench}>
        <div className={`panel-title-row ${styles.panelTitleRow}`}>
          <h2>경력 자산</h2>
          <span className="meta-pill">{careerAssets.length}개 버전</span>
        </div>
        <div className={styles.workflowControls}>
          <label>버전
            <select aria-label="버전" value={selectedAsset?.id ?? ""} onChange={(event) => selectVersion(event.target.value)} disabled={isBusy || sortedAssets.length === 0}>
              {sortedAssets.length === 0 ? <option value="">저장된 버전 없음</option> : null}
              {sortedAssets.map((asset, index) => <option key={asset.id} value={asset.id}>{versionLabel(asset, index)}</option>)}
            </select>
          </label>
          <label>목표 역할
            <select aria-label="목표 역할" value={targetRole} onChange={(event) => setTargetRole(event.target.value as CareerTargetRole)} disabled={isBusy}>
              {careerTargetRoles.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </label>
          <button className="primary-button" type="button" onClick={() => void generateAsset()} disabled={isBusy}>
            {isGeneratingCareer ? "생성 중" : "새 초안 생성"}
          </button>
        </div>
        {careerMessage ? <div aria-live="polite" className="alert success" role="status">{careerMessage}</div> : null}
        {statusMessage ? <div aria-live="polite" className="alert success" role="status">{statusMessage}</div> : null}
        {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}

        {selectedAsset ? (
          <article className={styles.careerResult} aria-busy={isBusy}>
            <div className={styles.resultHeader}>
              <div>
                <strong>{selectedAsset.generation_method}</strong>
                <span>생성 {selectedAsset.created_at.slice(0, 10)} · 수정 {selectedAsset.updated_at.slice(0, 10)}</span>
              </div>
            </div>

            {isEditingSelected && draft ? (
              <div className={styles.editGrid}>
                <label>수행 요약<textarea aria-label="수행 요약" disabled={isBusy} value={draft.work_summary} onChange={(event) => setDraft({ ...draft, work_summary: event.target.value })} /></label>
                <label>성과 요약<textarea aria-label="성과 요약" disabled={isBusy} value={draft.outcome_summary} onChange={(event) => setDraft({ ...draft, outcome_summary: event.target.value })} /></label>
                <label>이력서 문장<textarea aria-label="이력서 문장" disabled={isBusy} value={draft.resume_bullets} onChange={(event) => setDraft({ ...draft, resume_bullets: event.target.value })} /></label>
                <label>경력기술서<textarea aria-label="경력기술서" disabled={isBusy} value={draft.career_description} onChange={(event) => setDraft({ ...draft, career_description: event.target.value })} /></label>
                <label>포트폴리오<textarea aria-label="포트폴리오" disabled={isBusy} value={draft.portfolio_description} onChange={(event) => setDraft({ ...draft, portfolio_description: event.target.value })} /></label>
                <label>STAR 답변<textarea aria-label="STAR 답변" disabled={isBusy} value={draft.star_answer} onChange={(event) => setDraft({ ...draft, star_answer: event.target.value })} /></label>
              </div>
            ) : (
              <div className={styles.previewGrid}>
                <section><span>이력서 문장</span><p>{selectedAsset.resume_bullets || "-"}</p></section>
                <section><span>성과 요약</span><p>{selectedAsset.outcome_summary || "-"}</p></section>
                <section><span>경력기술서</span><p>{selectedAsset.career_description || "-"}</p></section>
                <section><span>포트폴리오</span><p>{selectedAsset.portfolio_description || "-"}</p></section>
                <details className={styles.copyDetails}><summary>전체 결과</summary><pre className={styles.copyOutput}>{careerCopyText(selectedAsset) || "경력 문장 없음"}</pre></details>
              </div>
            )}
            <div className={`form-actions compact-actions ${styles.resultActions}`}>
              {isEditingSelected ? <button className="secondary-button" type="button" onClick={cancelEdit} disabled={isBusy}>취소</button> : null}
              {isEditingSelected ? (
                <button className="primary-button" type="button" onClick={() => void handleSave(selectedAsset)} disabled={isBusy}>{isSaving ? "저장 중" : "수정 저장"}</button>
              ) : (
                <button className="secondary-button" type="button" onClick={() => startEdit(selectedAsset)} disabled={isBusy}>편집</button>
              )}
              <button className="secondary-button" type="button" onClick={() => void handleCopy(selectedAsset)} disabled={isBusy}>Markdown 복사</button>
            </div>
          </article>
        ) : (
          <div className="empty-state">저장된 경력 자산 없음</div>
        )}
      </section>
    </section>
  );
}
