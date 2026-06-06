from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings


def connect(settings: Settings, *, row_factory: Any | None = dict_row) -> psycopg.Connection:
    """Create a psycopg connection using the app's configured database URL."""

    if row_factory is None:
        return psycopg.connect(settings.resolved_database_url)
    return psycopg.connect(settings.resolved_database_url, row_factory=row_factory)
