import json
from pathlib import Path

import pytest
import requests

from macrocal import fred

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fred_fedfunds.json").read_text(encoding="utf-8"))
KEY = "sekrit-key-1234567890abcdef"


class FakeResponse:
    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", KEY)


def test_available_follows_the_key(monkeypatch):
    assert fred.available() is False
    monkeypatch.setenv("FRED_API_KEY", KEY)
    assert fred.available() is True


def test_without_a_key_it_fails_cleanly_and_makes_no_request(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("must not call FRED without a key")

    monkeypatch.setattr(fred.requests, "get", forbidden)
    r = fred.fred_series("FEDFUNDS")
    assert not r.ok
    assert "FRED_API_KEY" in r.error


def test_parses_observations_drops_missing_and_sorts(with_key, monkeypatch):
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: FakeResponse(FIXTURE))
    r = fred.fred_series("FEDFUNDS")
    assert r.ok
    assert list(r.data.columns) == ["date", "value"]
    assert len(r.data) == 5  # one "." dropped
    assert r.data["date"].is_monotonic_increasing
    assert r.data["value"].iloc[-1] == pytest.approx(3.90)
    assert r.as_of == "2026-08-01"
    assert "FRED" in r.source
    assert r.meta["label"] == fred.SERIES["FEDFUNDS"]


def test_sends_the_key_as_a_query_parameter_only(with_key, monkeypatch):
    seen = {}

    def get(url, params=None, timeout=None, **kw):
        seen.update(url=url, params=params, timeout=timeout)
        return FakeResponse(FIXTURE)

    monkeypatch.setattr(fred.requests, "get", get)
    fred.fred_series("GS10")
    assert KEY not in seen["url"]
    assert seen["params"]["api_key"] == KEY
    assert seen["params"]["series_id"] == "GS10"
    assert seen["timeout"]


def test_unknown_series_is_rejected_without_a_request(with_key, monkeypatch):
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: pytest.fail("no request expected"))
    r = fred.fred_series("NOT_A_SERIES")
    assert not r.ok
    assert "Unknown FRED series" in r.error


@pytest.mark.parametrize(
    "failure",
    [
        # requests puts the full URL, api_key included, in exception text
        requests.HTTPError(f"400 Client Error for url: https://api.stlouisfed.org/x?api_key={KEY}"),
        requests.ConnectionError(f"HTTPSConnectionPool(...): Max retries exceeded with url: /x?api_key={KEY}"),
        requests.Timeout(f"timed out: ...?api_key={KEY}"),
    ],
)
def test_the_api_key_never_appears_in_an_error(with_key, monkeypatch, failure):
    def get(*a, **k):
        raise failure

    monkeypatch.setattr(fred.requests, "get", get)
    r = fred.fred_series("FEDFUNDS")
    assert not r.ok
    assert KEY not in r.error
    assert "api_key" not in r.error


def test_a_bad_status_reports_the_code_not_the_body_if_it_echoes_the_key(with_key, monkeypatch):
    body = {"error_code": 400, "error_message": f"Bad Request. api_key={KEY} is not registered."}
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: FakeResponse(body, status=400))
    r = fred.fred_series("FEDFUNDS")
    assert not r.ok
    assert "400" in r.error
    assert KEY not in r.error


def test_empty_observations_is_a_clean_failure(with_key, monkeypatch):
    monkeypatch.setattr(fred.requests, "get", lambda *a, **k: FakeResponse({"observations": []}))
    r = fred.fred_series("FEDFUNDS")
    assert not r.ok
