"""FRED -- Federal Reserve Bank of St. Louis."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class FRED(Source):
    """FRED series. ``code`` is the FRED series id (e.g. ``"GDP"``).

    Requires a free API key in ``config.api_keys['fred']``.
    """

    id = "fred"
    requires_key = True

    def fetch(self, spec, config):
        key = config.api_key("fred")
        if not key:
            raise RuntimeError("Missing FRED API key (set api_keys.fred in config).")
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={spec.code}&api_key={key}&file_type=json"
        )
        observations = _http.get(url).json().get("observations", [])
        if not observations:
            raise ValueError(f"FRED returned no data for {spec.code}")
        data = pd.DataFrame(observations)
        data = data[data["value"] != "."]
        return self._series(data["value"], data["date"], spec.name)
