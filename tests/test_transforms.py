"""
Unit tests for your transformation functions.

Pandera checks the data; these check the code. They need fixtures, not
data files -- known input, known output.
"""

import pytest


def years_between(start: str, end: str) -> int:
    """Placeholder. Import your real function instead."""
    from datetime import date
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return (e - s).days // 365


def test_whole_years():
    assert years_between("2015-01-06", "2026-01-06") == 11


def test_same_day_is_zero():
    assert years_between("2026-01-06", "2026-01-06") == 0


@pytest.mark.skip(reason="replace with a test of your own matching logic")
def test_fuzzy_match_rejects_below_threshold():
    ...
