from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GOALS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "007_project_progress_goals.sql"
EVIDENCE_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "008_github_evidence_not_progress.sql"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_oracle.sh"


def test_project_goals_and_progress_flag_are_migrated() -> None:
    schema = GOALS_SCHEMA.read_text(encoding="utf-8")

    assert "objective TEXT NOT NULL DEFAULT ''" in schema
    assert "success_criteria TEXT NOT NULL DEFAULT ''" in schema
    assert "counts_toward_progress BOOLEAN NOT NULL DEFAULT true" in schema
    assert "lower(title) = 'oncc'" in schema
    assert "lower(title) IN ('emanual', 'e-manual')" in schema
    assert "lower(title) = 'worktrace'" in schema


def test_github_commit_and_pr_evidence_are_not_wbs_tasks() -> None:
    schema = EVIDENCE_SCHEMA.read_text(encoding="utf-8")

    assert "DELETE FROM project_tasks" in schema
    assert "source_key LIKE 'commit:%'" in schema
    assert "source_key LIKE 'pr:%'" in schema
    assert "RETURN NULL" in schema
    assert "trg_skip_github_evidence_task" in schema


def test_deploy_reapplies_idempotent_migrations_to_existing_volume() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "for migration in infrastructure/postgres/init/*.sql" in script
    assert "psql" in script
    assert "ON_ERROR_STOP=1" in script
