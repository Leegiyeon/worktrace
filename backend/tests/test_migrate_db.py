from pathlib import Path

from scripts.migrate_db import checksum, migration_files


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
