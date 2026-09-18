CREATE UNIQUE INDEX IF NOT EXISTS uq_milestones_owner_project_id
    ON project_milestones(owner_id, project_id, id);

CREATE TABLE IF NOT EXISTS project_milestone_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL,
    milestone_id UUID NOT NULL,
    actor_owner_id TEXT NOT NULL CHECK (actor_owner_id = owner_id),
    status TEXT NOT NULL CHECK (status IN ('done', 'planned')),
    version BIGINT NOT NULL CHECK (version > 0),
    request_id UUID NOT NULL,
    request_snapshot JSONB NOT NULL CHECK (jsonb_typeof(request_snapshot) = 'object'),
    context_fingerprint TEXT NOT NULL CHECK (context_fingerprint ~ '^[a-f0-9]{64}$'),
    context_snapshot JSONB NOT NULL CHECK (jsonb_typeof(context_snapshot) = 'object'),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 2000),
    evidence_note TEXT NOT NULL DEFAULT '' CHECK (length(evidence_note) <= 8000),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status <> 'done' OR length(btrim(evidence_note)) > 0),
    FOREIGN KEY (owner_id, project_id, milestone_id)
        REFERENCES project_milestones(owner_id, project_id, id) ON DELETE CASCADE,
    UNIQUE (owner_id, milestone_id, version),
    UNIQUE (owner_id, milestone_id, request_id)
);

CREATE OR REPLACE FUNCTION worktrace_guard_milestone_confirmation_history()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND NOT EXISTS (
        SELECT 1 FROM project_milestones
        WHERE owner_id=OLD.owner_id AND project_id=OLD.project_id AND id=OLD.milestone_id
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'milestone confirmation history is append-only';
END;
$$;
DROP TRIGGER IF EXISTS trg_milestone_confirmation_immutable ON project_milestone_confirmations;
CREATE TRIGGER trg_milestone_confirmation_immutable BEFORE UPDATE OR DELETE ON project_milestone_confirmations
FOR EACH ROW EXECUTE FUNCTION worktrace_guard_milestone_confirmation_history();

-- Legacy synthetic checkpoints remain historical data, never a confirmation API.
CREATE OR REPLACE FUNCTION worktrace_guard_legacy_validation_status()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.source_provider='derived-github' AND OLD.source_key LIKE 'milestone-validation:%' THEN
        IF TG_OP='DELETE' AND NOT EXISTS (SELECT 1 FROM projects WHERE id=OLD.project_id) THEN
            RETURN OLD;
        END IF;
        -- Preserve ON DELETE SET NULL when the parent milestone is removed.
        IF TG_OP='UPDATE' AND OLD.milestone_id IS NOT NULL AND NEW.milestone_id IS NULL
           AND NOT EXISTS (SELECT 1 FROM project_milestones WHERE id=OLD.milestone_id)
           AND (to_jsonb(NEW) - 'milestone_id') = (to_jsonb(OLD) - 'milestone_id') THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'legacy validation record is read-only';
    END IF;
    IF TG_OP='DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_legacy_validation_status_read_only ON project_tasks;
CREATE TRIGGER trg_legacy_validation_status_read_only BEFORE UPDATE OR DELETE ON project_tasks
FOR EACH ROW EXECUTE FUNCTION worktrace_guard_legacy_validation_status();
