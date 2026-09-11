"use client";

import { useState } from "react";

import { parseApiErrorMessage } from "../../reports/api-error";
import type { CareerAsset, CareerTargetRole } from "../types";

type CareerDraft = Pick<
  CareerAsset,
  "work_summary" | "outcome_summary" | "resume_bullets" | "career_description" | "portfolio_description" | "star_answer"
>;

type CareerPanelProps = {
  projectId: string;
  careerAssets: CareerAsset[];
  careerMessage: string;
  isGeneratingCareer: boolean;
  onGenerate: (targetRole: CareerTargetRole) => Promise<void>;
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

export function CareerPanel({
  projectId,
  careerAssets,
  careerMessage,
  isGeneratingCareer,
  onGenerate,
  onAssetUpdated
}: CareerPanelProps) {
  const [targetRole, setTargetRole] = useState<CareerTargetRole>("PM");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CareerDraft | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  function startEdit(asset: CareerAsset) {
    setEditingId(asset.id);
    setDraft(createDraft(asset));
    setStatusMessage("");
    setErrorMessage("");
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(null);
    setErrorMessage("");
  }

  async function handleSave(asset: CareerAsset) {
    if (!draft) return;
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
      await navigator.clipboard.writeText(careerCopyText(asset));
      setStatusMessage("Markdown 복사 완료");
    } catch {
      setErrorMessage("클립보드에 복사하지 못했습니다.");
    }
  }

  return (
    <section className="career-dashboard">
      <section className="panel career-generate-panel">
        <div className="panel-title-row">
          <h2>경력 자산 생성</h2>
          <span className="meta-pill">확정 근거만 사용</span>
        </div>
        <div className="career-generate-controls">
          <label>목표 역할
            <select value={targetRole} onChange={(event) => setTargetRole(event.target.value as CareerTargetRole)}>
              {careerTargetRoles.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </label>
          <button className="primary-button" type="button" onClick={() => void onGenerate(targetRole)} disabled={isGeneratingCareer}>
            {isGeneratingCareer ? "생성 중" : "새 초안 생성"}
          </button>
        </div>
        {careerMessage ? <div aria-live="polite" className="alert success" role="status">{careerMessage}</div> : null}
        {statusMessage ? <div aria-live="polite" className="alert success" role="status">{statusMessage}</div> : null}
        {errorMessage ? <div className="alert error" role="alert">{errorMessage}</div> : null}
        {careerAssets.length === 0 ? <div className="empty-state">저장된 경력 자산 없음</div> : null}
      </section>

      <section className="summary-grid inline outcome-metrics" aria-label="경력 자산 지표">
        <div className="metric-card"><span>저장 자산</span><strong>{careerAssets.length}</strong></div>
        <div className="metric-card"><span>이력서 초안</span><strong>{careerAssets.filter((asset) => asset.resume_bullets).length}</strong></div>
        <div className="metric-card"><span>포트폴리오</span><strong>{careerAssets.filter((asset) => asset.portfolio_description).length}</strong></div>
        <div className="metric-card"><span>면접 답변</span><strong>{careerAssets.filter((asset) => asset.star_answer).length}</strong></div>
      </section>

      <section className="career-editor-list" aria-label="저장된 경력 자산">
        {careerAssets.map((asset) => {
          const isEditing = editingId === asset.id && draft;
          return (
            <article className="panel career-editor-card" key={asset.id}>
              <div className="career-editor-header">
                <div>
                  <strong>{asset.generation_method}</strong>
                  <span>{asset.updated_at.slice(0, 10)} · {asset.source_summary}</span>
                </div>
              </div>

              {isEditing ? (
                <div className="career-edit-grid">
                  <label>수행 요약<textarea value={draft.work_summary} onChange={(event) => setDraft({ ...draft, work_summary: event.target.value })} /></label>
                  <label>성과 요약<textarea value={draft.outcome_summary} onChange={(event) => setDraft({ ...draft, outcome_summary: event.target.value })} /></label>
                  <label>이력서 문장<textarea value={draft.resume_bullets} onChange={(event) => setDraft({ ...draft, resume_bullets: event.target.value })} /></label>
                  <label>경력기술서<textarea value={draft.career_description} onChange={(event) => setDraft({ ...draft, career_description: event.target.value })} /></label>
                  <label>포트폴리오<textarea value={draft.portfolio_description} onChange={(event) => setDraft({ ...draft, portfolio_description: event.target.value })} /></label>
                  <label>STAR 답변<textarea value={draft.star_answer} onChange={(event) => setDraft({ ...draft, star_answer: event.target.value })} /></label>
                </div>
              ) : (
                <div className="career-preview-grid">
                  <section><span>이력서 문장</span><p>{asset.resume_bullets || "-"}</p></section>
                  <section><span>성과 요약</span><p>{asset.outcome_summary || "-"}</p></section>
                  <details><summary>전체 결과</summary><pre className="career-copy-output">{careerCopyText(asset) || "경력 문장 없음"}</pre></details>
                </div>
              )}
              <div className="form-actions compact-actions career-editor-actions">
                {isEditing ? <button className="secondary-button" type="button" onClick={cancelEdit}>취소</button> : null}
                {isEditing ? (
                  <button className="primary-button" type="button" onClick={() => void handleSave(asset)} disabled={isSaving}>{isSaving ? "저장 중" : "수정 저장"}</button>
                ) : (
                  <button className="secondary-button" type="button" onClick={() => startEdit(asset)}>편집</button>
                )}
                <button className="secondary-button" type="button" onClick={() => void handleCopy(asset)}>Markdown 복사</button>
              </div>
            </article>
          );
        })}
      </section>
    </section>
  );
}
