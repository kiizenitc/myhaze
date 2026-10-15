"""Apply supabase/migrations/*.sql in name order, each exactly once."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from .config import REPO_ROOT, load_settings

MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    conn.execute("create table if not exists schema_migrations "
                 "(name text primary key, applied_at timestamptz not null default now())")
    conn.execute("alter table schema_migrations enable row level security")
    done = {row[0] for row in conn.execute("select name from schema_migrations").fetchall()}
    applied = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
        applied.append(path.name)
    return applied


def main() -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(settings.db_url, autocommit=True, prepare_threshold=None) as conn:
        applied = apply_migrations(conn)
    print("applied:", ", ".join(applied) if applied else "nothing new")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
