ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS status_version BIGINT NOT NULL DEFAULT 0 CHECK (status_version >= 0);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_tasks_owner_project_id ON project_tasks(owner_id, project_id, id);

CREATE TABLE IF NOT EXISTS project_task_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL,
    task_id UUID NOT NULL,
    previous_status TEXT CHECK (previous_status IN ('planned', 'in_progress', 'done', 'on_hold')),
    next_status TEXT NOT NULL CHECK (next_status IN ('planned', 'in_progress', 'done', 'on_hold')),
    actor_owner_id TEXT CHECK (actor_owner_id IS NULL OR actor_owner_id = owner_id),
    source TEXT NOT NULL CHECK (source IN ('user', 'milestone_validation', 'system')),
    reason TEXT CHECK (reason IS NULL OR length(reason) <= 2000),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status_version BIGINT NOT NULL CHECK (status_version > 0),
    FOREIGN KEY (owner_id, project_id) REFERENCES projects(owner_id, id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id, project_id, task_id) REFERENCES project_tasks(owner_id, project_id, id) ON DELETE CASCADE,
    UNIQUE (owner_id, task_id, status_version)
);
CREATE INDEX IF NOT EXISTS idx_task_status_history_lookup
    ON project_task_status_history(owner_id, project_id, task_id, status_version DESC);

-- Existing completed tasks intentionally retain unknown completion dates.
CREATE OR REPLACE FUNCTION worktrace_stamp_task_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.status_version := 1;
        NEW.completed_at := CASE WHEN NEW.status = 'done' THEN clock_timestamp() ELSE NULL END;
    ELSE
        IF NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.project_id IS DISTINCT FROM OLD.project_id THEN
            RAISE EXCEPTION 'task ownership and project cannot change';
        END IF;
        IF NEW.status IS DISTINCT FROM OLD.status THEN
            NEW.status_version := OLD.status_version + 1;
            NEW.completed_at := CASE WHEN NEW.status = 'done' THEN clock_timestamp() ELSE NULL END;
        ELSE
            NEW.status_version := OLD.status_version;
            NEW.completed_at := OLD.completed_at;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION worktrace_record_task_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    actor TEXT := NULLIF(current_setting('worktrace.task_status_actor_owner_id', true), '');
    origin TEXT := current_setting('worktrace.task_status_source', true);
    explanation TEXT := NULLIF(btrim(current_setting('worktrace.task_status_reason', true)), '');
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;
    IF actor IS DISTINCT FROM NEW.owner_id OR origin IS NULL OR origin NOT IN ('user', 'milestone_validation') THEN
        actor := NULL;
        origin := 'system';
        explanation := NULL;
    END IF;
    INSERT INTO project_task_status_history (
        owner_id, project_id, task_id, previous_status, next_status,
        actor_owner_id, source, reason, changed_at, status_version
    ) VALUES (
        NEW.owner_id, NEW.project_id, NEW.id,
        CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.status END, NEW.status,
        actor, origin, explanation, COALESCE(NEW.completed_at, clock_timestamp()), NEW.status_version
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_task_transition_stamp ON project_tasks;
CREATE TRIGGER trg_task_transition_stamp BEFORE INSERT OR UPDATE ON project_tasks
FOR EACH ROW EXECUTE FUNCTION worktrace_stamp_task_transition();
DROP TRIGGER IF EXISTS trg_task_transition_record ON project_tasks;
CREATE TRIGGER trg_task_transition_record AFTER INSERT OR UPDATE ON project_tasks
FOR EACH ROW EXECUTE FUNCTION worktrace_record_task_transition();

CREATE OR REPLACE FUNCTION worktrace_guard_task_status_history()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND NOT EXISTS (
        SELECT 1 FROM project_tasks WHERE owner_id=OLD.owner_id AND project_id=OLD.project_id AND id=OLD.task_id
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'task status history is append-only';
END;
$$;
DROP TRIGGER IF EXISTS trg_task_history_immutable ON project_task_status_history;
CREATE TRIGGER trg_task_history_immutable BEFORE UPDATE OR DELETE ON project_task_status_history
FOR EACH ROW EXECUTE FUNCTION worktrace_guard_task_status_history();
