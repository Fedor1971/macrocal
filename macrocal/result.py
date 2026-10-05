"""Common return type for every data loader, so panels can degrade without try/except in UI code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Result:
    data: Any = None  # a DataFrame for series/tables, a dict for single-record payloads
    error: str | None = None
    source: str = ""
    as_of: str = ""  # data date as reported by the source, not "now"

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None and len(self.data) > 0

    @classmethod
    def fail(cls, error: str, source: str = "") -> Result:
        return cls(None, error=error, source=source)
