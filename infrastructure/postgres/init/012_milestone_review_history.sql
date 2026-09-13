CREATE TABLE IF NOT EXISTS project_milestone_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    milestone_id UUID NOT NULL REFERENCES project_milestones(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN ('ready_candidate', 'not_ready', 'needs_review')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reasoning_summary TEXT NOT NULL,
    missing_checks JSONB NOT NULL DEFAULT '[]'::jsonb,
    supporting_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    reviewed_wbs_total INTEGER NOT NULL DEFAULT 0 CHECK (reviewed_wbs_total >= 0),
    reviewed_wbs_completed INTEGER NOT NULL DEFAULT 0 CHECK (reviewed_wbs_completed >= 0),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    model TEXT NOT NULL DEFAULT '',
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_milestone_reviews_project_latest
    ON project_milestone_reviews (owner_id, project_id, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_milestone_reviews_milestone_latest
    ON project_milestone_reviews (owner_id, milestone_id, reviewed_at DESC);
