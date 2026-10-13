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
    r = _check(tmp_path, None)
    assert r.returncode == 1
    assert "missing env file" in r.stdout + r.stderr


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


def test_unquoted_spaces_rejected(tmp_path):
    r = _check(tmp_path, "SEC_USER_AGENT=Tarun t@x.com\n")
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "not valid shell" in out and "quote values" in out
    assert "Tarun" not in out and "t@x.com" not in out


def test_shell_instance_not_inherited(tmp_path):
    env_file = tmp_path / "owner.env"
    env_file.write_text("FOO=1\n")
    env_file.chmod(0o600)
    env = {**os.environ, "VAARTHA_OWNER_ENV": str(env_file), "VARTA_INSTANCE": "demo"}
    r = subprocess.run(["bash", str(SCRIPT), "check"], env=env, capture_output=True, text=True)
    assert r.returncode == 0
