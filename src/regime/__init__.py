"""Regime upgrade stubs: offline demo + deferred GPR/MRI feed hooks."""

from src.regime.feeds import FeedConfig, fetch_gpr, fetch_mri
from src.regime.offline_demo import (
    change_point_check,
    label_regimes,
    load_fixture_events,
    run_offline_demo,
)

__all__ = [
    "FeedConfig",
    "fetch_gpr",
    "fetch_mri",
    "load_fixture_events",
    "label_regimes",
    "change_point_check",
    "run_offline_demo",
]
