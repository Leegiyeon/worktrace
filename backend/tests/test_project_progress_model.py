from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GOALS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "007_project_progress_goals.sql"
EVIDENCE_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "008_github_evidence_not_progress.sql"
COMMIT_WBS_SCHEMA = REPO_ROOT / "infrastructure" / "postgres" / "init" / "010_commit_derived_wbs.sql"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_oracle.sh"
PROJECT_SERVICE = REPO_ROOT / "backend" / "app" / "services" / "projects.py"


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


def test_commit_evidence_synthesizes_wbs_only_without_real_issues() -> None:
    schema = COMMIT_WBS_SCHEMA.read_text(encoding="utf-8")

    assert "source_key LIKE 'issue:%'" in schema
    assert "source_provider = 'derived-github'" in schema
    assert "'commit-milestone:' || m.id::text" in schema
    assert "'milestone-validation:' || m.id::text" in schema
    assert "'[커밋 근거] ' || m.title || ' 구현'" in schema
    assert "'[검증 필요] ' || m.title || ' 성취 기준 확인'" in schema
    assert "status = 'done'" in schema
    assert "worktrace_refresh_commit_derived_wbs" in schema
    assert "trg_refresh_commit_derived_wbs_evidence" in schema
    assert "trg_refresh_commit_derived_wbs_issue" in schema


def test_deploy_uses_checksum_runner_without_raw_sql_replay() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "for migration in infrastructure/postgres/init/*.sql" not in script
    assert "psql" not in script
    assert "up -d --wait db" in script
    assert "python scripts/migrate_db.py --preflight" in script
    assert "exec -T backend python scripts/migrate_db.py" in script
    assert "sync_github_data.py" not in script
    assert "--cleanup-samples" not in script


def test_milestone_progress_requires_complete_wbs_coverage() -> None:
    service = PROJECT_SERVICE.read_text(encoding="utf-8")

    assert "COALESCE(ms.scoped_task_count, 0) = COALESCE(ts.total_tasks, 0)" in service
    assert "WHEN COALESCE(ts.total_tasks, 0) > 0 THEN 'wbs'" in service
    assert "ELSE 'unscoped' END AS progress_basis" in service
    assert "COALESCE(SUM(mt.task_count), 0)::int AS scoped_task_count" in service
