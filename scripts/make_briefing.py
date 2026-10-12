"""Generate today's briefing with the configured LLM.

Run: uv run python -m scripts.make_briefing
"""

import sys
from contextlib import closing

from api.agent import llm_client
from api.agent_tools import default_toolbox
from api.briefing import make_briefing
from api.db import connect, init_db
from api.settings import Settings

if __name__ == "__main__":
    settings = Settings.from_env()
    if not settings.llm_configured:
        sys.exit("briefing failed: LLM not configured")
    try:
        with closing(connect(settings.db_path)) as conn:
            init_db(conn)
            row = make_briefing(conn, llm_client(settings), settings.llm_model,
                                default_toolbox(settings))
        print(f"briefing written for {row['date']}")
    except Exception as exc:  # never print details: they could echo request data
        sys.exit(f"briefing failed: {type(exc).__name__}")
