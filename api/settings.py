"""Instance settings from environment variables."""

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

INSTANCES = ("owner", "demo")
PLAID_ENVS = ("sandbox", "production")
DEMO_CHAT_RATE = 20
DEMO_ADMIN_RATE = 5  # sync / link_token / exchange calls per IP per hour on the demo
DEFAULT_TZ = "America/New_York"
REDIRECT_SCHEME = "https"  # Plaid allows http://localhost only in sandbox; we require https
AUTH_IDLE_MINUTES = 15  # owner session idle timeout (env AUTH_IDLE_MINUTES)
PASSKEY_RP_NAME = "Vārtā"
DEV_HOST = "localhost"  # the only host allowed a plain-http passkey origin


def _check_redirect_uri(uri: str) -> None:
    """Plaid OAuth redirect: https, a real host, no wildcard, query or fragment."""
    parts = urlsplit(uri)
    if parts.scheme != REDIRECT_SCHEME or not parts.hostname or any(c in uri for c in "*?#"):
        raise ValueError("PLAID_REDIRECT_URI must be an https URL with no wildcard, "
                         f"query or fragment, got {uri!r}")


def _check_passkey_config(rp_id: str | None, origin: str | None) -> None:
    """Fail closed: the owner lock needs an RP ID and an exact https origin on that RP ID.

    http is allowed only for http://localhost[:port] (local dev).
    """
    if not rp_id or not origin:
        raise ValueError("PASSKEY_RP_ID and PASSKEY_ORIGIN are required when the owner lock is on "
                         "(set OWNER_AUTH=0 to disable it for local dev)")
    parts = urlsplit(origin)
    host = parts.hostname or ""
    exact = origin == f"{parts.scheme}://{parts.netloc}" and "@" not in parts.netloc
    secure = parts.scheme == "https" or (parts.scheme == "http" and host == DEV_HOST)
    on_rp = host == rp_id or host.endswith("." + rp_id)
    if not (host and exact and secure and on_rp):
        raise ValueError(f"PASSKEY_ORIGIN must be https://<host on PASSKEY_RP_ID> "
                         f"(or http://localhost), got {origin!r} for RP ID {rp_id!r}")


def local_today(tz: str, now: datetime | None = None) -> date:
    """The calendar date in zone `tz` (now = current UTC time unless given)."""
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


@dataclass(frozen=True)
class Settings:
    """Per-instance configuration. Secrets are excluded from repr."""

    db_path: Path
    instance: str
    plaid_env: str = "sandbox"
    plaid_client_id: str | None = field(default=None, repr=False)
    plaid_secret: str | None = field(default=None, repr=False)
    token_key: str | None = field(default=None, repr=False)
    alpaca_key: str | None = field(default=None, repr=False)
    alpaca_secret: str | None = field(default=None, repr=False)
    finnhub_key: str | None = field(default=None, repr=False)
    typesafe_key: str | None = field(default=None, repr=False)
    sec_user_agent: str | None = field(default=None, repr=False)
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    chat_rate_per_hour: int = 0  # 0 = off
    trust_proxy: bool = False
    tz: str = DEFAULT_TZ
    run_worker: bool = False  # run the scheduler in the API process (single-dyno hosting)
    cors_origins: tuple[str, ...] = ()
    cookie_domain: str | None = None
    plaid_redirect_uri: str | None = None  # OAuth return URL registered in the Plaid Dashboard
    auth_required: bool | None = None  # None = on for the owner instance (fail closed)
    passkey_rp_id: str | None = None
    passkey_origin: str | None = None
    passkey_rp_name: str = PASSKEY_RP_NAME
    auth_idle_minutes: int = AUTH_IDLE_MINUTES

    def __post_init__(self) -> None:
        if self.plaid_env not in PLAID_ENVS:
            raise ValueError(f"PLAID_ENV must be one of {PLAID_ENVS}, got {self.plaid_env!r}")
        if self.instance == "demo" and self.plaid_env == "production":
            raise ValueError("the demo instance must use the Plaid sandbox")
        if self.plaid_redirect_uri:
            _check_redirect_uri(self.plaid_redirect_uri)
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins, not *")
        if self.auth_required is None:
            object.__setattr__(self, "auth_required", self.instance == "owner")
        if self.auth_idle_minutes <= 0:
            raise ValueError("AUTH_IDLE_MINUTES must be positive")

    def check_auth_config(self) -> None:
        """Raise unless the passkey lock is off or fully configured (called at app startup)."""
        if self.auth_required:
            _check_passkey_config(self.passkey_rp_id, self.passkey_origin)

    @property
    def plaid_configured(self) -> bool:
        """True when both Plaid credentials are present."""
        return bool(self.plaid_client_id and self.plaid_secret)

    @property
    def llm_configured(self) -> bool:
        """True when both the LLM base URL and model are set."""
        return bool(self.llm_base_url and self.llm_model)

    @classmethod
    def from_env(cls) -> "Settings":
        """Read VARTA_*, PLAID_*, PASSKEY_*, TOKEN_ENCRYPTION_KEY, news keys; reject bad combos."""
        instance = os.environ.get("VARTA_INSTANCE", "demo")
        if instance not in INSTANCES:
            raise ValueError(f"VARTA_INSTANCE must be one of {INSTANCES}, got {instance!r}")
        return cls(
            db_path=Path(os.environ.get("VARTA_DB_PATH", "data/varta.db")),
            instance=instance,
            plaid_env=os.environ.get("PLAID_ENV", "sandbox"),
            plaid_client_id=os.environ.get("PLAID_CLIENT_ID") or None,
            plaid_secret=os.environ.get("PLAID_SECRET") or None,
            plaid_redirect_uri=os.environ.get("PLAID_REDIRECT_URI") or None,
            token_key=os.environ.get("TOKEN_ENCRYPTION_KEY") or None,
            alpaca_key=os.environ.get("ALPACA_API_KEY") or None,
            alpaca_secret=os.environ.get("ALPACA_SECRET_KEY") or None,
            finnhub_key=os.environ.get("FINNHUB_API_KEY") or None,
            typesafe_key=os.environ.get("TYPESAFE_API_KEY") or None,
            sec_user_agent=os.environ.get("SEC_USER_AGENT") or None,
            llm_base_url=os.environ.get("LLM_BASE_URL") or None,
            llm_model=os.environ.get("LLM_MODEL") or None,
            llm_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            chat_rate_per_hour=int(os.environ.get(
                "CHAT_RATE_PER_HOUR", DEMO_CHAT_RATE if instance == "demo" else 0)),
            trust_proxy=os.environ.get("TRUST_PROXY") == "1",
            tz=os.environ.get("VARTA_TZ") or DEFAULT_TZ,
            run_worker=os.environ.get("RUN_WORKER") == "1",
            cors_origins=tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",")
                               if o.strip()),
            cookie_domain=os.environ.get("COOKIE_DOMAIN") or None,
            auth_required=instance == "owner" and os.environ.get("OWNER_AUTH") != "0",
            # Browsers serialize origins in lowercase; compare like with like.
            passkey_rp_id=(os.environ.get("PASSKEY_RP_ID") or "").lower() or None,
            passkey_origin=(os.environ.get("PASSKEY_ORIGIN") or "").lower() or None,
            passkey_rp_name=os.environ.get("PASSKEY_RP_NAME") or PASSKEY_RP_NAME,
            auth_idle_minutes=int(os.environ.get("AUTH_IDLE_MINUTES") or AUTH_IDLE_MINUTES),
        )
