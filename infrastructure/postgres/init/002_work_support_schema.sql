CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idea' CHECK (status IN ('idea', 'review', 'in_progress', 'on_hold', 'done')),
    role TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    storage_path TEXT NOT NULL DEFAULT '',
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    extracted_text TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT '',
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    upload_status TEXT NOT NULL DEFAULT 'metadata_only',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    extraction_error TEXT NOT NULL DEFAULT '',
    analysis_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    item_type TEXT NOT NULL CHECK (item_type IN ('task', 'decision', 'risk', 'career_candidate', 'next_check')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    due_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'done', 'on_hold')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    due_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    log_date DATE NOT NULL,
    work_type TEXT NOT NULL DEFAULT 'other' CHECK (work_type IN ('planning', 'meeting', 'research', 'deliverable', 'development', 'testing', 'reporting', 'coordination', 'problem_solving', 'other')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    decisions TEXT NOT NULL DEFAULT '',
    collaborators TEXT NOT NULL DEFAULT '',
    next_actions TEXT NOT NULL DEFAULT '',
    duration_minutes INTEGER NOT NULL DEFAULT 0 CHECK (duration_minutes >= 0),
    blockers TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    title TEXT NOT NULL,
    outcome_type TEXT NOT NULL DEFAULT 'qualitative' CHECK (outcome_type IN ('quantitative', 'qualitative')),
    before_state TEXT NOT NULL DEFAULT '',
    after_state TEXT NOT NULL DEFAULT '',
    metric_name TEXT NOT NULL DEFAULT '',
    metric_value NUMERIC(18, 4),
    metric_unit TEXT NOT NULL DEFAULT '',
    evidence_work_log_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[],
    evidence_document_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[],
    resume_ready BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (outcome_type = 'qualitative' OR metric_value IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS career_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL DEFAULT 'local-owner',
    source_summary TEXT NOT NULL DEFAULT '',
    work_summary TEXT NOT NULL DEFAULT '',
    outcome_summary TEXT NOT NULL DEFAULT '',
    resume_bullets TEXT NOT NULL DEFAULT '',
    career_description TEXT NOT NULL DEFAULT '',
    portfolio_description TEXT NOT NULL DEFAULT '',
    star_answer TEXT NOT NULL DEFAULT '',
    markdown TEXT NOT NULL DEFAULT '',
    generation_method TEXT NOT NULL DEFAULT 'template',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE extracted_items ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS work_type TEXT NOT NULL DEFAULT 'other';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS decisions TEXT NOT NULL DEFAULT '';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS collaborators TEXT NOT NULL DEFAULT '';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS next_actions TEXT NOT NULL DEFAULT '';
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS duration_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS due_date DATE;
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS outcome_type TEXT NOT NULL DEFAULT 'qualitative';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS before_state TEXT NOT NULL DEFAULT '';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS after_state TEXT NOT NULL DEFAULT '';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS metric_name TEXT NOT NULL DEFAULT '';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS metric_value NUMERIC(18, 4);
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS metric_unit TEXT NOT NULL DEFAULT '';
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS evidence_work_log_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[];
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS evidence_document_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[];
ALTER TABLE project_outcomes ADD COLUMN IF NOT EXISTS resume_ready BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-owner';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS source_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS work_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS outcome_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS resume_bullets TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS career_description TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS portfolio_description TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS star_answer TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS markdown TEXT NOT NULL DEFAULT '';
ALTER TABLE career_assets ADD COLUMN IF NOT EXISTS generation_method TEXT NOT NULL DEFAULT 'template';

DO $$
BEGIN
    ALTER TABLE project_tasks
        ADD CONSTRAINT project_tasks_priority_check CHECK (priority IN ('low', 'medium', 'high'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE project_outcomes
        ADD CONSTRAINT project_outcomes_outcome_type_check CHECK (outcome_type IN ('quantitative', 'qualitative'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE project_outcomes
        ADD CONSTRAINT project_outcomes_quantitative_metric_check CHECK (outcome_type = 'qualitative' OR metric_value IS NOT NULL);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE work_logs
        ADD CONSTRAINT work_logs_work_type_check CHECK (work_type IN ('planning', 'meeting', 'research', 'deliverable', 'development', 'testing', 'reporting', 'coordination', 'problem_solving', 'other'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE work_logs
        ADD CONSTRAINT work_logs_duration_minutes_check CHECK (duration_minutes >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_projects_owner_updated ON projects (owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects (status);
CREATE INDEX IF NOT EXISTS idx_documents_owner_updated ON documents (owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents (project_id);
CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_analysis_status ON documents (analysis_status);
CREATE INDEX IF NOT EXISTS idx_extracted_items_owner_updated ON extracted_items (owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_extracted_items_project_id ON extracted_items (project_id);
CREATE INDEX IF NOT EXISTS idx_extracted_items_document_id ON extracted_items (document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_items_type ON extracted_items (item_type);
CREATE INDEX IF NOT EXISTS idx_extracted_items_updated_at ON extracted_items (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_tasks_owner_status ON project_tasks (owner_id, status);
CREATE INDEX IF NOT EXISTS idx_project_tasks_project_id ON project_tasks (project_id);
CREATE INDEX IF NOT EXISTS idx_project_tasks_updated_at ON project_tasks (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_tasks_owner_priority ON project_tasks (owner_id, priority);
CREATE INDEX IF NOT EXISTS idx_project_tasks_owner_due_date ON project_tasks (owner_id, due_date);

CREATE INDEX IF NOT EXISTS idx_work_logs_owner_date ON work_logs (owner_id, log_date DESC);
CREATE INDEX IF NOT EXISTS idx_work_logs_project_id ON work_logs (project_id);
CREATE INDEX IF NOT EXISTS idx_work_logs_updated_at ON work_logs (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_logs_owner_project_date ON work_logs (owner_id, project_id, log_date DESC);
CREATE INDEX IF NOT EXISTS idx_work_logs_owner_work_type ON work_logs (owner_id, work_type);

CREATE INDEX IF NOT EXISTS idx_project_outcomes_owner_project_updated ON project_outcomes (owner_id, project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_outcomes_owner_type ON project_outcomes (owner_id, outcome_type);
CREATE INDEX IF NOT EXISTS idx_project_outcomes_resume_ready ON project_outcomes (owner_id, resume_ready);
CREATE INDEX IF NOT EXISTS idx_career_assets_owner_project_updated ON career_assets (owner_id, project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_career_assets_generation_method ON career_assets (owner_id, generation_method);
