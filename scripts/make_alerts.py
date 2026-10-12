"""Generate rule-based alerts.

Run: uv run python -m scripts.make_alerts
"""

import json
from contextlib import closing

from api.agent_tools import default_toolbox
from api.alerts import generate_alerts
from api.db import connect, init_db
from api.settings import Settings

if __name__ == "__main__":
    settings = Settings.from_env()
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)
        print(json.dumps({"alerts": generate_alerts(conn, default_toolbox(settings))}))
