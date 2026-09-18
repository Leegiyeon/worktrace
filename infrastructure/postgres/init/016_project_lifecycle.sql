ALTER TABLE projects ADD COLUMN IF NOT EXISTS service_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS lifecycle_version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS development_ended_on DATE;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS lifecycle_confirmed_at TIMESTAMPTZ;

DO $$
BEGIN
    ALTER TABLE projects
        ADD CONSTRAINT projects_service_status_check CHECK (service_status IN ('unknown', 'not_released', 'operating', 'retired'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE projects
        ADD CONSTRAINT projects_lifecycle_version_check CHECK (lifecycle_version >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE projects
        ADD CONSTRAINT projects_owner_id_unique UNIQUE (owner_id, id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS project_lifecycle_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL,
    actor_owner_id TEXT NOT NULL,
    request_id UUID NOT NULL,
    request_snapshot JSONB NOT NULL CHECK (jsonb_typeof(request_snapshot) = 'object'),
    previous_status TEXT NOT NULL CHECK (previous_status IN ('idea', 'review', 'in_progress', 'on_hold', 'done')),
    next_status TEXT NOT NULL CHECK (next_status IN ('idea', 'review', 'in_progress', 'on_hold', 'done')),
    previous_service_status TEXT NOT NULL CHECK (previous_service_status IN ('unknown', 'not_released', 'operating', 'retired')),
    next_service_status TEXT NOT NULL CHECK (next_service_status IN ('unknown', 'not_released', 'operating', 'retired')),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0 AND length(reason) <= 2000),
    incomplete_reason TEXT CHECK (incomplete_reason IS NULL OR (length(btrim(incomplete_reason)) > 0 AND length(incomplete_reason) <= 2000)),
    development_ended_on DATE,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (owner_id, project_id) REFERENCES projects(owner_id, id) ON DELETE CASCADE,
    UNIQUE (owner_id, project_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_project_lifecycle_history_project_confirmed
    ON project_lifecycle_history (owner_id, project_id, confirmed_at DESC);

CREATE OR REPLACE FUNCTION worktrace_guard_project_lifecycle_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND NOT EXISTS (
           SELECT 1 FROM projects p
           WHERE p.owner_id = OLD.owner_id AND p.id = OLD.project_id
       ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'project lifecycle history is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_project_lifecycle_history_append_only_update ON project_lifecycle_history;
CREATE TRIGGER trg_project_lifecycle_history_append_only_update
BEFORE UPDATE ON project_lifecycle_history
FOR EACH ROW
EXECUTE FUNCTION worktrace_guard_project_lifecycle_history_mutation();

DROP TRIGGER IF EXISTS trg_project_lifecycle_history_append_only_delete ON project_lifecycle_history;
CREATE TRIGGER trg_project_lifecycle_history_append_only_delete
BEFORE DELETE ON project_lifecycle_history
FOR EACH ROW
EXECUTE FUNCTION worktrace_guard_project_lifecycle_history_mutation();
