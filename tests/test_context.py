import pandas as pd
import pytest

from macrocal.context import context_stats


def monthly(values: list[float], start="2025-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"date": dates, "value": values})


def test_latest_previous_and_changes():
    stats = context_stats(monthly([100.0, 102.0, 105.0]))
    assert stats["latest"] == 105.0
    assert stats["previous"] == 102.0
    assert stats["change"] == pytest.approx(3.0)
    assert stats["pct_change"] == pytest.approx(3 / 102 * 100)
    assert stats["latest_date"] == pd.Timestamp("2025-03-01")


def test_yoy_uses_the_point_twelve_months_earlier():
    values = [100.0] + [0.0] * 11 + [110.0]  # Jan 2025 -> Jan 2026
    stats = context_stats(monthly(values))
    assert stats["yoy_pct"] == pytest.approx(10.0)


def test_yoy_is_none_when_the_year_ago_month_is_missing():
    stats = context_stats(monthly([100.0, 101.0, 102.0]))
    assert stats["yoy_pct"] is None


def test_single_point_has_no_previous_or_change():
    stats = context_stats(monthly([4.2]))
    assert stats["latest"] == 4.2
    assert stats["previous"] is None
    assert stats["change"] is None
    assert stats["pct_change"] is None


def test_previous_is_the_prior_available_point_even_across_a_gap():
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2025-08-01", "2025-09-01", "2025-11-01"]), "value": [1.0, 2.0, 4.0]}
    )
    stats = context_stats(df)
    assert stats["previous"] == 2.0
    assert stats["change"] == 2.0


def test_zero_previous_does_not_divide_by_zero():
    stats = context_stats(monthly([0.0, 5.0]))
    assert stats["pct_change"] is None
