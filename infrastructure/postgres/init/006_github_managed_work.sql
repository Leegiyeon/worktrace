ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS source_provider TEXT, ADD COLUMN IF NOT EXISTS source_key TEXT;
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS source_provider TEXT, ADD COLUMN IF NOT EXISTS source_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_tasks_owner_source ON project_tasks (owner_id, source_provider, source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_logs_owner_source ON work_logs (owner_id, source_provider, source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL;
