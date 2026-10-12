"""Source fetchers over mock transports: parsing, auth, fail-soft."""

from datetime import date

import httpx

from api.news_sources import (
    MAX_RESPONSE_BYTES,
    fetch_alpaca,
    fetch_edgar,
    fetch_finnhub,
    fetch_gdelt,
    fetch_polymarket,
    fetch_rss,
)

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Fed holds rates steady</title><link>https://mw.com/a</link>
<pubDate>Sun, 11 Oct 2026 14:30:00 GMT</pubDate><description>
&lt;p&gt;Policy &lt;b&gt;unchanged&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title></title><link>https://mw.com/empty</link></item>
</channel></rss>"""


def _t(handler):
    return httpx.MockTransport(handler)


def test_alpaca_parses_and_sends_headers():
    seen = {}

    def h(req):
        seen.update(headers=req.headers, params=dict(req.url.params))
        return httpx.Response(200, json={"news": [{
            "headline": "NVIDIA up", "summary": "s", "url": "https://b.com/1", "source": "benzinga",
            "created_at": "2026-10-11T14:30:05Z", "symbols": ["NVDA", "AMD"]}]})

    items = fetch_alpaca("k", "s", ["NVDA", "AMD"], transport=_t(h))
    assert seen["headers"]["APCA-API-KEY-ID"] == "k"
    assert seen["params"]["symbols"] == "NVDA,AMD"
    assert items[0].source == "Alpaca/benzinga"
    assert items[0].symbols == ("NVDA", "AMD")
    assert items[0].published_at == "2026-10-11T14:30:05Z"


def test_alpaca_missing_key_no_request():
    def h(req):
        raise AssertionError("should not be called")

    assert fetch_alpaca(None, None, ["NVDA"], transport=_t(h)) == []


def test_finnhub_unix_time_and_symbol_cap():
    calls = []

    def h(req):
        calls.append(req.url.params["symbol"])
        return httpx.Response(200, json=[{
            "headline": "TSMC capex", "summary": "", "url": "https://r.com/2",
            "source": "Reuters", "datetime": 1791772200}])

    syms = [f"T{i}" for i in range(12)]
    items = fetch_finnhub("k", syms, date(2026, 10, 12), transport=_t(h))
    assert len(calls) == 8
    assert items[0].source == "Finnhub/Reuters"
    assert items[0].published_at.endswith("Z") and items[0].symbols == ("T0",)


def test_rss_parses_strips_html_and_skips_empty():
    ok = _t(lambda r: httpx.Response(200, text=RSS))
    items = fetch_rss((("MarketWatch", "https://feed"),), transport=ok)
    assert len(items) == 1
    assert items[0].title == "Fed holds rates steady"
    assert items[0].text == "Policy unchanged"
    assert items[0].published_at == "2026-10-11T14:30:00Z"


def test_failures_are_soft():
    boom = _t(lambda r: httpx.Response(500, text="err"))
    html = _t(lambda r: httpx.Response(200, text="<html>not json</html>"))
    assert fetch_alpaca("k", "s", ["NVDA"], transport=boom) == []
    assert fetch_alpaca("k", "s", ["NVDA"], transport=html) == []
    assert fetch_finnhub("k", ["NVDA"], date(2026, 10, 12), transport=boom) == []
    bad_xml = _t(lambda r: httpx.Response(200, text="<not-xml"))
    assert fetch_rss((("X", "https://feed"),), transport=bad_xml) == []


def test_network_error_soft():
    def h(req):
        raise httpx.ConnectError("down")

    assert fetch_rss((("X", "https://feed"),), transport=_t(h)) == []


def test_rss_item_without_pubdate_skipped_rest_kept():
    xml = ("<rss><channel><item><title>A</title><link>https://x/a</link></item>"
           "<item><title>B</title><link>https://x/b</link>"
           "<pubDate>Sun, 11 Oct 2026 14:30:00 GMT</pubDate></item></channel></rss>")
    ok = _t(lambda r: httpx.Response(200, text=xml))
    items = fetch_rss((("X", "https://feed"),), transport=ok)
    assert [i.title for i in items] == ["B"]


def test_alpaca_bad_item_skipped_and_all_headers_params():
    seen = {}

    def h(req):
        seen.update(headers=req.headers, params=dict(req.url.params))
        return httpx.Response(200, json={"news": [
            {"headline": "bad", "url": "u", "source": "s"},
            {"headline": "ok", "url": "u2", "source": "s", "created_at": "2026-10-11T14:30:05Z"}]})

    items = fetch_alpaca("k", "sec", ["NVDA"], transport=_t(h))
    assert [i.title for i in items] == ["ok"]
    assert seen["headers"]["APCA-API-SECRET-KEY"] == "sec"
    assert seen["params"]["limit"] == "50" and seen["params"]["sort"] == "desc"


def test_finnhub_header_auth_bad_article_skipped_and_symbol_failure_isolated():
    seen = []

    def h(req):
        seen.append((req.headers.get("X-Finnhub-Token"), dict(req.url.params)))
        if req.url.params["symbol"] == "AAA":
            return httpx.Response(500, text="err")
        return httpx.Response(200, json=[
            {"headline": "bad", "url": "u", "source": "s"},
            {"headline": "ok", "url": "u2", "source": "s", "datetime": 1791772200}])

    items = fetch_finnhub("k", ["AAA", "BBB"], date(2026, 10, 12), transport=_t(h))
    assert [i.title for i in items] == ["ok"]
    assert all(tok == "k" and "token" not in p for tok, p in seen)


def test_finnhub_missing_key_no_request():
    def h(req):
        raise AssertionError("should not be called")

    assert fetch_finnhub(None, ["NVDA"], date(2026, 10, 12), transport=_t(h)) == []


def test_gdelt_parses_and_survives_rate_limit_text():
    ok = _t(lambda r: httpx.Response(200, json={"articles": [
        {"url": "https://ft.com/x", "title": "New sanctions hit tankers",
         "seendate": "20261011T143000Z",
         "domain": "ft.com"}, {"url": "", "title": "no url"}]}))
    items = fetch_gdelt(transport=ok)
    assert [i.title for i in items] == ["New sanctions hit tankers"]
    assert items[0].published_at == "2026-10-11T14:30:00Z" and items[0].source == "GDELT/ft.com"
    limited = _t(lambda r: httpx.Response(200, text="Please limit requests to one every 5 seconds"))
    assert fetch_gdelt(transport=limited) == []


def test_edgar_needs_user_agent_and_filters_8k():
    def h(req):
        assert req.headers["User-Agent"] == "Varta dev@example.com"
        if req.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {
                "cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}})
        return httpx.Response(200, json={"name": "NVIDIA CORP", "filings": {"recent": {
            "form": ["8-K", "10-Q", "8-K"],
            "filingDate": ["2026-10-10", "2026-10-09", "2026-09-01"],
            "accessionNumber": ["0001045810-26-000123", "x", "y"],
            "primaryDocument": ["d8k.htm", "q.htm", "o.htm"]}}})

    items = fetch_edgar("Varta dev@example.com", ["NVDA", "ZZZ"], date(2026, 10, 12),
                        transport=_t(h))
    assert len(items) == 1
    assert items[0].url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/d8k.htm")
    assert items[0].symbols == ("NVDA",) and items[0].source == "SEC EDGAR"
    assert fetch_edgar(None, ["NVDA"], date(2026, 10, 12),
                       transport=_t(lambda r: 1 / 0)) == []


def test_polymarket_filters_and_ranks():
    markets = [
        {"id": 1, "question": "Will China blockade Taiwan in 2026?",
         "outcomePrices": "[\"0.07\", \"0.93\"]", "liquidity": "900000",
         "endDate": "2026-12-31T00:00:00Z", "slug": "china-taiwan"},
        {"id": 2, "question": "NBA finals winner?", "outcomePrices": "[\"0.5\",\"0.5\"]",
         "liquidity": "5", "slug": "nba"},
        {"id": 3, "question": "US recession in 2026?", "outcomePrices": "[\"0.21\",\"0.79\"]",
         "liquidity": "100", "endDate": "2026-12-31", "slug": "rec"},
    ]
    pages = iter([markets, [], []])
    got = fetch_polymarket(
        transport=_t(lambda r: httpx.Response(200, json=next(pages))))
    assert [m.market_id for m in got] == ["1", "3"]
    assert got[0].yes_prob == 0.07 and got[0].category == "China / Taiwan"
    assert got[1].category == "US Macro"


def test_edgar_one_malformed_ticker_entry_skipped():
    def h(req):
        if req.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={
                "0": {"ticker": "BAD"},
                "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}})
        return httpx.Response(200, json={"filings": {"recent": {
            "form": ["8-K"], "filingDate": ["2026-10-10"],
            "accessionNumber": ["0001045810-26-000123"], "primaryDocument": ["d.htm"]}}})

    items = fetch_edgar("Varta dev@example.com", ["NVDA"], date(2026, 10, 12), transport=_t(h))
    assert len(items) == 1
    assert items[0].title == "NVIDIA CORP files 8-K (2026-10-10)"


def test_oversized_response_treated_as_failure(caplog):
    big = httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))
    with caplog.at_level("WARNING"):
        assert fetch_rss((("L", "https://f.example/rss"),), transport=_t(lambda r: big)) == []
        assert fetch_gdelt(transport=_t(lambda r: big)) == []
    assert "response too large" in caplog.text
