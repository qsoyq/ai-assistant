"""Read migration metadata from disposable copies, never a live database."""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .paths import is_link


def schema_versions(root: Path) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for database in root.glob("cindy-*.db"):
        result[database.name] = None
        if is_link(database) or not database.is_file():
            continue
        with tempfile.TemporaryDirectory(prefix="cindy-schema-") as temporary:
            copied = Path(temporary) / database.name
            for suffix in ("", "-wal", "-shm"):
                source = database.with_name(f"{database.name}{suffix}")
                if source.is_file() and not is_link(source):
                    shutil.copyfile(source, copied.with_name(f"{copied.name}{suffix}"))
            try:
                with sqlite3.connect(f"{copied.as_uri()}?mode=ro", uri=True) as connection:
                    row = connection.execute("SELECT value FROM migration_meta WHERE key='schema_version'").fetchone()
                    if row and re.fullmatch(r"[0-9]+", str(row[0])):
                        result[database.name] = int(row[0])
            except sqlite3.Error:
                pass
    return result


def highest_migration(resources: Path) -> int | None:
    versions = [int(path.name[:4]) for path in (resources / "drizzle").glob("*.sql") if re.match(r"^[0-9]{4}_", path.name)]
    return max(versions) if versions else None
