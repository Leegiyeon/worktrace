from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_local.sh"
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "restore_local.sh"


def read_script(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_local_backup_restore_scripts_are_shell_syntax_valid() -> None:
    for script in (BACKUP_SCRIPT, RESTORE_SCRIPT):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_local_backup_restore_scripts_are_executable() -> None:
    for script in (BACKUP_SCRIPT, RESTORE_SCRIPT):
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR


def test_backup_script_uses_compose_db_and_owner_only_permissions() -> None:
    script = read_script(BACKUP_SCRIPT)

    assert 'COMPOSE_SERVICE="${COMPOSE_DB_SERVICE:-db}"' in script
    assert "docker compose exec -T" in script
    assert "pg_dump" in script
    assert "--format=custom" in script
    assert "--no-owner" in script
    assert "--no-privileges" in script
    assert "umask 077" in script
    assert "chmod 700" in script
    assert "chmod 600" in script
    assert "chmod 700 --" not in script
    assert "chmod 600 --" not in script
    assert 'container_id="$(docker compose ps -q' in script
    assert "pg_restore --list" in script
    assert "POSTGRES_PASSWORD" not in script


def test_restore_script_requires_confirm_and_validates_input_before_restore() -> None:
    script = read_script(RESTORE_SCRIPT)

    confirm_index = script.index('if [[ "${confirm}" != "true"')
    regular_file_index = script.index('if [[ ! -f "${backup_file}" ]]')
    readable_index = script.index('if [[ ! -r "${backup_file}" ]]')
    non_empty_index = script.index('if [[ ! -s "${backup_file}" ]]')
    restore_index = script.index("pg_restore \\\n    --clean")

    assert confirm_index < regular_file_index < readable_index < non_empty_index < restore_index
    assert "docker compose exec -T" in script
    assert 'container_id="$(docker compose ps -q' in script
    assert "pg_restore --list" in script
    assert "--clean" in script
    assert "--exit-on-error" in script
    assert "--if-exists" in script
    assert "POSTGRES_PASSWORD" not in script


def test_restore_without_confirm_exits_before_docker_or_database_access() -> None:
    result = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), "/tmp/nonexistent.dump"],
        check=False,
        env={**os.environ, "PATH": os.environ["PATH"]},
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Restore requires: --confirm BACKUP_FILE" in result.stderr
    assert "db service is not available" not in result.stderr
