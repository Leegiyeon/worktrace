from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import quote

import psycopg


DEFAULT_MIGRATIONS_DIR = Path("/app/infrastructure/postgres/init")
LOCK_ID = 928_441_017


def migration_files(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*.sql") if path.is_file())


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_migrations(connection: psycopg.Connection, root: Path) -> list[str]:
    applied: list[str] = []
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
        existing = {
            row[0]: row[1]
            for row in connection.execute("SELECT version, checksum FROM schema_migrations").fetchall()
        }

        for path in migration_files(root):
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
        applied = apply_migrations(connection, root)
    print("Migrations applied: " + (", ".join(applied) if applied else "none"))


if __name__ == "__main__":
    main()
