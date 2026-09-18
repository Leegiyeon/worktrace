CREATE OR REPLACE FUNCTION worktrace_project_plan_context(owner TEXT, project UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
    WITH scoped_project AS (
        SELECT p.id
        FROM projects p
        WHERE p.owner_id = owner AND p.id = project
    ),
    tasks AS (
        SELECT jsonb_agg(
                   jsonb_build_object(
                       'id', t.id::text,
                       'title', t.title,
                       'description', COALESCE(t.description, ''),
                       'milestone_id', t.milestone_id::text,
                       'counts_toward_progress', COALESCE(t.counts_toward_progress, true),
                       'source_provider', t.source_provider,
                       'source_key', t.source_key
                   )
                   ORDER BY t.id
               ) AS items
        FROM project_tasks t
        JOIN scoped_project p ON p.id = t.project_id
        WHERE t.owner_id = owner
          AND t.project_id = project
          AND NOT (
              COALESCE(t.source_provider, '') = 'derived-github'
              AND COALESCE(t.source_key, '') LIKE 'milestone-validation:%'
          )
    ),
    milestones AS (
        SELECT jsonb_agg(
                   jsonb_build_object(
                       'id', m.id::text,
                       'title', m.title,
                       'weight', m.weight
                   )
                   ORDER BY m.id
               ) AS items
        FROM project_milestones m
        JOIN scoped_project p ON p.id = m.project_id
        WHERE m.owner_id = owner
          AND m.project_id = project
    )
    SELECT jsonb_build_object(
        'tasks', COALESCE((SELECT items FROM tasks), '[]'::jsonb),
        'milestones', COALESCE((SELECT items FROM milestones), '[]'::jsonb)
    );
$$;

CREATE TABLE IF NOT EXISTS project_plan_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    policy TEXT NOT NULL CHECK (policy IN ('wbs', 'milestone')),
    context_fingerprint TEXT NOT NULL CHECK (context_fingerprint ~ '^[a-f0-9]{64}$'),
    context_snapshot JSONB NOT NULL CHECK (jsonb_typeof(context_snapshot) = 'object'),
    request_id UUID NOT NULL,
    request_snapshot JSONB NOT NULL CHECK (jsonb_typeof(request_snapshot) = 'object'),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 2000),
    exclusion_reason TEXT NOT NULL DEFAULT '' CHECK (length(exclusion_reason) <= 2000),
    reviewed_derived BOOLEAN NOT NULL DEFAULT false,
    approved_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    actor_owner_id TEXT NOT NULL CHECK (actor_owner_id = owner_id),
    FOREIGN KEY (owner_id, project_id) REFERENCES projects(owner_id, id) ON DELETE CASCADE,
    UNIQUE (owner_id, project_id, version),
    UNIQUE (owner_id, project_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_project_plan_approvals_latest
    ON project_plan_approvals (owner_id, project_id, version DESC);

CREATE OR REPLACE FUNCTION worktrace_guard_project_plan_approval_history()
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
    RAISE EXCEPTION 'project plan approval history is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_project_plan_approvals_append_only_update ON project_plan_approvals;
CREATE TRIGGER trg_project_plan_approvals_append_only_update
BEFORE UPDATE ON project_plan_approvals
FOR EACH ROW
EXECUTE FUNCTION worktrace_guard_project_plan_approval_history();

DROP TRIGGER IF EXISTS trg_project_plan_approvals_append_only_delete ON project_plan_approvals;
CREATE TRIGGER trg_project_plan_approvals_append_only_delete
BEFORE DELETE ON project_plan_approvals
FOR EACH ROW
EXECUTE FUNCTION worktrace_guard_project_plan_approval_history();
