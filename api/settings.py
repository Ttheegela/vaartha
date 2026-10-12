"""Instance settings from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

INSTANCES = ("owner", "demo")


@dataclass(frozen=True)
class Settings:
    """Per-instance configuration."""

    db_path: Path
    instance: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Read VARTA_DB_PATH and VARTA_INSTANCE; reject unknown instances."""
        instance = os.environ.get("VARTA_INSTANCE", "demo")
        if instance not in INSTANCES:
            raise ValueError(f"VARTA_INSTANCE must be one of {INSTANCES}, got {instance!r}")
        db_path = Path(os.environ.get("VARTA_DB_PATH", "data/varta.db"))
        return cls(db_path=db_path, instance=instance)
