"""Normalization, hashing and tagging."""

from core.news import (
    RawItem,
    normalize_title,
    normalize_url,
    tag_tickers,
    tag_topics,
    title_hash,
    url_hash,
)

SECS = {"NVDA": ("nvidia",), "AMD": ("advanced micro devices",), "SPY": ("s&p 500",),
        "TSM": ("tsmc", "taiwan semiconductor")}


def _item(title, text="", symbols=()):
    return RawItem("test", "https://x.com/a", title, text, "2026-10-12T00:00:00Z", tuple(symbols))


def test_title_normalization_collapses_case_and_punctuation():
    assert normalize_title("  NVIDIA Beats — Estimates!! ") == normalize_title(
        "nvidia beats estimates")
    assert title_hash("Fed holds rates.") == title_hash("FED HOLDS RATES")


def test_url_normalization_drops_tracking():
    a = "https://WWW.Reuters.com/markets/story/?utm_source=x&id=7#top"
    b = "https://www.reuters.com/markets/story?id=7"
    assert normalize_url(a) == normalize_url(b)
    assert url_hash(a) == url_hash(b)
    assert normalize_url("https://x.com/a?id=1") != normalize_url("https://x.com/a?id=2")


def test_source_symbols_win():
    assert tag_tickers(_item("Chip news", symbols=["NVDA", "TSM"]), SECS) == ["NVDA", "TSM"]


def test_ticker_whole_word_case_sensitive():
    assert tag_tickers(_item("AMD launches new GPU"), SECS) == ["AMD"]
    assert tag_tickers(_item("AMDocs reports earnings"), SECS) == []
    assert tag_tickers(_item("New spyware found on phones"), SECS) == []
    assert tag_tickers(_item("amd shares slip"), SECS) == []


def test_alias_case_insensitive_whole_word():
    assert tag_tickers(_item("Nvidia and TSMC sign deal"), SECS) == ["NVDA", "TSM"]
    assert tag_tickers(_item("Taiwan Semiconductor output rises"), SECS) == ["TSM"]


def test_unknown_source_symbols_ignored():
    assert tag_tickers(_item("x", symbols=["ZZZZ", "NVDA"]), SECS) == ["NVDA"]


def test_topics():
    assert tag_topics("New sanctions on Iran lift Brent crude") == ["energy", "geopolitics"]
    assert tag_topics("Quiet day") == []
