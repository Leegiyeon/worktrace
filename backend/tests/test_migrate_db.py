from pathlib import Path

import pytest

from scripts.migrate_db import (
    assert_complete_existing_schema_baseline,
    checksum,
    migration_files,
    validate_migration_state,
)


def test_migration_files_are_ordered_and_ignore_non_sql(tmp_path: Path) -> None:
    (tmp_path / "010_last.sql").write_text("SELECT 10;", encoding="utf-8")
    (tmp_path / "002_first.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")

    assert [path.name for path in migration_files(tmp_path)] == ["002_first.sql", "010_last.sql"]


def test_checksum_changes_with_migration_content(tmp_path: Path) -> None:
    migration = tmp_path / "001_example.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    first = checksum(migration)
    migration.write_text("SELECT 2;", encoding="utf-8")

    assert checksum(migration) != first


class FakeScalarResult:
    def __init__(self, value: bool | list[tuple[str, str]]):
        self.value = value

    def fetchone(self) -> tuple[bool]:
        assert isinstance(self.value, bool)
        return (self.value,)

    def fetchall(self) -> list[tuple[str, str]]:
        assert isinstance(self.value, list)
        return self.value


class FakeConnection:
    def __init__(self, existing_tables: set[str], recorded: dict[str, str] | None = None):
        self.existing_tables = existing_tables
        self.recorded = recorded or {}

    def execute(self, query: str, params: tuple[str, ...] = ()) -> FakeScalarResult:
        if "to_regclass" not in query:
            if "SELECT version, checksum FROM schema_migrations" in query:
                return FakeScalarResult(list(self.recorded.items()))
            raise AssertionError(f"unexpected query: {query}")
        table_name = params[0].split(".", 1)[1]
        return FakeScalarResult(table_name in self.existing_tables)


def test_migration_guard_allows_fresh_database_without_baseline() -> None:
    assert_complete_existing_schema_baseline(FakeConnection(set()), {}, [])


def test_migration_guard_allows_complete_existing_schema_baseline(tmp_path: Path) -> None:
    migrations = write_legacy_baseline_migrations(tmp_path)

    assert_complete_existing_schema_baseline(
        FakeConnection({"projects", "project_tasks"}),
        {path.name: "checksum" for path in migrations},
        migrations,
    )


def test_migration_guard_refuses_existing_untracked_worktrace_schema(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no recorded migration baseline"):
        assert_complete_existing_schema_baseline(
            FakeConnection({"projects", "work_logs"}),
            {},
            write_legacy_baseline_migrations(tmp_path),
        )


def test_migration_guard_refuses_partial_existing_schema_baseline(tmp_path: Path) -> None:
    migrations = write_legacy_baseline_migrations(tmp_path)

    with pytest.raises(RuntimeError, match="incomplete recorded migration baseline"):
        assert_complete_existing_schema_baseline(
            FakeConnection({"projects", "work_logs"}),
            {"001_extensions.sql": "checksum"},
            migrations,
        )


def test_migration_preflight_refuses_changed_recorded_checksum(tmp_path: Path) -> None:
    migration = tmp_path / "001_example.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Applied migration changed"):
        validate_migration_state(
            FakeConnection({"schema_migrations"}, {"001_example.sql": "old"}),
            tmp_path,
        )


def test_migration_preflight_refuses_missing_recorded_file(tmp_path: Path) -> None:
    (tmp_path / "001_example.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing from filesystem"):
        validate_migration_state(
            FakeConnection({"schema_migrations"}, {"000_missing.sql": "old"}),
            tmp_path,
        )


def write_legacy_baseline_migrations(root: Path) -> list[Path]:
    names = [
        "001_extensions.sql",
        "002_work_support_schema.sql",
        "003_github_evidence.sql",
        "004_github_delivery_operations.sql",
        "005_worktrace_brand.sql",
        "006_github_managed_work.sql",
        "007_project_progress_goals.sql",
        "008_github_evidence_not_progress.sql",
        "009_project_milestones.sql",
        "010_commit_derived_wbs.sql",
        "011_worktrace_evidence_classification.sql",
        "012_milestone_review_history.sql",
        "013_milestone_review_staleness.sql",
    ]
    paths = [root / name for name in names]
    for path in paths:
        path.write_text("SELECT 1;", encoding="utf-8")
    return paths
