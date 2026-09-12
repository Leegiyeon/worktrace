from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_oracle.sh"


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
