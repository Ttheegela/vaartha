"""Briefing text parsing."""

from api.briefing import parse_briefing


def test_normal():
    assert parse_briefing("Pay Con Edison.\n- Due Oct 14\n• Food at 86%\n") == (
        "Pay Con Edison.", ["Due Oct 14", "Food at 86%"])


def test_markdown_headline():
    assert parse_briefing("## **Pay the bill**\n- a") == ("Pay the bill", ["a"])


def test_bullets_capped_at_three():
    assert parse_briefing("H\n- 1\n- 2\n- 3\n- 4")[1] == ["1", "2", "3"]


def test_empty():
    assert parse_briefing("") == ("", [])
    assert parse_briefing("\n  \n") == ("", [])
