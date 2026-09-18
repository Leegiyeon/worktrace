-- Preserve existing user work. New evidence must not synthesize or delete WBS.
DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_evidence ON project_milestone_evidence;
DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_issue ON project_tasks;

-- Retain the legacy function signature for callers without mutating business data.
CREATE OR REPLACE FUNCTION worktrace_refresh_commit_derived_wbs(p_owner_id TEXT, p_project_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_repository_sources_owner_id ON repository_sources(owner_id, id);

-- GitHub's external state is independent of locally edited task status and content.
CREATE TABLE IF NOT EXISTS github_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    repository_source_id UUID NOT NULL,
    external_id BIGINT NOT NULL,
    number INTEGER NOT NULL CHECK (number > 0),
    kind TEXT NOT NULL CHECK (kind IN ('issue', 'pr')),
    source_updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (owner_id, repository_source_id)
        REFERENCES repository_sources(owner_id, id) ON DELETE CASCADE,
    UNIQUE (owner_id, repository_source_id, number)
);
