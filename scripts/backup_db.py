"""Snapshot the SQLite database and prune old snapshots.

Run: uv run python -m scripts.backup_db [--out data/backups] [--keep 7]
"""

import argparse
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from api.settings import Settings

DEFAULT_KEEP = 7
DEFAULT_OUT = "data/backups"


def backup_dir() -> Path:
    """Backup directory from VARTA_BACKUP_DIR, default data/backups."""
    return Path(os.environ.get("VARTA_BACKUP_DIR", DEFAULT_OUT))


def backup(db_path: Path, out_dir: Path, keep: int = DEFAULT_KEEP,
           now: datetime | None = None) -> Path:
    """Copy the live DB to out_dir/varta-YYYYMMDD-HHMM.db and keep only the newest `keep`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"varta-{(now or datetime.now(UTC)):%Y%m%d-%H%M}.db"
    with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)
    for old in sorted(out_dir.glob("varta-*.db"))[:-keep]:
        old.unlink()
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=backup_dir())
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args()
    print(backup(Settings.from_env().db_path, args.out, args.keep))
