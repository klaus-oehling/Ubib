"""Statistics Canada -- Web Data Service (WDS)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class StatCan(Source):
    """Statistics Canada vector series. ``code`` is a vector id (e.g. ``"v41690973"``)."""

    id = "statcan"

    def fetch(self, spec, config):
        vector = str(spec.code).lstrip("vV")
        url = (
            "https://www150.statcan.gc.ca/t1/wds/rest/"
            "getDataFromVectorsAndLatestNPeriods"
        )
        body = [{"vectorId": int(vector), "latestN": 600}]
        payload = _http.post(url, json=body, verify=False).json()
        points = payload[0]["object"]["vectorDataPoint"]
        data = pd.DataFrame(points)
        index = pd.to_datetime(data["refPer"])
        return self._series(data["value"], index, spec.name).sort_index()
