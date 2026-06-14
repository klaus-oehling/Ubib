"""BLS -- U.S. Bureau of Labor Statistics (API v2)."""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from . import _http
from .base import Source


class BLS(Source):
    """BLS series. ``code`` is a single BLS series id (e.g. ``"CUUR0000SA0"``)."""

    id = "bls"
    requires_key = True

    def fetch(self, spec, config):
        key = config.api_key("bls")
        this_year = dt.date.today().year
        payload = json.dumps(
            {
                "seriesid": [spec.code],
                "startyear": str(this_year - 19),
                "endyear": str(this_year),
                "registrationKey": key,
            }
        )
        response = _http.post(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            data=payload,
            headers={"Content-type": "application/json"},
        )
        result = response.json()["Results"]["series"][0]["data"]
        if not result:
            raise ValueError(f"BLS returned no data for {spec.code}")

        records = []
        for row in result:
            period = row["period"]  # M01..M13 or Q01..Q05
            if period in ("M13", "Q05"):
                continue  # annual averages
            month = int(period[1:]) * (3 if period.startswith("Q") else 1)
            records.append((dt.datetime(int(row["year"]), month, 1), float(row["value"])))
        index, values = zip(*records)
        return self._series(values, index, spec.name).sort_index()
