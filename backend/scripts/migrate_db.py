from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from urllib.parse import quote

import psycopg


DEFAULT_MIGRATIONS_DIR = Path("/app/infrastructure/postgres/init")
LOCK_ID = 928_441_017
TRACKING_TABLE = "schema_migrations"
LEGACY_EXISTING_SCHEMA_BASELINE_VERSION = "013_milestone_review_staleness.sql"
APP_TABLE_SENTINELS = (
    "projects",
    "project_tasks",
    "work_logs",
    "project_outcomes",
    "career_assets",
    "repository_sources",
    "github_commits",
    "project_milestones",
    "project_milestone_evidence",
)


def migration_files(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*.sql") if path.is_file())


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_exists(connection: psycopg.Connection, table_name: str) -> bool:
    return bool(
        connection.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table_name}",)).fetchone()[0]
    )


def app_schema_exists(connection: psycopg.Connection) -> bool:
    return any(table_exists(connection, table_name) for table_name in APP_TABLE_SENTINELS)


def recorded_migrations(connection: psycopg.Connection) -> dict[str, str]:
    if not table_exists(connection, TRACKING_TABLE):
        return {}
    return {
        row[0]: row[1]
        for row in connection.execute(f"SELECT version, checksum FROM {TRACKING_TABLE}").fetchall()
    }


def required_existing_schema_baseline_versions(migrations: list[Path]) -> list[str]:
    versions: list[str] = []
    for path in migrations:
        versions.append(path.name)
        if path.name == LEGACY_EXISTING_SCHEMA_BASELINE_VERSION:
            return versions
    raise RuntimeError(
        f"Required legacy baseline migration is missing from filesystem: {LEGACY_EXISTING_SCHEMA_BASELINE_VERSION}"
    )


def assert_complete_existing_schema_baseline(
    connection: psycopg.Connection,
    existing: dict[str, str],
    migrations: list[Path],
) -> None:
    if not app_schema_exists(connection):
        return
    if existing:
        required_versions = required_existing_schema_baseline_versions(migrations)
        missing_versions = [version for version in required_versions if version not in existing]
        if not missing_versions:
            return
        raise RuntimeError(
            "Existing Worktrace schema has an incomplete recorded migration baseline. Refusing to replay SQL. "
            f"Missing baseline migration(s): {', '.join(missing_versions)}. "
            "Verify a production backup/restore and audit schema_migrations before rerunning."
        )
    raise RuntimeError(
        "Existing Worktrace schema has no recorded migration baseline. Refusing to replay SQL. "
        "Verify a production backup/restore, audit the live schema against infrastructure/postgres/init, "
        "then create schema_migrations baseline rows for the already-applied SQL checksums before rerunning."
    )


def validate_migration_state(connection: psycopg.Connection, root: Path) -> dict[str, str]:
    migrations = migration_files(root)
    migration_checksums = {path.name: checksum(path) for path in migrations}
    existing = recorded_migrations(connection)
    assert_complete_existing_schema_baseline(connection, existing, migrations)
    for version, applied_checksum in existing.items():
        expected_checksum = migration_checksums.get(version)
        if expected_checksum is None:
            raise RuntimeError(f"Recorded migration is missing from filesystem: {version}")
        if applied_checksum != expected_checksum:
            raise RuntimeError(f"Applied migration changed: {version}")
    return existing


def apply_migrations(connection: psycopg.Connection, root: Path) -> list[str]:
    applied: list[str] = []
    migrations = migration_files(root)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        existing = validate_migration_state(connection, root)

        for path in migrations:
            version = path.name
            current_checksum = checksum(path)
            if version in existing:
                if existing[version] != current_checksum:
                    raise RuntimeError(f"Applied migration changed: {version}")
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                (version, current_checksum),
            )
            applied.append(version)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Worktrace SQL migrations with checksum tracking.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="validate migration tracking and checksums without applying pending SQL",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ.get("POSTGRES_HOST", "db")
        port = os.environ.get("POSTGRES_PORT", "5432")
        database = os.environ["POSTGRES_DB"]
        database_url = (
            f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
            f"{host}:{port}/{quote(database, safe='')}"
        )

    root = Path(os.environ.get("MIGRATIONS_DIR", DEFAULT_MIGRATIONS_DIR))
    files = migration_files(root)
    if not files:
        raise RuntimeError(f"No migration files found in {root}")

    with psycopg.connect(database_url) as connection:
        if args.preflight:
            existing = validate_migration_state(connection, root)
            print(f"Migration preflight passed: {len(existing)} recorded migration(s)")
            return
        applied = apply_migrations(connection, root)
    print("Migrations applied: " + (", ".join(applied) if applied else "none"))


if __name__ == "__main__":
    main()
