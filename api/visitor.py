"""Anonymous visitor identity (cookie), client IP and a per-key rate limiter."""

import re
import time
from collections import defaultdict, deque
from uuid import uuid4

VISITOR_COOKIE = "varta_vid"
VISITOR_RE = re.compile(r"^[a-f0-9]{32}$")
COOKIE_MAX_AGE = 31536000  # 1 year
DEFAULT_WINDOW_S = 3600


def visitor_id(request) -> str | None:
    """The visitor cookie value if well-formed, else None."""
    v = request.cookies.get(VISITOR_COOKIE)
    return v if v and VISITOR_RE.match(v) else None


def new_visitor_id() -> str:
    """A fresh random visitor id."""
    return uuid4().hex


def client_ip(request, trust_proxy: bool) -> str:
    """Caller IP; behind a trusted proxy, the last X-Forwarded-For entry (the one it appended)."""
    xff = request.headers.get("x-forwarded-for")
    if trust_proxy and xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limiter: at most `limit` calls per key per `window_s`; limit <= 0 is off."""

    # ponytail: in-process memory; move to SQLite if the api runs >1 worker process
    def __init__(self, limit: int, window_s: int = DEFAULT_WINDOW_S, clock=time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Record a call for `key` and return whether it is within the limit."""
        if self.limit <= 0:
            return True
        now = self.clock()
        q = self._hits[key]
        while q and q[0] <= now - self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
