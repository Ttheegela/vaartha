"""
llm.py — GeoSentinel Terminal (VARTA)
Exposes pre-computed Gemma 4 LLM crisis scores from GDELT headlines.
Never calls Gemma on user interaction — all scoring is pre-computed via
notebooks/06_llm_scoring.ipynb or scripts/amarel_score_gdelt.py.
"""

import polars as pl
from src.data.loaders import load_gdelt
from src.utils import log
from config import KEY_EVENTS


def get_scored_headlines(demo_mode: bool = True) -> pl.DataFrame:
    """
    Load GDELT headlines with LLM crisis scores.

    Args:
        demo_mode: passed to load_gdelt.
    Returns:
        DataFrame with columns: date, headline, tone, llm_score, query_term
        Sorted by date descending.
    Example:
        df = get_scored_headlines(demo_mode=True)
    """
    df = load_gdelt(demo_mode)
    if df.is_empty():
        return df
    return df.sort("date", descending=True)


def get_event_headlines(event_date: str, window_days: int = 30, demo_mode: bool = True) -> pl.DataFrame:
    """
    Return headlines within ±window_days of a geopolitical event date.

    Args:
        event_date: ISO date string, e.g. '2022-02-24'.
        window_days: Days before/after event to include.
        demo_mode: passed to get_scored_headlines.
    Returns:
        DataFrame filtered to event window, sorted by llm_score desc.
    Example:
        df = get_event_headlines('2022-02-24', window_days=30)
    """
    df = get_scored_headlines(demo_mode)
    if df.is_empty():
        return df

    import datetime
    center = datetime.date.fromisoformat(event_date)
    lo = (center - datetime.timedelta(days=window_days)).isoformat()
    hi = (center + datetime.timedelta(days=window_days)).isoformat()

    filtered = df.filter(
        (pl.col("date").cast(pl.Utf8) >= lo) &
        (pl.col("date").cast(pl.Utf8) <= hi)
    )
    if "llm_score" in filtered.columns:
        filtered = filtered.sort("llm_score", descending=True)
    return filtered


def get_daily_avg_score(demo_mode: bool = True) -> pl.DataFrame:
    """
    Compute daily mean LLM crisis score across all headlines.

    Args:
        demo_mode: passed to get_scored_headlines.
    Returns:
        DataFrame with columns: date, avg_llm_score
        Sorted by date ascending.
    Example:
        df = get_daily_avg_score()
    """
    df = get_scored_headlines(demo_mode)
    if df.is_empty() or "llm_score" not in df.columns:
        return pl.DataFrame()
    return (
        df.group_by("date")
        .agg(pl.col("llm_score").mean().alias("avg_llm_score"))
        .sort("date")
    )


def get_top_headlines(n: int = 20, demo_mode: bool = True) -> pl.DataFrame:
    """
    Return the top-N highest crisis-scored headlines across the full dataset.

    Args:
        n: Number of headlines to return.
        demo_mode: passed to get_scored_headlines.
    Returns:
        DataFrame with top-N rows sorted by llm_score desc.
    Example:
        df = get_top_headlines(n=10)
    """
    df = get_scored_headlines(demo_mode)
    if df.is_empty() or "llm_score" not in df.columns:
        return df
    return df.sort("llm_score", descending=True).head(n)
