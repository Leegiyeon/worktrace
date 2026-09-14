"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { acceptSavedDraft, draftChanged, mergeProjectDrafts, type GoalDraftState, type ProjectDraft } from "../goals/goal-drafts";

function useGoalDraftStore() {
  const [state, setState] = useState<GoalDraftState>({ drafts: {}, baselines: {} });
  const [savingProjects, setSavingProjects] = useState<Record<string, boolean>>({});
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const savedRevision = useRef(0);
  const beginRead = useCallback(() => savedRevision.current, []);
  const dirtyProjectIds = useMemo(() => Object.keys(state.drafts).filter(id => draftChanged(state.drafts[id], state.baselines[id])), [state]);
  const isSaving = Object.values(savingProjects).some(Boolean);
  const mergeProjects = useCallback((projects: (ProjectDraft & { id: string })[], revision: number) => {
    if (revision === savedRevision.current) setState(current => mergeProjectDrafts(current, projects));
  }, []);
  const updateDraft = useCallback((id: string, patch: Partial<ProjectDraft>) => setState(current => ({
    ...current, drafts: { ...current.drafts, [id]: { ...current.drafts[id], ...patch } }
  })), []);
  const acceptSavedProject = useCallback((project: ProjectDraft & { id: string }, submitted: ProjectDraft) => {
    savedRevision.current += 1;
    setState(current => acceptSavedDraft(current, project, submitted));
  }, []);
  const resetDraft = useCallback((id: string) => setState(current => ({ ...current, drafts: { ...current.drafts, [id]: current.baselines[id] } })), []);
  const clearDrafts = useCallback(() => {
    savedRevision.current += 1;
    setState({ drafts: {}, baselines: {} });
    setSelectedProjectId("");
    setSavingProjects({});
  }, []);
  const confirmNavigation = useCallback((discard = false) => {
    if (isSaving) {
      window.alert("목표를 저장 중입니다. 저장이 끝난 후 이동하세요.");
      return false;
    }
    if (!dirtyProjectIds.length) return true;
    return window.confirm(discard
      ? "저장하지 않은 목표가 있습니다. 로그아웃하면 초안이 사라집니다. 로그아웃하시겠습니까?"
      : "저장하지 않은 목표가 있습니다. 다른 화면으로 이동하시겠습니까? 초안은 현재 탭에서 유지됩니다.");
  }, [dirtyProjectIds.length, isSaving]);

  useEffect(() => {
    if (!dirtyProjectIds.length && !isSaving) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const guardLink = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;
      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin || (destination.pathname === window.location.pathname && destination.search === window.location.search)) return;
      if (!confirmNavigation()) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    document.addEventListener("click", guardLink, true);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      document.removeEventListener("click", guardLink, true);
    };
  }, [dirtyProjectIds.length, isSaving, confirmNavigation]);

  return { drafts: state.drafts, dirtyProjectIds, beginRead, mergeProjects, updateDraft, resetDraft, acceptSavedProject, savingProjects, setSavingProjects, selectedProjectId, setSelectedProjectId, confirmNavigation, clearDrafts };
}

const GoalDraftContext = createContext<ReturnType<typeof useGoalDraftStore> | null>(null);

export function GoalDraftProvider({ children }: { children: ReactNode }) {
  const value = useGoalDraftStore();
  return <GoalDraftContext.Provider value={value}>{children}</GoalDraftContext.Provider>;
}

export function useGoalDrafts() {
  const context = useContext(GoalDraftContext);
  if (!context) throw new Error("GoalDraftProvider is required");
  return context;
}
