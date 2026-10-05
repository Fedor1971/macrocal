"""Common return type for every data loader, so panels can degrade without try/except in UI code."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Result:
    data: pd.DataFrame | None
    error: str | None = None
    source: str = ""
    as_of: str = ""  # data date as reported by the source, not "now"

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None and not self.data.empty

    @classmethod
    def fail(cls, error: str, source: str = "") -> Result:
        return cls(None, error=error, source=source)
