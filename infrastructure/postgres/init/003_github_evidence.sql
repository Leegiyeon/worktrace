CREATE TABLE IF NOT EXISTS repository_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    provider TEXT NOT NULL DEFAULT 'github' CHECK (provider IN ('github')),
    repository_id BIGINT NOT NULL,
    full_name TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, provider, repository_id),
    UNIQUE (owner_id, provider, full_name)
);

CREATE TABLE IF NOT EXISTS github_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    delivery_id TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    repository_id BIGINT,
    repository_full_name TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('processed', 'ignored', 'failed')),
    reason TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS github_commits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_source_id UUID NOT NULL REFERENCES repository_sources(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    sha TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    author_name TEXT NOT NULL DEFAULT '',
    author_email TEXT NOT NULL DEFAULT '',
    committed_at TIMESTAMPTZ,
    url TEXT NOT NULL DEFAULT '',
    added_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    modified_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    removed_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, repository_source_id, sha)
);

CREATE INDEX IF NOT EXISTS idx_repository_sources_owner_project ON repository_sources (owner_id, project_id);
CREATE INDEX IF NOT EXISTS idx_github_deliveries_owner_received ON github_deliveries (owner_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_github_commits_owner_project_date ON github_commits (owner_id, project_id, committed_at DESC);
