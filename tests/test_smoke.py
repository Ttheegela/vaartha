"""Smoke test: packages import without side effects."""


def test_packages_import():
    import api  # noqa: F401
    import core  # noqa: F401
