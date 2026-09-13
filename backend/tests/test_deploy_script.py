from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_oracle.sh"
PROGRESS_REPORT = REPO_ROOT / "backend" / "scripts" / "report_progress_snapshot.py"


def test_deploy_migrations_use_database_container_credentials() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "${POSTGRES_USER:-worktrace}" not in script
    assert "${POSTGRES_DB:-worktrace}" not in script
    assert "exec -T db sh -c" in script
    assert 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in script


def test_deploy_still_fails_closed_on_migration_errors() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    assert "ON_ERROR_STOP=1" in script
    assert "trap deployment_diagnostics ERR" in script


def test_deploy_canonicalizes_renamed_repository_origin() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "https://github.com/Leegiyeon/worktrace.git" in script
    assert 'git remote set-url origin "$REPOSITORY_URL"' in script
    assert 'git remote get-url origin' in script


def test_deploy_reports_real_progress_after_github_sync() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    report = PROGRESS_REPORT.read_text(encoding="utf-8")

    assert "python scripts/sync_github_data.py --cleanup-samples" in script
    assert "python scripts/report_progress_snapshot.py" in script
    assert "list_projects" in report
    assert "list_project_milestones" in report
    assert "derived_wbs=" in report
    assert "github_issue_wbs=" in report
    assert 'progress_text = "산정 전" if project.progress_basis == "unscoped"' in report
