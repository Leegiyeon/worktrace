from pathlib import Path

from app.core.config import Settings
from app.db.schema import load_schema_sql, resolve_schema_sql_path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "002_work_support_schema.sql"
GITHUB_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "003_github_evidence.sql"
GITHUB_OPERATIONS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "004_github_delivery_operations.sql"
WORKTRACE_BRAND_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "005_worktrace_brand.sql"
GITHUB_MANAGED_WORK_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "006_github_managed_work.sql"
PROJECT_GOALS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "007_project_progress_goals.sql"
GITHUB_EVIDENCE_PROGRESS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "008_github_evidence_not_progress.sql"
PROJECT_MILESTONE_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "009_project_milestones.sql"
PROJECT_LIFECYCLE_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "016_project_lifecycle.sql"


def test_schema_loader_reads_canonical_sql_file() -> None:
    settings = Settings(work_support_schema_sql_path=str(CANONICAL_SCHEMA))

    assert resolve_schema_sql_path(settings) == CANONICAL_SCHEMA
    assert load_schema_sql(settings) == CANONICAL_SCHEMA.read_text(encoding="utf-8")


def test_schema_module_does_not_embed_table_ddl() -> None:
    schema_source = (REPO_ROOT / "backend" / "app" / "db" / "schema.py").read_text(encoding="utf-8")

    assert "SCHEMA_SQL =" not in schema_source
    assert "CREATE TABLE IF NOT EXISTS projects" not in schema_source


def test_backend_compose_mounts_canonical_sql_for_runner_only() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./infrastructure/postgres/init:/app/infrastructure/postgres/init:ro" in compose
    assert "/docker-entrypoint-initdb.d" not in compose
    assert "python scripts/migrate_db.py && exec uvicorn" in compose


def test_canonical_schema_contains_project_tasks() -> None:
    schema = CANONICAL_SCHEMA.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS project_tasks" in schema
    assert "status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'done', 'on_hold'))" in schema
    assert "priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high'))" in schema
    assert "due_date DATE" in schema
    assert "idx_project_tasks_project_id" in schema
    assert "idx_project_tasks_owner_due_date" in schema


def test_canonical_schema_contains_project_outcomes() -> None:
    schema = CANONICAL_SCHEMA.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS project_outcomes" in schema
    assert "outcome_type TEXT NOT NULL DEFAULT 'qualitative' CHECK (outcome_type IN ('quantitative', 'qualitative'))" in schema
    assert "metric_value NUMERIC(18, 4)" in schema
    assert "evidence_work_log_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[]" in schema
    assert "evidence_document_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[]" in schema
    assert "resume_ready BOOLEAN NOT NULL DEFAULT false" in schema
    assert "idx_project_outcomes_owner_project_updated" in schema


def test_canonical_schema_contains_career_assets() -> None:
    schema = CANONICAL_SCHEMA.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS career_assets" in schema
    assert "source_summary TEXT NOT NULL DEFAULT ''" in schema
    assert "resume_bullets TEXT NOT NULL DEFAULT ''" in schema
    assert "portfolio_description TEXT NOT NULL DEFAULT ''" in schema
    assert "star_answer TEXT NOT NULL DEFAULT ''" in schema
    assert "generation_method TEXT NOT NULL DEFAULT 'template'" in schema
    assert "idx_career_assets_owner_project_updated" in schema


def test_canonical_schema_contains_github_evidence_tables() -> None:
    schema = GITHUB_SCHEMA.read_text(encoding="utf-8")

    for table in ["repository_sources", "github_deliveries", "github_commits"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "delivery_id TEXT NOT NULL UNIQUE" in schema
    assert "UNIQUE (owner_id, repository_source_id, sha)" in schema


def test_github_delivery_operations_track_reprocessing() -> None:
    schema = GITHUB_OPERATIONS_SCHEMA.read_text(encoding="utf-8")

    assert "processing_attempts INTEGER NOT NULL DEFAULT 1" in schema
    assert "last_processed_at TIMESTAMPTZ NOT NULL DEFAULT now()" in schema
    assert "idx_github_deliveries_repository_received" in schema


def test_worktrace_brand_migration_updates_project_and_repository() -> None:
    schema = WORKTRACE_BRAND_SCHEMA.read_text(encoding="utf-8")

    assert "SET title = 'worktrace'" in schema
    assert "SET full_name = 'Leegiyeon/worktrace'" in schema
    assert "lower(title) = 'work-support'" in schema


def test_github_managed_work_has_idempotent_source_keys() -> None:
    schema = GITHUB_MANAGED_WORK_SCHEMA.read_text(encoding="utf-8")

    assert "ALTER TABLE project_tasks" in schema
    assert "ALTER TABLE work_logs" in schema
    assert "source_provider TEXT" in schema
    assert "source_key TEXT" in schema
    assert "uq_project_tasks_owner_source" in schema
    assert "uq_work_logs_owner_source" in schema


def test_project_goal_migration_separates_progress_evidence() -> None:
    goals = PROJECT_GOALS_SCHEMA.read_text(encoding="utf-8")
    evidence = GITHUB_EVIDENCE_PROGRESS_SCHEMA.read_text(encoding="utf-8")

    assert "objective TEXT" in goals
    assert "success_criteria TEXT" in goals
    assert "counts_toward_progress BOOLEAN" in goals
    assert "DELETE FROM project_tasks" in evidence
    assert "source_key LIKE 'commit:%'" in evidence
    assert "source_key LIKE 'pr:%'" in evidence


def test_project_milestone_migration_has_weighted_progress_structure() -> None:
    schema = PROJECT_MILESTONE_SCHEMA.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS project_milestones" in schema
    assert "weight INTEGER NOT NULL CHECK (weight > 0 AND weight <= 100)" in schema
    assert "acceptance_criteria TEXT NOT NULL DEFAULT ''" in schema
    assert "ADD COLUMN IF NOT EXISTS milestone_id UUID" in schema
    assert "ON DELETE SET NULL" in schema
    assert "핵심 업무 전산화" in schema
    assert "Retrieval 품질" in schema
    assert "Career AI" in schema


def test_project_lifecycle_migration_separates_development_and_service_state() -> None:
    schema = PROJECT_LIFECYCLE_SCHEMA.read_text(encoding="utf-8")

    assert "service_status TEXT NOT NULL DEFAULT 'unknown'" in schema
    assert "lifecycle_version BIGINT NOT NULL DEFAULT 0" in schema
    assert "development_ended_on DATE" in schema
    assert "lifecycle_confirmed_at TIMESTAMPTZ" in schema
    assert "CREATE TABLE IF NOT EXISTS project_lifecycle_history" in schema
    assert "FOREIGN KEY (owner_id, project_id) REFERENCES projects(owner_id, id)" in schema
    assert "request_snapshot JSONB NOT NULL" in schema
    assert "confirmed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()" in schema
    assert "UNIQUE (owner_id, project_id, request_id)" in schema
    assert "worktrace_guard_project_lifecycle_history_mutation" in schema
    assert "NOT EXISTS" in schema
    assert "BEFORE UPDATE ON project_lifecycle_history" in schema
    assert "BEFORE DELETE ON project_lifecycle_history" in schema
