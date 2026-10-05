import pytest

from macrocal.mapping import series_for_event

# Names below are real fxstreet USD event names (collected 2026-10-05).


@pytest.mark.parametrize(
    ("name", "series"),
    [
        ("Consumer Price Index (MoM)", "us_cpi"),
        ("Consumer Price Index (YoY)", "us_cpi"),
        ("Consumer Price Index n.s.a (MoM)", "us_cpi"),
        ("Producer Price Index (MoM)", "us_ppi"),
        ("Producer Price Index (YoY)", "us_ppi"),
        ("Unemployment Rate", "us_unemployment_rate"),
        ("Nonfarm Payrolls", "us_nonfarm_payrolls"),
        ("Labor Force Participation Rate", "us_labor_participation"),
        ("Average Hourly Earnings (MoM)", "us_avg_hourly_earnings"),
        ("Average Hourly Earnings (YoY)", "us_avg_hourly_earnings"),
        ("Retail Sales (MoM)", "us_retail_sales"),
        ("Retail Sales (YoY)", "us_retail_sales"),
    ],
)
def test_known_usd_releases_map_to_their_series(name, series):
    assert series_for_event(name, "USD") == series


@pytest.mark.parametrize(
    "name",
    [
        # look-alikes whose headline is a different measure than our series
        "Consumer Price Index ex Food & Energy (MoM)",
        "Consumer Price Index ex Food & Energy (YoY)",
        "Consumer Price Index Core s.a",
        "Producer Price Index ex Food & Energy (MoM)",
        "Retail Sales ex Autos (MoM)",
        "Retail Sales Control Group",
        "Nonfarm Payrolls Benchmark Revision",
        "Nonfarm Productivity",
        "U6 Underemployment Rate",
        "ADP Employment Change",
        "Initial Jobless Claims",
        "ISM Manufacturing Prices Paid",
        "Import Price Index (MoM)",
        "Core Personal Consumption Expenditures - Price Index (MoM)",
        "FOMC Minutes",
        "",
    ],
)
def test_lookalikes_and_unrelated_events_are_not_mapped(name):
    assert series_for_event(name, "USD") is None


@pytest.mark.parametrize("currency", ["EUR", "GBP", "CAD", "AUD", "", None])
def test_non_usd_events_are_never_mapped(currency):
    assert series_for_event("Unemployment Rate", currency) is None
    assert series_for_event("Consumer Price Index (YoY)", currency) is None


def test_matching_ignores_case_and_extra_whitespace():
    assert series_for_event("  unemployment   RATE ", "USD") == "us_unemployment_rate"
