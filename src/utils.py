"""
utils.py — GeoSentinel Terminal (VARTA)
Shared helpers: logger, palette, chart utilities.
Import from here — never reimplement.
"""

import logging
import datetime
import polars as pl
import plotly.graph_objects as go
from config import TEAM_PALETTE, KEY_EVENTS

# ── Logger ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("varta")


def set_dark_theme(fig: go.Figure) -> go.Figure:
    """
    Apply Bloomberg-style dark theme to a Plotly figure.

    Args:
        fig: Plotly Figure object.
    Returns:
        Same figure with dark theme applied.
    Example:
        fig = set_dark_theme(px.line(df, x='date', y='price'))
    """
    fig.update_layout(
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0f0f1a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(gridcolor="#1e293b", linecolor="#334155"),
        yaxis=dict(gridcolor="#1e293b", linecolor="#334155"),
    )
    return fig


def annotate_events(fig: go.Figure, events: list[tuple] | None = None) -> go.Figure:
    """
    Add vertical event lines to a Plotly time-series figure.

    Args:
        fig: Plotly Figure.
        events: List of (date_str, label) tuples. Defaults to KEY_EVENTS from config.
    Returns:
        Figure with event annotations added.
    Example:
        fig = annotate_events(fig)
    """
    if events is None:
        events = KEY_EVENTS
    for date_str, label in events:
        fig.add_vline(
            x=datetime.datetime.fromisoformat(date_str).timestamp() * 1000,  # milliseconds for Plotly datetime axis
            line_dash="dash",
            line_color="#475569",
            annotation_text=label,
            annotation_position="top left",
            annotation_font_size=9,
            annotation_font_color="#94a3b8",
        )
    return fig


def save_parquet(df: pl.DataFrame, path, label: str = "") -> None:
    """
    Save a Polars DataFrame to Parquet and log it.

    Args:
        df: Polars DataFrame.
        path: pathlib.Path or str destination.
        label: Human-readable label for logging.
    Example:
        save_parquet(df, DATA_PROC / 'prices.parquet', 'asset prices')
    """
    df.write_parquet(path)
    log.info(f"Saved {label} → {path} ({len(df):,} rows)")


def load_parquet(path, label: str = "") -> pl.DataFrame:
    """
    Load a Parquet file into a Polars DataFrame and log it.

    Args:
        path: pathlib.Path or str source.
        label: Human-readable label for logging.
    Returns:
        Polars DataFrame.
    Example:
        df = load_parquet(DATA_PROC / 'prices.parquet', 'asset prices')
    """
    df = pl.read_parquet(path)
    log.info(f"Loaded {label} ← {path} ({len(df):,} rows)")
    return df


def georisk_score(gpr: float, gpr_min: float, gpr_max: float) -> float:
    """
    Normalize a GPR value to a 0-100 GeoRisk score.

    Args:
        gpr: Raw GPR value.
        gpr_min: Historical minimum GPR.
        gpr_max: Historical maximum GPR.
    Returns:
        Float in [0, 100].
    Example:
        score = georisk_score(187.3, 50.0, 400.0)
    """
    if gpr_max == gpr_min:
        return 50.0
    return round(((gpr - gpr_min) / (gpr_max - gpr_min)) * 100, 1)
