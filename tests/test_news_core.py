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


SHORT = {"F": ("ford",), "T": ("at&t",), "A": ("agilent",), "AMD": ("advanced micro devices",)}


def test_short_tickers_not_text_matched():
    assert tag_tickers(_item("A new chip ships"), SHORT) == []
    assert tag_tickers(_item("F-35 deal"), SHORT) == []
    assert tag_tickers(_item("Ford beats estimates"), SHORT) == ["F"]
    assert tag_tickers(_item("AT&T results"), SHORT) == ["T"]


def test_ticker_possessive_matches_but_joiners_block():
    assert tag_tickers(_item("AMD's new GPU"), SHORT) == ["AMD"]
    assert tag_tickers(_item("AMD-based servers"), SHORT) == []
    assert tag_tickers(_item("AMD&Intel deal"), SHORT) == []


def test_topic_keywords_match_at_word_start():
    assert tag_topics("Senator visits Chipotle in Miranda") == []
    assert tag_topics("Chipmakers rally on new chips") == ["semiconductors"]
    assert tag_topics("US widens sanctions") == ["geopolitics"]


def test_url_query_order_ignored():
    assert normalize_url("https://x.com/a?b=1&a=2") == normalize_url("https://x.com/a?a=2&b=1")


def test_title_unicode_punctuation_dropped():
    assert normalize_title("Fed… holds") == normalize_title("Fed holds")


def test_dot_blocks_only_before_alphanumeric():
    assert tag_tickers(_item("Investors bought AMD."), SHORT) == ["AMD"]
    assert tag_tickers(_item("AMD.X listing"), SHORT) == []


def test_chipmaker_and_inflationary_keywords():
    assert tag_topics("Chipmaker shares jump") == ["semiconductors"]
    assert tag_topics("Inflationary pressure builds") == ["macro"]


def test_hyphen_blocks_topic_keyword():
    assert tag_topics("Blue-chip stocks rally") == []
    assert tag_topics("Chip stocks rally") == ["semiconductors"]


def test_hyphenated_geo_names_still_tag_geopolitics():
    assert tag_topics("US-Iran tensions rise") == ["geopolitics"]
    assert tag_topics("Israel-Iran strikes") == ["geopolitics"]
    assert tag_topics("US-Taiwan deal") == ["geopolitics"]


def test_blue_chip_phrase_is_neutral():
    assert tag_topics("blue-chip stocks rally") == []
    assert tag_topics("blue chip stocks rally") == []
    assert tag_topics("blue-chip chipmaker gains") == ["semiconductors"]
