ALTER TABLE github_deliveries
    ADD COLUMN IF NOT EXISTS processing_attempts INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS last_processed_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_github_deliveries_repository_received
    ON github_deliveries (owner_id, repository_id, received_at DESC);
