import datetime as dt

import numpy as np
import pandas as pd
import pytest

from macrocal import markets


def yahoo_frame(closes: dict[str, list[float]], start="2026-09-01") -> pd.DataFrame:
    """Same shape yfinance 1.7 returns: (Price, Ticker) MultiIndex columns, even for one ticker."""
    n = max(len(v) for v in closes.values())
    index = pd.bdate_range(start, periods=n, name="Date")
    close = pd.DataFrame({sym: pd.Series(vals, index=index[: len(vals)]) for sym, vals in closes.items()})
    volume = close * 0 + 1
    return pd.concat({"Close": close, "Volume": volume}, axis=1)


@pytest.fixture
def downloads(monkeypatch):
    calls: list[tuple] = []

    def install(frame):
        def fake(symbols, start, end):
            calls.append((symbols, start, end))
            return markets.extract_close(frame)

        monkeypatch.setattr(markets, "_download", fake)

    return install, calls


# --- yfinance frame shape ---------------------------------------------------------------


def test_extract_close_returns_one_column_per_symbol():
    close = markets.extract_close(yahoo_frame({"^GSPC": [1.0, 2.0], "GC=F": [3.0, 4.0]}))
    assert list(close.columns) == ["^GSPC", "GC=F"]


def test_extract_close_handles_a_single_ticker_multiindex():
    close = markets.extract_close(yahoo_frame({"^GSPC": [1.0, 2.0]}))
    assert list(close.columns) == ["^GSPC"]
    assert close["^GSPC"].tolist() == [1.0, 2.0]


@pytest.mark.parametrize("raw", [None, pd.DataFrame()])
def test_extract_close_rejects_empty_replies(raw):
    with pytest.raises(markets.MarketsError, match="no data"):
        markets.extract_close(raw)


def test_extract_close_rejects_a_frame_without_closes():
    with pytest.raises(markets.MarketsError, match="closing prices"):
        markets.extract_close(pd.DataFrame({"Open": [1.0]}))


# --- windows -------------------------------------------------------------------------


def test_preset_windows_relative_to_today():
    today = dt.date(2026, 10, 5)
    assert markets.preset_window("Last 1 year", today) == ("2025-10-05", "2026-10-05")
    assert markets.preset_window("Last 5 years", today) == ("2021-10-05", "2026-10-05")


def test_crisis_presets_are_fixed_windows():
    start, end = markets.preset_window("COVID-19 crash 2020", dt.date(2026, 10, 5))
    assert (start, end) == markets.CRISIS_WINDOWS["COVID-19 crash 2020"]
    assert start < end


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="preset"):
        markets.preset_window("Someday", dt.date(2026, 10, 5))


# --- fetch_prices ----------------------------------------------------------------------


def test_fetch_prices_maps_yahoo_symbols_back_to_keys(downloads):
    install, calls = downloads
    install(yahoo_frame({"^GSPC": [100.0, 101.0, 102.0], "GC=F": [50.0, 51.0, 52.0]}))
    r = markets.fetch_prices(["sp500", "gold"], "2026-09-01", "2026-09-30")
    assert r.ok
    assert list(r.data.columns) == ["date", "sp500", "gold"]
    assert r.data["sp500"].iloc[-1] == 102.0
    assert "Yahoo Finance" in r.source
    assert r.as_of == r.data["date"].iloc[-1].date().isoformat()
    assert set(calls[0][0]) == {"^GSPC", "GC=F"}


def test_end_date_is_inclusive_in_the_request(downloads):
    install, calls = downloads
    install(yahoo_frame({"^GSPC": [1.0, 2.0]}))
    markets.fetch_prices(["sp500"], "2026-09-01", "2026-09-30")
    assert calls[0][2] == "2026-10-01"  # yfinance treats `end` as exclusive


def test_asset_with_no_data_is_dropped_and_reported(downloads):
    install, _ = downloads
    install(yahoo_frame({"^GSPC": [1.0, 2.0, 3.0], "GC=F": [np.nan, np.nan, np.nan]}))
    r = markets.fetch_prices(["sp500", "gold"], "2026-09-01", "2026-09-30")
    assert r.ok
    assert list(r.data.columns) == ["date", "sp500"]
    assert r.meta["missing"] == ["gold"]


