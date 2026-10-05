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
