ALTER TABLE project_milestone_reviews
    ADD COLUMN IF NOT EXISTS context_fingerprint TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_project_milestone_reviews_current_context
    ON project_milestone_reviews (owner_id, project_id, milestone_id, reviewed_at DESC, context_fingerprint);
