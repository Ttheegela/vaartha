"""Fail any test that opens a network connection (TestClient is in-process)."""

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*a, **k):
        raise RuntimeError("network access in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
