export type ProjectDraft = { objective: string; success_criteria: string };
type GoalProject = ProjectDraft & { id: string };
export type GoalDraftState = {
  drafts: Record<string, ProjectDraft>;
  baselines: Record<string, ProjectDraft>;
};

export function toProjectDraft(project: ProjectDraft): ProjectDraft {
  return { objective: project.objective, success_criteria: project.success_criteria };
}

export function draftChanged(draft: ProjectDraft | undefined, baseline: ProjectDraft | undefined) {
  return Boolean(draft && (!baseline || draft.objective !== baseline.objective || draft.success_criteria !== baseline.success_criteria));
}

export function mergeProjectDrafts(current: GoalDraftState, projects: GoalProject[]): GoalDraftState {
  const drafts = { ...current.drafts };
  const baselines = { ...current.baselines };
  for (const project of projects) {
    // Compare with the last fetched baseline, not with a newly changed server value.
    if (!draftChanged(drafts[project.id], baselines[project.id])) drafts[project.id] = toProjectDraft(project);
    baselines[project.id] = toProjectDraft(project);
  }
  return { drafts, baselines };
}

export function acceptSavedDraft(current: GoalDraftState, project: GoalProject, submittedDraft: ProjectDraft): GoalDraftState {
  const currentDraft = current.drafts[project.id];
  const saveCompletedBeforeFurtherEdit = !draftChanged(currentDraft, submittedDraft);
  return {
    drafts: { ...current.drafts, [project.id]: saveCompletedBeforeFurtherEdit ? toProjectDraft(project) : currentDraft },
    baselines: { ...current.baselines, [project.id]: toProjectDraft(project) }
  };
}
