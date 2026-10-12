"""Source fetchers over mock transports: parsing, auth, fail-soft."""

from datetime import date

import httpx

from api.news_sources import fetch_alpaca, fetch_finnhub, fetch_rss

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
