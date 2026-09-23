"""
Feed hooks for geopolitical / market-risk indices.

Live GPR / MRI fetchers are intentionally stubbed. Offline demo mode is the
default — see ``FeedConfig.offline_mode`` and ``src.regime.offline_demo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FeedConfig:
    """Configuration for regime feed adapters.

    Attributes:
        offline_mode: When True (default), callers should use fixtures /
            ``offline_demo`` instead of network fetches. Live GPR/MRI wiring
            is deferred to a later upgrade.
    """

    offline_mode: bool = True


def fetch_gpr(config: FeedConfig | None = None) -> Any:
    """Fetch Caldara–Iacoviello Geopolitical Risk (GPR) index.

    Planned free source: daily GPR series published by Matteo Iacoviello
    (matteoiacoviello.com / associated academic data releases). Not wired yet —
    keep ``FeedConfig.offline_mode=True`` and use fixture-backed demos.

    Raises:
        NotImplementedError: Always, until live GPR ingest lands.
    """
    _ = config or FeedConfig()
    raise NotImplementedError(
        "Live GPR fetch deferred. Use offline fixtures "
        "(data/fixtures/regime_events.json) or see Caldara–Iacoviello GPR "
        "free data at https://www.matteoiacoviello.com/gpr.htm"
    )


def fetch_mri(config: FeedConfig | None = None) -> Any:
    """Fetch MRI-style market-risk / moneyfeel sentiment feed.

    Planned free/public MRI-style feeds (e.g. moneyfeel-style risk appetite
    proxies). Not wired yet — offline demo remains the supported path.

    Raises:
        NotImplementedError: Always, until live MRI ingest lands.
    """
    _ = config or FeedConfig()
    raise NotImplementedError(
        "Live MRI / moneyfeel-style feed deferred. Use offline fixtures "
        "and FeedConfig(offline_mode=True)."
    )
