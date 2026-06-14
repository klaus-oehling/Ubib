"""World Bank -- World Development Indicators API."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class WorldBank(Source):
    """World Bank indicator.

    ``code`` is the 3-letter country code immediately followed by the indicator
    code, e.g. ``"BRANY.GDP.MKTP.CD"`` (country ``BRA`` + ``NY.GDP.MKTP.CD``).
    """

    id = "worldbank"

    def fetch(self, spec, config):
        country, indicator = str(spec.code)[:3], str(spec.code)[3:]
        url = (
            f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
            "?format=json&per_page=20000"
        )
        payload = _http.get(url, verify=False).json()
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            raise ValueError(f"World Bank returned no data for {spec.code}")
        data = pd.DataFrame(payload[1])
        data = data.dropna(subset=["value"])
        index = pd.to_datetime(data["date"], format="%Y")
        return self._series(data["value"], index, spec.name)
