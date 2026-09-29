-- Preserve a request before it becomes a GitHub issue or an approved WBS item.
CREATE TABLE IF NOT EXISTS work_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL,
    request_id UUID NOT NULL,
    title TEXT NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 180),
    body TEXT NOT NULL DEFAULT '' CHECK (length(body) <= 10000),
    desired_outcome TEXT NOT NULL DEFAULT '' CHECK (length(desired_outcome) <= 2000),
    constraints TEXT NOT NULL DEFAULT '' CHECK (length(constraints) <= 2000),
    source TEXT NOT NULL CHECK (source IN ('chat', 'manual')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, request_id),
    FOREIGN KEY (owner_id, project_id) REFERENCES projects(owner_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_work_requests_owner_project_created
    ON work_requests (owner_id, project_id, created_at DESC, id DESC);
