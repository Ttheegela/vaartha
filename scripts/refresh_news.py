"""Refresh news, sentiment and crowd odds.

Run: uv run python -m scripts.refresh_news --offline   (fixtures + heuristic scorer, no network)
     uv run python -m scripts.refresh_news             (live sources; keys from the environment)
"""

import argparse
from contextlib import closing
from datetime import UTC, datetime

from api.db import connect, init_db
from api.news_fixtures import fixture_sources
from api.news_pipeline import default_sources, refresh_news
from api.scoring import HeuristicScorer, TypeSafeScorer
from api.settings import Settings


def run(settings: Settings, *, offline: bool, now: datetime) -> dict:
    """Run one refresh cycle against the configured DB; offline never touches the network."""
    if offline:
        sources, scorer = fixture_sources(now), HeuristicScorer()
    else:
        sources = default_sources(settings, now.date())
        scorer = TypeSafeScorer(settings.typesafe_key) if settings.typesafe_key \
            else HeuristicScorer()
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        return refresh_news(conn, sources, scorer, now, fallback=HeuristicScorer())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    print(run(Settings.from_env(), offline=args.offline, now=datetime.now(UTC)))
