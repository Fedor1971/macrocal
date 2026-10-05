import pandas as pd

from macrocal import events


def raw_calendar() -> pd.DataFrame:
    # Shape confirmed live in ecocal-dashboard: Start is a MM/DD/YYYY HH:MM:SS string.
    return pd.DataFrame(
        {
            "Id": ["b", "a", "c"],
            "Start": ["10/07/2026 14:30:00", "10/06/2026 08:00:00", "10/07/2026 09:00:00"],
            "Name": ["Core CPI (MoM)", "Unemployment Rate", "ECB Speech"],
            "Impact": ["HIGH", "MEDIUM", "LOW"],
            "Currency": ["USD", "USD", "EUR"],
        }
    )


def test_shape_calendar_parses_start_and_sorts_ascending():
    shaped = events.shape_calendar(raw_calendar())
    assert pd.api.types.is_datetime64_any_dtype(shaped["Start"])
    assert list(shaped["Id"]) == ["a", "c", "b"]


def test_shape_calendar_empty_input_keeps_columns():
    shaped = events.shape_calendar(pd.DataFrame())
    assert list(shaped.columns) == events.BASIC_COLUMNS
    assert shaped.empty


def test_filter_events_by_impact_and_currency():
    shaped = events.shape_calendar(raw_calendar())
    out = events.filter_events(shaped, impacts=["HIGH", "MEDIUM"], currencies=["USD"])
    assert set(out["Id"]) == {"a", "b"}


def test_filter_events_empty_selection_returns_no_rows():
    shaped = events.shape_calendar(raw_calendar())
    assert events.filter_events(shaped, impacts=[], currencies=["USD"]).empty


def test_clean_description_strips_tags_and_scripts():
    html = '<p>Inflation <b>rose</b></p><script>alert(1)</script><a href="http://x">link</a>'
    text = events.clean_description(html)
    assert "<" not in text
    assert "alert" not in text
    assert "Inflation rose" in text


def test_clean_description_handles_none_and_entities():
    assert events.clean_description(None) == ""
    assert events.clean_description("Fed &amp; ECB") == "Fed & ECB"


def test_fetch_calendar_wraps_failures_in_result(monkeypatch):
    def boom(start, end):
        raise RuntimeError("fxstreet down")

    monkeypatch.setattr(events, "_fetch_calendar_raw", boom)
    r = events.fetch_calendar("2026-10-06", "2026-10-13")
    assert not r.ok
    assert "fxstreet down" in r.error
    assert r.source == events.SOURCE


def test_fetch_calendar_success_returns_shaped_frame(monkeypatch):
    monkeypatch.setattr(events, "_fetch_calendar_raw", lambda s, e: raw_calendar())
    r = events.fetch_calendar("2026-10-06", "2026-10-13")
    assert r.ok
    assert r.as_of == "2026-10-06 to 2026-10-13"
    assert len(r.data) == 3


def test_fetch_event_details_wraps_failures_in_result(monkeypatch):
    def boom(event_id):
        raise RuntimeError("timeout")

    monkeypatch.setattr(events, "_fetch_event_details_raw", boom)
    r = events.fetch_event_details("abc")
    assert not r.ok
    assert "timeout" in r.error


def test_fetch_event_details_success_keeps_dict(monkeypatch):
    payload = {"actual": 4.2, "consensus": 4.1, "previous": 4.1, "countryCode": "US"}
    monkeypatch.setattr(events, "_fetch_event_details_raw", lambda i: payload)
    r = events.fetch_event_details("abc")
    assert r.ok
    assert r.data["countryCode"] == "US"
