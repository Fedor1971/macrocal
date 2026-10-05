"""Live smoke tests: hit the real third-party services. Run manually: pytest -m live -q"""

import pytest

from macrocal import intel

pytestmark = pytest.mark.live


def test_intel_us_series_live():
    r = intel.us_series("us_unemployment_rate")
    assert r.ok, r.error
    assert len(r.data) >= 12
    assert r.data["value"].between(0, 30).all()
    assert r.as_of


def test_intel_bad_country_is_a_clean_error_live():
    with pytest.raises(intel.IntelError, match="No data for country"):
        intel.call_tool("country_profile", {"country": "ZZZ"})


def test_intel_world_bank_loaders_live():
    profile = intel.country_profile("NLD")
    assert profile.ok, profile.error
    unemployment_in_profile = profile.data.set_index("key").loc["unemployment", "value"]

    compare = intel.compare_countries("unemployment", ["NLD", "DEU", "FRA"])
    assert compare.ok, compare.error
    assert len(compare.data) == 3
    # same cross-endpoint consistency check as the manual test on 2026-10-05
    nld = compare.data.set_index("country").loc["Netherlands", "value"]
    assert nld == unemployment_in_profile

    history = intel.country_indicator("NLD", "inflation", years=5)
    assert history.ok, history.error
    assert history.data["year"].is_monotonic_increasing


def test_intel_wb_indicator_list_has_not_drifted_live():
    listed = intel.call_tool("list_indicators", {})["world_bank"]
    assert intel.WB_INDICATORS == listed
