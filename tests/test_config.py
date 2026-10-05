from macrocal.config import get_secret


def test_returns_env_value(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "abc123")
    assert get_secret("FRED_API_KEY") == "abc123"


def test_missing_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert get_secret("GEMINI_API_KEY") is None


def test_blank_value_counts_as_missing(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "   ")
    assert get_secret("FRED_API_KEY") is None


def test_value_is_stripped(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "  abc123\n")
    assert get_secret("FRED_API_KEY") == "abc123"


def test_never_raises_without_streamlit_secrets_file(monkeypatch):
    monkeypatch.delenv("SOME_UNSET_KEY", raising=False)
    assert get_secret("SOME_UNSET_KEY") is None
