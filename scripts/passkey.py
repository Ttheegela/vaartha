"""Manage the owner instance's passkey lock.

Run via the owner script so it uses the owner database:
     scripts/owner.sh passkey setup-code    # one-time code to register a passkey
     scripts/owner.sh passkey list          # count and dates, never key material
     scripts/owner.sh passkey reset [--yes] # delete every passkey and session
"""

import argparse
from contextlib import closing

from api.auth import SETUP_CODE_MINUTES, issue_setup_code
from api.db import connect, init_db
from api.settings import Settings

RESET_WORD = "RESET"


def main(argv: list[str] | None = None, settings: Settings | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup-code")
    sub.add_parser("list")
    reset = sub.add_parser("reset")
    reset.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)
    settings = settings or Settings.from_env()
    if not settings.db_path.exists():
        raise SystemExit(f"no database at {settings.db_path}; run via "
                         "'scripts/owner.sh passkey ...' (the owner instance's DB)")
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)

    if args.cmd == "setup-code":
        code = issue_setup_code(settings.db_path)
        print(f"Setup code (valid {SETUP_CODE_MINUTES} min): {code}")
        return
    with closing(connect(settings.db_path)) as conn:
        if args.cmd == "list":
            rows = conn.execute("SELECT created_at, last_used_at FROM auth_credentials "
                                "ORDER BY created_at").fetchall()
            print(f"{len(rows)} passkey(s)")
            for r in rows:
                print(f"created {r['created_at']}  last used {r['last_used_at'] or 'never'}")
            return
        if not args.yes and input(f"type {RESET_WORD} to confirm: ") != RESET_WORD:
            raise SystemExit("not confirmed; nothing deleted")
        with conn:
            creds = conn.execute("DELETE FROM auth_credentials").rowcount
            sessions = conn.execute("DELETE FROM auth_sessions").rowcount
            conn.execute("DELETE FROM auth_challenges")
        print(f"deleted {creds} passkey(s) and {sessions} session(s)")


if __name__ == "__main__":
    main()
