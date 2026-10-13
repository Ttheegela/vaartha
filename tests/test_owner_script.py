"""Light tests for scripts/owner.sh: syntax and the `check` subcommand."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "owner.sh"
SENTINEL = "SECRET_SENTINEL_123"


def _check(tmp_path: Path, body: str | None, mode: int = 0o600):
    env_file = tmp_path / "owner.env"
    if body is not None:
        env_file.write_text(body)
        env_file.chmod(mode)
    env = {**os.environ, "VAARTHA_OWNER_ENV": str(env_file)}
    return subprocess.run(
        ["bash", str(SCRIPT), "check"], env=env, capture_output=True, text=True
    )


def test_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_missing_file(tmp_path):
    assert _check(tmp_path, None).returncode == 1


def test_wrong_mode(tmp_path):
    r = _check(tmp_path, f"TOKEN={SENTINEL}\n", 0o644)
    assert r.returncode == 1
    assert "chmod 600" in r.stdout + r.stderr


def test_demo_instance_refused(tmp_path):
    r = _check(tmp_path, f"VARTA_INSTANCE=demo\nTOKEN={SENTINEL}\n")
    assert r.returncode == 1


def test_valid_and_no_values_printed(tmp_path):
    r = _check(tmp_path, f"VARTA_INSTANCE=owner\nTOKEN={SENTINEL}\n")
    assert r.returncode == 0
    assert SENTINEL not in r.stdout + r.stderr


def test_sentinel_not_printed_on_failure(tmp_path):
    r = _check(tmp_path, f"VARTA_INSTANCE=demo\nTOKEN={SENTINEL}\n")
    assert SENTINEL not in r.stdout + r.stderr
