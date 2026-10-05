"""Calendar event -> macro series. Explicit full-name rules, USD only.

Wrong-series is worse than no-series, so every rule matches the whole event name. Variants whose
headline is a different measure than our series (Core CPI, PPI ex Food & Energy, Retail Sales ex
Autos, ...) are deliberately left unmapped. Names are real fxstreet event names (2026-10-05).
"""

from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), series)
    for p, series in [
        (r"consumer price index (n\.s\.a )?\((mom|yoy)\)", "us_cpi"),
        (r"producer price index \((mom|yoy)\)", "us_ppi"),
        (r"unemployment rate", "us_unemployment_rate"),
        (r"nonfarm payrolls", "us_nonfarm_payrolls"),
        (r"labor force participation rate", "us_labor_participation"),
        (r"average hourly earnings \((mom|yoy)\)", "us_avg_hourly_earnings"),
        (r"retail sales \((mom|yoy)\)", "us_retail_sales"),
    ]
]


def series_for_event(name: str | None, currency: str | None) -> str | None:
    if currency != "USD" or not name:
        return None
    normalised = " ".join(name.split())
    for pattern, series in _RULES:
        if pattern.fullmatch(normalised):
            return series
    return None
