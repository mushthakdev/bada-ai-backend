"""Lightweight additive schema patches for local SQLite (create_all does not ALTER)."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# table -> list of (column_name, sqlite_type_sql)
_SQLITE_ADDITIVE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "campaigns": [
        ("media_plan_json", "TEXT"),
        ("is_omnichannel", "BOOLEAN DEFAULT 0 NOT NULL"),
        ("is_simulated_delivery", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("launch_summary_json", "TEXT"),
    ],
}


def ensure_sqlite_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _SQLITE_ADDITIVE_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, col_type in columns:
                if name in existing:
                    continue
                ddl = f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"
                logger.info("SQLite schema patch: %s", ddl)
                conn.execute(text(ddl))
            # Refresh inspector cache for subsequent tables if needed
            inspector = inspect(engine)
