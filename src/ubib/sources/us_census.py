"""U.S. Census Bureau -- Economic Indicators Time Series (EITS)."""

from __future__ import annotations

import json

import pandas as pd

from . import _http
from .base import Source


class USCensus(Source):
    """US Census EITS series.

    ``code`` is a JSON object with the EITS query fields: ``table_code``,
    ``category_code``, ``data_type_code``, ``seasonally_adj``, ``error_data``,
    ``time_slot_id`` and ``for``.
    """

    id = "us_census"
    requires_key = True

    def fetch(self, spec, config):
        key = config.api_key("us_census")
        c = json.loads(spec.code)
        base = f"https://api.census.gov/data/timeseries/eits/{c['table_code']}"
        query = {
            "get": "cell_value,category_code",
            "time_slot_id": c["time_slot_id"],
            "error_data": c["error_data"],
            "for": c["for"],
            "seasonally_adj": c["seasonally_adj"],
            "data_type_code": c["data_type_code"],
            "time": "from 1960",
            "key": key,
        }
        if c.get("category_code"):
            query["category_code"] = c["category_code"]
        rows = _http.get(base, params=query, verify=False).json()
        data = pd.DataFrame(rows[1:], columns=rows[0])
        index = pd.to_datetime(data["time"])
        return self._series(data["cell_value"], index, spec.name).sort_index()
