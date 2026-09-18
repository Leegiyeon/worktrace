from pathlib import Path
import stat
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_oracle.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"
PROGRESS_REPORT = REPO_ROOT / "backend" / "scripts" / "report_progress_snapshot.py"


def test_deploy_requires_exact_verified_sha() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "Usage: $0 <verified-commit-sha>" in script
    assert "^[0-9a-fA-F]{40}$" in script
    assert "git status --porcelain --untracked-files=normal" in script
    assert "Refusing to deploy from a dirty worktree" in script
    assert 'git checkout --detach "$DEPLOY_SHA"' in script
    assert 'git rev-parse HEAD' in script
    assert "git pull" not in script
    assert "git checkout main" not in script


def test_ci_bootstraps_tested_deploy_script_over_ssh_stdin() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'DEPLOY_SHA: ${{ github.sha }}' in workflow
    assert '"bash -s -- $DEPLOY_SHA" < scripts/deploy_oracle.sh' in workflow
    assert "bash scripts/deploy_oracle.sh" not in workflow
    assert "git pull --ff-only origin main" not in workflow


def test_deploy_uses_checksum_migration_runner() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "${POSTGRES_USER:-worktrace}" not in script
    assert "${POSTGRES_DB:-worktrace}" not in script
    assert "for migration in infrastructure/postgres/init/*.sql" not in script
    assert "psql" not in script
    assert 'up -d --wait db' in script
    assert 'run --rm --no-deps backend python scripts/migrate_db.py --preflight' in script
    assert 'exec -T backend python scripts/migrate_db.py' in script


def test_deploy_still_fails_closed_on_migration_errors() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    assert "scripts/migrate_db.py" in script
    assert "trap deployment_diagnostics ERR" in script


def test_deploy_canonicalizes_renamed_repository_origin() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "https://github.com/Leegiyeon/worktrace.git" in script
    assert "mv /home/ubuntu/work-support" in script
    assert 'git remote set-url origin "$REPOSITORY_URL"' in script
    assert 'git remote get-url origin' in script


def test_deploy_does_not_sync_or_cleanup_business_data() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "sync_github_data.py" not in script
    assert "--cleanup-samples" not in script


def test_deploy_reports_real_progress_without_business_data_sync() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    report = PROGRESS_REPORT.read_text(encoding="utf-8")

    assert "python scripts/report_progress_snapshot.py" in script
    assert "list_projects" in report
    assert "list_project_milestones" in report
    assert "derived_wbs=" in report
    assert "github_issue_wbs=" in report
    assert "source_key LIKE 'issue:%%'" in report
    assert "source_key LIKE 'issue:%'" not in report.replace("issue:%%", "")
    assert 'progress_text = _progress_provenance(project)' in report


def test_deploy_script_runs_with_mocked_commands_at_verified_sha(tmp_path: Path) -> None:
    deploy_sha = "0123456789abcdef0123456789abcdef01234567"
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / ".env.production").write_text("WORK_SUPPORT_PASSWORD_HASH=x\n", encoding="utf-8")
    log_file = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    def write_executable(name: str, body: str) -> None:
        path = fake_bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_executable(
        "git",
        f"""#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> {log_file}
if [[ "$1 $2" == "remote get-url" ]]; then echo https://github.com/Leegiyeon/worktrace.git; fi
if [[ "$1 $2" == "rev-parse HEAD" ]]; then echo {deploy_sha}; fi
""",
    )
    write_executable(
        "docker",
        f"""#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >> {log_file}
if [[ "$1" == "ps" ]]; then exit 0; fi
""",
    )
    write_executable("curl", f"#!/usr/bin/env bash\nprintf 'curl %s\\n' \"$*\" >> {log_file}\n")
    write_executable("sed", f"#!/usr/bin/env bash\nprintf 'sed %s\\n' \"$*\" >> {log_file}\n")
    write_executable("sleep", f"#!/usr/bin/env bash\nprintf 'sleep %s\\n' \"$*\" >> {log_file}\n")

    env = {"APP_DIR": str(app_dir), "PATH": f"{fake_bin}:/usr/bin:/bin"}

    result = subprocess.run(
        ["/bin/bash", str(DEPLOY_SCRIPT), deploy_sha],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    commands = log_file.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert f"git checkout --detach {deploy_sha}" in commands
    assert "git pull" not in commands
    assert "git checkout main" not in commands
    assert "docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.oracle.yml up -d --wait db" in commands
    assert "docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.oracle.yml run --rm --no-deps backend python scripts/migrate_db.py --preflight" in commands
    assert "docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.oracle.yml exec -T backend python scripts/migrate_db.py" in commands
    assert "sync_github_data.py" not in commands
    assert "--cleanup-samples" not in commands


def test_deploy_script_refuses_dirty_worktree_before_container_mutation(tmp_path: Path) -> None:
    deploy_sha = "0123456789abcdef0123456789abcdef01234567"
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / ".env.production").write_text("WORK_SUPPORT_PASSWORD_HASH=x\n", encoding="utf-8")
    log_file = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    def write_executable(name: str, body: str) -> None:
        path = fake_bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    write_executable(
        "git",
        f"""#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> {log_file}
if [[ "$1" == "status" ]]; then printf ' M scripts/deploy_oracle.sh\\n?? scratch.txt\\n'; fi
""",
    )
    write_executable(
        "docker",
        f"""#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >> {log_file}
exit 99
""",
    )
    write_executable("sed", f"#!/usr/bin/env bash\nprintf 'sed %s\\n' \"$*\" >> {log_file}\n")

    result = subprocess.run(
        ["/bin/bash", str(DEPLOY_SCRIPT), deploy_sha],
        env={"APP_DIR": str(app_dir), "PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    commands = log_file.read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "Refusing to deploy from a dirty worktree" in result.stderr
    assert " M scripts/deploy_oracle.sh" in result.stderr
    assert "?? scratch.txt" in result.stderr
    assert "git status --porcelain --untracked-files=normal" in commands
    assert "git checkout" not in commands
    assert "docker" not in commands
    assert "sed" not in commands
