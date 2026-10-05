import pandas as pd

from macrocal.result import Result


def test_result_with_data_is_ok():
    r = Result(pd.DataFrame({"a": [1]}), source="BLS", as_of="2026-09")
    assert r.ok
    assert r.error is None


def test_result_with_error_is_not_ok():
    r = Result(None, error="boom", source="economy-intel")
    assert not r.ok


def test_result_with_empty_frame_is_not_ok():
    assert not Result(pd.DataFrame()).ok


def test_result_with_dict_payload_is_ok():
    assert Result({"actual": 1}).ok
    assert not Result({}).ok


def test_result_meta_defaults_to_empty_dict_per_instance():
    a, b = Result(None), Result(None)
    assert a.meta == {} and a.meta is not b.meta


def test_result_is_immutable():
    r = Result(None, error="x")
    try:
        r.error = "y"
    except AttributeError:
        return
    raise AssertionError("Result should be frozen")


def test_fail_helper_builds_error_result():
    r = Result.fail("no key", source="FRED")
    assert not r.ok
    assert r.error == "no key"
    assert r.source == "FRED"
    assert r.data is None
