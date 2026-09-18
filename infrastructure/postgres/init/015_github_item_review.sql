ALTER TABLE github_items ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE github_items ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE github_items ADD COLUMN IF NOT EXISTS task_id UUID;
ALTER TABLE github_items ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE github_items ADD COLUMN IF NOT EXISTS decision_source_updated_at TIMESTAMPTZ;
ALTER TABLE github_items ADD COLUMN IF NOT EXISTS decision_source_digest TEXT;

CREATE OR REPLACE FUNCTION worktrace_bump_github_item_source_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.payload IS DISTINCT FROM NEW.payload
       OR OLD.source_updated_at IS DISTINCT FROM NEW.source_updated_at THEN
        NEW.version := OLD.version + 1;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bump_github_item_source_version ON github_items;
CREATE TRIGGER trg_bump_github_item_source_version
BEFORE UPDATE OF payload, source_updated_at ON github_items
FOR EACH ROW
EXECUTE FUNCTION worktrace_bump_github_item_source_version();

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_tasks_owner_id ON project_tasks(owner_id, id);

DO $$
BEGIN
    ALTER TABLE github_items DROP CONSTRAINT IF EXISTS github_items_task_id_fkey;
    ALTER TABLE github_items
        ADD CONSTRAINT github_items_owner_task_fk FOREIGN KEY (owner_id, task_id)
        REFERENCES project_tasks(owner_id, id) ON DELETE SET NULL (task_id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION worktrace_validate_github_item_task_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    source_project_id UUID;
    task_project_id UUID;
BEGIN
    IF NEW.task_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT project_id INTO source_project_id
    FROM repository_sources
    WHERE owner_id = NEW.owner_id AND id = NEW.repository_source_id;

    SELECT project_id INTO task_project_id
    FROM project_tasks
    WHERE owner_id = NEW.owner_id AND id = NEW.task_id;

    IF source_project_id IS NULL OR task_project_id IS NULL OR source_project_id <> task_project_id THEN
        RAISE foreign_key_violation USING MESSAGE = 'github item task must belong to the same owner and project';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validate_github_item_task_scope ON github_items;
CREATE TRIGGER trg_validate_github_item_task_scope
BEFORE INSERT OR UPDATE OF owner_id, repository_source_id, task_id ON github_items
FOR EACH ROW
EXECUTE FUNCTION worktrace_validate_github_item_task_scope();

CREATE OR REPLACE FUNCTION worktrace_prevent_linked_repository_project_move()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.project_id IS DISTINCT FROM NEW.project_id
       AND EXISTS (
           SELECT 1 FROM github_items gi
           WHERE gi.owner_id = OLD.owner_id
             AND gi.repository_source_id = OLD.id
             AND gi.task_id IS NOT NULL
       ) THEN
        RAISE foreign_key_violation USING MESSAGE = 'linked github item repository source cannot move projects';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_linked_repository_project_move ON repository_sources;
CREATE TRIGGER trg_prevent_linked_repository_project_move
BEFORE UPDATE OF project_id ON repository_sources
FOR EACH ROW
EXECUTE FUNCTION worktrace_prevent_linked_repository_project_move();

CREATE OR REPLACE FUNCTION worktrace_prevent_linked_task_project_move()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.project_id IS DISTINCT FROM NEW.project_id
       AND EXISTS (
           SELECT 1 FROM github_items gi
           WHERE gi.owner_id = OLD.owner_id
             AND gi.task_id = OLD.id
       ) THEN
        RAISE foreign_key_violation USING MESSAGE = 'linked github item task cannot move projects';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_linked_task_project_move ON project_tasks;
CREATE TRIGGER trg_prevent_linked_task_project_move
BEFORE UPDATE OF project_id ON project_tasks
FOR EACH ROW
EXECUTE FUNCTION worktrace_prevent_linked_task_project_move();

DO $$
BEGIN
    ALTER TABLE github_items
        ADD CONSTRAINT github_items_review_status_check CHECK (review_status IN ('pending', 'adopted', 'ignored'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE github_items
        ADD CONSTRAINT github_items_version_check CHECK (version >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_github_items_owner_review
    ON github_items (owner_id, review_status, source_updated_at DESC, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_github_items_owner_task
    ON github_items (owner_id, task_id) WHERE task_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS github_item_decision_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    github_item_id UUID NOT NULL,
    request_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'link', 'ignore', 'restore')),
    request_payload JSONB NOT NULL CHECK (jsonb_typeof(request_payload) = 'object'),
    source_payload JSONB NOT NULL CHECK (jsonb_typeof(source_payload) = 'object'),
    source_version INTEGER NOT NULL CHECK (source_version >= 0),
    source_updated_at TIMESTAMPTZ NOT NULL,
    previous_review_status TEXT NOT NULL,
    previous_task_id UUID,
    next_review_status TEXT NOT NULL,
    next_task_id UUID,
    actor_owner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_github_items_owner_id ON github_items(owner_id, id);

DO $$
BEGIN
    ALTER TABLE github_item_decision_audits
        ADD CONSTRAINT github_item_decision_audits_owner_item_fk FOREIGN KEY (owner_id, github_item_id)
        REFERENCES github_items(owner_id, id) ON DELETE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_github_item_decision_audits_item
    ON github_item_decision_audits (owner_id, github_item_id, created_at DESC);
