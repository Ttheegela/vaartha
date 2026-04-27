"""
build_demo_bundle.py — GeoSentinel Terminal (VARTA)
Freeze all processed data to CSVs in data/demo/ for offline presentation.
Run this before May 3, 2026 (before presentation day).
Usage: python scripts/build_demo_bundle.py
After running, set DEMO_MODE = True in config.py (already the default).
"""

import polars as pl
from src.utils import log
from config import DATA_PROC, DATA_DEMO


def freeze(name: str) -> None:
    """Load a processed Parquet and save it as a demo CSV."""
    src = DATA_PROC / f"{name}.parquet"
    dst = DATA_DEMO / f"{name}.csv"
    if not src.exists():
        log.warning(f"Skipping {name} — {src} not found. Run fetch_all_data.py first.")
        return
    df = pl.read_parquet(src)
    df.write_csv(dst)
    log.info(f"Frozen {name} → {dst} ({len(df):,} rows)")


def main():
    log.info("=== build_demo_bundle.py starting ===")
    for dataset in ["prices", "fred", "gdelt", "regimes", "signals", "kronos_forecasts"]:
        freeze(dataset)
    log.info("=== Demo bundle complete. Test offline before May 3! ===")


if __name__ == "__main__":
    main()
