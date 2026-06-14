"""ABS -- Australian Bureau of Statistics (SDMX-JSON)."""

from __future__ import annotations

import json

import pandas as pd

from . import _http
from .base import Source


class ABS(Source):
    """ABS series. ``code`` is JSON ``{"url": ..., "post_url": ..., "freq": "M|Q|S"}``."""

    id = "abs"

    def fetch(self, spec, config):
        c = json.loads(spec.code)
        headers = {"accept": "application/vnd.sdmx.data+json"}
        payload = _http.get(c["url"], headers=headers, verify=False).json()
        time_values = payload["data"]["structure"]["dimensions"]["observation"][0]["values"]
        dates = [v["id"] for v in time_values]
        observations = payload["data"]["dataSets"][0]["series"][c["post_url"]]["observations"]
        values = pd.Series({int(k): obs[0] for k, obs in observations.items()}).sort_index()
        values.index = dates

        freq = c.get("freq", "M").upper()
        if freq == "S":  # semi-annual coded as YYYY-S1/S2
            ym = [f"{d[:4]}-{int(d[-1]) * 6}" for d in values.index]
            index = pd.to_datetime(ym, format="%Y-%m") + pd.offsets.MonthEnd(0)
        else:
            index = pd.to_datetime(values.index) + pd.offsets.MonthEnd(0)
        return self._series(values.values, index, spec.name).sort_index()
