"""Repo hygiene: runtime data is ignored, source data directories elsewhere are not."""

import subprocess


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path]).returncode == 0


def test_runtime_data_dir_ignored():
    assert _ignored("data/varta.db")


def test_nested_data_dirs_not_ignored():
    assert not _ignored("web/lib/data/mock.ts")
    assert not _ignored("evals/data/tasks.yaml")
