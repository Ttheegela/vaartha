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
    r = _check(tmp_path, f"VARTA_INSTANCE=owner\nOWNER_AUTH=0\nTOKEN={SENTINEL}\n")
    assert r.returncode == 0
    assert SENTINEL not in r.stdout + r.stderr


def test_sentinel_not_printed_on_failure(tmp_path):
    r = _check(tmp_path, f"VARTA_INSTANCE=demo\nTOKEN={SENTINEL}\n")
    assert SENTINEL not in r.stdout + r.stderr


def test_passkey_vars_required_unless_auth_off(tmp_path):
    r = _check(tmp_path, f"TOKEN={SENTINEL}\nPASSKEY_RP_ID=\n")
    assert r.returncode == 1
    assert "PASSKEY_RP_ID" in r.stdout + r.stderr and SENTINEL not in r.stdout + r.stderr
    r = _check(tmp_path, "PASSKEY_RP_ID=h.example\n")
    assert r.returncode == 1 and "PASSKEY_ORIGIN" in r.stdout + r.stderr
    ok = "PASSKEY_RP_ID=h.example\nPASSKEY_ORIGIN=https://h.example\n"
    assert _check(tmp_path, ok).returncode == 0
    assert _check(tmp_path, "OWNER_AUTH=0\n").returncode == 0


def test_unquoted_spaces_rejected(tmp_path):
    r = _check(tmp_path, "SEC_USER_AGENT=Tarun t@x.com\n")
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "not valid shell" in out and "quote values" in out
    assert "Tarun" not in out and "t@x.com" not in out


def test_shell_instance_not_inherited(tmp_path):
    env_file = tmp_path / "owner.env"
    env_file.write_text("OWNER_AUTH=0\n")
    env_file.chmod(0o600)
    env = {**os.environ, "VAARTHA_OWNER_ENV": str(env_file), "VARTA_INSTANCE": "demo"}
    r = subprocess.run(["bash", str(SCRIPT), "check"], env=env, capture_output=True, text=True)
    assert r.returncode == 0


def test_stale_pidfile_with_recycled_pid_is_ignored(tmp_path):
    """A pidfile pointing at an unrelated live process is stale: not running, never killed."""
    data = tmp_path / "Library" / "Application Support" / "Vaartha"
    data.mkdir(parents=True)
    victim = subprocess.Popen(["sleep", "30"])
    try:
        for n in ("api", "web"):
            (data / f"{n}.pid").write_text(str(victim.pid))
        env = {**os.environ, "HOME": str(tmp_path)}
        for cmd in ("status", "stop"):
            r = subprocess.run(["bash", str(SCRIPT), cmd], env=env, capture_output=True, text=True)
            assert "api: running" not in r.stdout and "web: running" not in r.stdout
            assert "stopped api" not in r.stdout and "stopped web" not in r.stdout
            assert victim.poll() is None, f"{cmd} killed an unrelated process"
        assert not (data / "api.pid").exists() and not (data / "web.pid").exists()
    finally:
        victim.kill()
        victim.wait()


OK_PASSKEY = "PASSKEY_RP_ID=h.example\nPASSKEY_ORIGIN=https://h.example\n"


def test_malformed_passkey_origin_fails_check(tmp_path):
    for origin in ("https://h.example/", "http://h.example", "https://other.example"):
        r = _check(tmp_path, f"PASSKEY_RP_ID=h.example\nPASSKEY_ORIGIN={origin}\n")
        out = r.stdout + r.stderr
        assert r.returncode == 1 and "PASSKEY_ORIGIN" in out, origin
    assert _check(tmp_path, OK_PASSKEY).returncode == 0


def test_owner_auth_not_inherited_by_check(tmp_path):
    env_file = tmp_path / "owner.env"
    env_file.write_text("VARTA_INSTANCE=owner\n")
    env_file.chmod(0o600)
    env = {**os.environ, "VAARTHA_OWNER_ENV": str(env_file), "OWNER_AUTH": "0"}
    r = subprocess.run(["bash", str(SCRIPT), "check"], env=env, capture_output=True, text=True)
    assert r.returncode == 1  # the shell's OWNER_AUTH=0 must not disable the lock


def test_passkey_subcommand_uses_owner_db(tmp_path):
    """`owner.sh passkey` runs the CLI against $DATA_DIR/varta.db, not a cwd-relative DB."""
    import sqlite3

    from api.db import connect, init_db

    data = tmp_path / "Library" / "Application Support" / "Vaartha"
    data.mkdir(parents=True)
    conn = connect(data / "varta.db")
    init_db(conn)
    conn.close()
    env_file = tmp_path / "owner.env"
    env_file.write_text(OK_PASSKEY)
    env_file.chmod(0o600)
    env = {**os.environ, "HOME": str(tmp_path), "VAARTHA_OWNER_ENV": str(env_file)}
    env.pop("VARTA_DB_PATH", None)
    run = lambda *a: subprocess.run(  # noqa: E731
        ["bash", str(SCRIPT), "passkey", *a], env=env, capture_output=True, text=True, cwd=tmp_path)
    r = run("list")
    assert r.returncode == 0 and "0 passkey(s)" in r.stdout, r.stdout + r.stderr
    r = run("setup-code")
    assert r.returncode == 0 and "Setup code" in r.stdout, r.stdout + r.stderr
    rows = sqlite3.connect(data / "varta.db").execute("SELECT count(*) FROM app_state").fetchone()
    assert rows[0] >= 1
    assert not (tmp_path / "data").exists()
