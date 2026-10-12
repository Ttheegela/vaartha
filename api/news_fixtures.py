"""Deterministic offline news and prediction-market data. Demo/test data only, not real news."""

from datetime import UTC, datetime, timedelta

from api.news_pipeline import Sources
from api.news_sources import Market
from core.news import RawItem

OLD_DAYS = 100


def fixture_sources(now: datetime) -> Sources:
    """Fixture items relative to `now`: one duplicate, MARKET items, one stale item."""

    def at(**delta) -> str:
        return (now - timedelta(**delta)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    export = "US tightens chip export controls on Nvidia sales to China"
    alpaca = [
        RawItem("Alpaca", "https://news.example.com/nvda-earnings",
                "Nvidia earnings beat estimates as data center revenue surges",
                "Nvidia posted record growth and raised guidance.", at(hours=3), ("NVDA",)),
    ]
    finnhub = [
        RawItem("Finnhub", "https://news.example.com/nvda-export", export,
                "New export controls restrict advanced chip shipments.", at(hours=8), ("NVDA",)),
        RawItem("Finnhub", "https://news.example.com/tsm-capex",
                "TSMC raises capex plan on strong AI chip demand",
                "The foundry expects higher spending next year.", at(days=1), ("TSM",)),
    ]
    rss = [
        RawItem("MarketWatch", "https://rss.example.com/story?id=9&utm_source=feed", export.upper(),
                "", at(hours=7)),
        RawItem("MarketWatch", "https://rss.example.com/fed",
                "Federal Reserve signals rate cut as inflation cools", "", at(days=2)),
        RawItem("MarketWatch", "https://rss.example.com/inflation",
                "Inflation fears weigh on Treasury yield outlook", "", at(days=3)),
    ]
    gdelt = [
        RawItem("GDELT", "https://gdelt.example.com/opec",
                "OPEC cuts supply and Exxon shares rally", "Crude prices climb.", at(days=4)),
    ]
    edgar = [
        RawItem("EDGAR", "https://sec.example.com/nvda-8k", "NVDA filed an 8-K", "",
                at(days=5), ("NVDA",)),
        RawItem("EDGAR", "https://sec.example.com/nvda-old-8k", "NVDA filed an older 8-K", "",
                at(days=OLD_DAYS), ("NVDA",)),
    ]
    markets = [
        Market("fx-taiwan", "Will China invade Taiwan this year?", 0.07, 250000.0, "2026-12-31",
               "https://poly.example.com/taiwan", "geopolitics"),
        Market("fx-recession", "Will the US enter a recession?", 0.21, 180000.0, "2026-12-31",
               "https://poly.example.com/recession", "macro"),
        Market("fx-iran", "Iran nuclear deal signed?", 0.12, 90000.0, "2026-12-31",
               "https://poly.example.com/iran", "geopolitics"),
    ]
    return Sources(
        news=[("Alpaca", lambda t: alpaca), ("Finnhub", lambda t: finnhub),
              ("RSS", lambda t: rss), ("GDELT", lambda t: gdelt), ("EDGAR", lambda t: edgar)],
        markets=lambda: markets,
    )
