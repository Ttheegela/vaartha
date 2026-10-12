"""Instance settings from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

INSTANCES = ("owner", "demo")
PLAID_ENVS = ("sandbox", "production")


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

    def __post_init__(self) -> None:
        if self.plaid_env not in PLAID_ENVS:
            raise ValueError(f"PLAID_ENV must be one of {PLAID_ENVS}, got {self.plaid_env!r}")
        if self.instance == "demo" and self.plaid_env == "production":
            raise ValueError("the demo instance must use the Plaid sandbox")

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
        """Read VARTA_*, PLAID_*, TOKEN_ENCRYPTION_KEY and news keys; reject bad combinations."""
        instance = os.environ.get("VARTA_INSTANCE", "demo")
        if instance not in INSTANCES:
            raise ValueError(f"VARTA_INSTANCE must be one of {INSTANCES}, got {instance!r}")
        return cls(
            db_path=Path(os.environ.get("VARTA_DB_PATH", "data/varta.db")),
            instance=instance,
            plaid_env=os.environ.get("PLAID_ENV", "sandbox"),
            plaid_client_id=os.environ.get("PLAID_CLIENT_ID") or None,
            plaid_secret=os.environ.get("PLAID_SECRET") or None,
            token_key=os.environ.get("TOKEN_ENCRYPTION_KEY") or None,
            alpaca_key=os.environ.get("ALPACA_API_KEY") or None,
            alpaca_secret=os.environ.get("ALPACA_SECRET_KEY") or None,
            finnhub_key=os.environ.get("FINNHUB_API_KEY") or None,
            typesafe_key=os.environ.get("TYPESAFE_API_KEY") or None,
            sec_user_agent=os.environ.get("SEC_USER_AGENT") or None,
            llm_base_url=os.environ.get("LLM_BASE_URL") or None,
            llm_model=os.environ.get("LLM_MODEL") or None,
            llm_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
        )
