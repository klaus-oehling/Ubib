"""ONS -- Office for National Statistics (United Kingdom)."""

from __future__ import annotations

import json

import pandas as pd

from . import _http
from .base import Source


class ONS(Source):
    """ONS series. ``code`` is JSON ``{"dataset_id": ..., "timeseries_id": ..., "freq": "M|Q|A"}``."""

    id = "ons"

    def fetch(self, spec, config):
        c = json.loads(spec.code)
        url = (
            f"https://api.ons.gov.uk/timeseries/{c['timeseries_id']}"
            f"/dataset/{c['dataset_id']}/data"
        )
        payload = _http.get(url, verify=False).json()
        freq = c.get("freq", "M").upper()
        block = {"Q": "quarters", "M": "months", "A": "years"}.get(freq, "years")
        data = pd.json_normalize(payload[block])

        if freq == "Q":
            ym = data["date"].apply(lambda x: f"{x[:4]}-{int(x[-1]) * 3}")
            index = pd.to_datetime(ym, format="%Y-%m") + pd.offsets.MonthEnd(0)
        elif freq == "M":
            index = pd.to_datetime(data["date"], format="%Y %b") + pd.offsets.MonthEnd(0)
        else:
            index = pd.to_datetime(data["date"], format="%Y") + pd.offsets.MonthEnd(0)
        return self._series(data["value"], index, spec.name).sort_index()
