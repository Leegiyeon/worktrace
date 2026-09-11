from pathlib import Path

from app.core.config import Settings
from app.db.schema import load_schema_sql, resolve_schema_sql_path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "002_work_support_schema.sql"


def test_schema_loader_reads_canonical_sql_file() -> None:
    settings = Settings(work_support_schema_sql_path=str(CANONICAL_SCHEMA))

    assert resolve_schema_sql_path(settings) == CANONICAL_SCHEMA
    assert load_schema_sql(settings) == CANONICAL_SCHEMA.read_text(encoding="utf-8")


def test_schema_module_does_not_embed_table_ddl() -> None:
    schema_source = (REPO_ROOT / "backend" / "app" / "db" / "schema.py").read_text(encoding="utf-8")

    assert "SCHEMA_SQL =" not in schema_source
    assert "CREATE TABLE IF NOT EXISTS projects" not in schema_source


def test_backend_compose_mounts_canonical_sql_for_container_init() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./infrastructure/postgres/init:/app/infrastructure/postgres/init:ro" in compose


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
    schema = CANONICAL_SCHEMA.read_text(encoding="utf-8")

    for table in ["repository_sources", "github_deliveries", "github_commits"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "delivery_id TEXT NOT NULL UNIQUE" in schema
    assert "UNIQUE (owner_id, repository_source_id, sha)" in schema
