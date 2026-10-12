"""Visitor cookie, client IP and rate limiter helpers."""

from types import SimpleNamespace as NS

from api.visitor import RateLimiter, client_ip, visitor_id


def _req(headers=None, cookies=None, host="9.9.9.9"):
    return NS(headers=headers or {}, cookies=cookies or {}, client=NS(host=host) if host else None)


def test_limiter_window():
    now = [0.0]
    rl = RateLimiter(2, window_s=100, clock=lambda: now[0])
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    assert rl.allow("b")
    now[0] = 101
    assert rl.allow("a")


def test_limiter_zero_always_allows():
    rl = RateLimiter(0)
    assert all(rl.allow("a") for _ in range(100))


def test_client_ip():
    xff = {"x-forwarded-for": "1.1.1.1, 2.2.2.2"}
    assert client_ip(_req(xff), False) == "9.9.9.9"
    assert client_ip(_req(xff), True) == "2.2.2.2"
    assert client_ip(_req(), True) == "9.9.9.9"
    assert client_ip(_req(host=None), False) == "unknown"


def test_visitor_id_validates():
    good = "a" * 32
    assert visitor_id(_req(cookies={"varta_vid": good})) == good
    assert visitor_id(_req(cookies={"varta_vid": "nope"})) is None
    assert visitor_id(_req()) is None
