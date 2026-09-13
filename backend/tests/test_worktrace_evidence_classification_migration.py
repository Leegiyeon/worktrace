from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "infrastructure" / "postgres" / "init" / "011_worktrace_evidence_classification.sql"


def migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_project_insight_is_more_specific_than_project_wbs() -> None:
    sql = migration_text()

    assert "project[ _-]?(analyst|insight)" in sql
    assert "RETURN 'project-insight'" in sql
    assert sql.index("RETURN 'project-insight'") < sql.index("RETURN 'project-wbs'")
    assert "project|프로젝트" not in sql


def test_generic_evidence_word_does_not_force_github_milestone() -> None:
    sql = migration_text()
    github_rule = sql.split("RETURN 'github-evidence'", 1)[0].rsplit("IF normalized ~", 1)[-1]

    assert "github" in github_rule
    assert "webhook" in github_rule
    assert "|evidence|" not in github_rule
    assert "|근거|" not in github_rule


def test_historical_evidence_is_reclassified_and_wbs_refreshed() -> None:
    sql = migration_text()

    assert "DELETE FROM project_milestone_evidence" in sql
    assert "INSERT INTO project_milestone_evidence" in sql
    assert "worktrace_infer_worktrace_milestone_key(c.message)" in sql
    assert "worktrace_refresh_commit_derived_wbs" in sql
    assert "BEFORE INSERT OR UPDATE ON project_milestone_evidence" in sql
