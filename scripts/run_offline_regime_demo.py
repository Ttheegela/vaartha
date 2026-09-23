#!/usr/bin/env python3
"""Tiny offline runner: import and execute the regime fixture demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root without install
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.regime.offline_demo import run_offline_demo


def main() -> int:
    result = run_offline_demo()
    compact = {
        "mode": result["mode"],
        "n_events": result["n_events"],
        "regime_counts": result["validation"].get("regime_counts"),
        "change_point": result["change_point"],
        "feeds": result["feeds"],
        "sample_labels": [
            {"date": e["date"], "title": e["title"], "regime": e["regime"]}
            for e in result["labeled"][:3]
        ],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