def test_all_assets_missing_is_a_failure(downloads):
    install, _ = downloads
    install(yahoo_frame({"^GSPC": [np.nan, np.nan]}))
    r = markets.fetch_prices(["sp500"], "2026-09-01", "2026-09-30")
    assert not r.ok


@pytest.mark.parametrize(
    ("keys", "start", "end"),
    [
        (["made_up"], "2026-01-01", "2026-02-01"),
        ([], "2026-01-01", "2026-02-01"),
        (["sp500"], "2026-02-01", "2026-01-01"),
        (["sp500"], "2026-01-01", "2026-01-01"),
        (["sp500"], "1990-01-01", "2026-01-01"),  # window longer than 20 years
        (["sp500"], "not-a-date", "2026-01-01"),
    ],
)
def test_bad_arguments_fail_without_downloading(downloads, keys, start, end):
    install, calls = downloads
    install(yahoo_frame({"^GSPC": [1.0]}))
    r = markets.fetch_prices(keys, start, end)
    assert not r.ok
    assert r.error
    assert calls == []


def test_download_failures_become_a_safe_result(monkeypatch):
    def boom(symbols, start, end):
        raise RuntimeError("internal detail that should not be shown")

    monkeypatch.setattr(markets, "_download", boom)
    r = markets.fetch_prices(["sp500"], "2026-01-01", "2026-02-01")
    assert not r.ok
    assert "RuntimeError" in r.error
    assert "internal detail" not in r.error


# --- maths -------------------------------------------------------------------------------


def wide(**series: list[float]) -> pd.DataFrame:
    n = max(len(v) for v in series.values())
    df = pd.DataFrame(series)
    df.insert(0, "date", pd.bdate_range("2026-01-01", periods=n))
    return df


def test_normalise_rebases_each_asset_to_100_at_its_first_value():
    out = markets.normalise(wide(sp500=[50.0, 55.0, 60.0], gold=[200.0, 190.0, 210.0]))
    assert out["sp500"].tolist() == pytest.approx([100.0, 110.0, 120.0])
    assert out["gold"].tolist() == pytest.approx([100.0, 95.0, 105.0])


def test_normalise_uses_the_first_valid_value_for_late_starting_assets():
    out = markets.normalise(wide(sp500=[50.0, 55.0, 60.0], gold=[np.nan, 200.0, 220.0]))
    assert out["gold"].iloc[1] == pytest.approx(100.0)
    assert out["gold"].iloc[2] == pytest.approx(110.0)


def test_returns_are_percent_changes_but_the_yield_uses_level_changes():
    out = markets.returns(wide(sp500=[100.0, 110.0, 99.0], bond10y=[5.0, 5.1, 5.0]))
    assert out["sp500"].iloc[0] == pytest.approx(10.0)
    assert out["sp500"].iloc[1] == pytest.approx(-10.0)
    # a % change of a rate is not meaningful: 5.0 -> 5.1 is +0.1 percentage points
    assert out["bond10y"].iloc[0] == pytest.approx(0.1)
    assert out["bond10y"].iloc[1] == pytest.approx(-0.1)


def test_correlation_of_mirrored_series_is_plus_and_minus_one():
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 1, 60))
    df = wide(sp500=list(base), gold=list(base * 2), oil=list(200 - base))
    corr = markets.correlation(df)
    assert corr.loc["sp500", "gold"] == pytest.approx(1.0, abs=1e-6)
    assert corr.loc["sp500", "oil"] < -0.5
    assert corr.loc["sp500", "sp500"] == pytest.approx(1.0)
    assert (corr.values == corr.values.T).all() or np.allclose(corr.values, corr.values.T, equal_nan=True)


def test_correlation_needs_enough_overlapping_days():
    short = markets.correlation(wide(sp500=[1.0, 2.0, 3.0, 4.0], gold=[2.0, 1.0, 3.0, 5.0]))
    assert short.isna().all().all()
