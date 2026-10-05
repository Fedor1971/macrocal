import pytest

from macrocal.text import escape_markdown, sanitize_answer


def test_escape_neutralises_images_and_links():
    out = escape_markdown("![x](http://evil.example/p.png?q=1) and [click](javascript:alert(1))")
    assert "![" not in out
    assert "](" not in out


@pytest.mark.parametrize("raw", ["Federal Statistics Office", "St. Louis Fed", "US CPI 3.4% YoY, 2026-10-05"])
def test_escape_keeps_ordinary_text_readable(raw):
    assert escape_markdown(raw) == raw


def test_escape_handles_none_and_non_strings():
    assert escape_markdown(None) == ""
    assert escape_markdown(42) == "42"


def test_sanitize_answer_removes_markdown_images():
    out = sanitize_answer("Unemployment is 4.2%. ![t](https://evil.example/x.png?data=secret) Done.")
    assert "evil.example" not in out
    assert "4.2%" in out


def test_sanitize_answer_removes_html_tags_but_keeps_text():
    out = sanitize_answer('<img src="http://evil/x"> Rate <b>4.2%</b><script>alert(1)</script>')
    assert "<" not in out
    assert "Rate" in out and "4.2%" in out
    assert "alert" not in out


def test_sanitize_answer_keeps_normal_markdown():
    text = "**Rate** is 4.2%:\n\n- item one\n- item two\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    assert sanitize_answer(text) == text


def test_sanitize_answer_keeps_plain_links():
    assert "[BLS](https://www.bls.gov)" in sanitize_answer("See [BLS](https://www.bls.gov).")
