"""Eurostat -- dissemination API (JSON-stat)."""

from __future__ import annotations

import json

import pandas as pd

from . import _http
from .base import Source

_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


class Eurostat(Source):
    """Eurostat dataset.

    ``code`` is a JSON object: ``{"table": "prc_hicp_midx", "params": {...}}``.
    The ``params`` must select a single value on every non-time dimension so the
    result reduces to one series.
    """

    id = "eurostat"

    def fetch(self, spec, config):
        spec_code = json.loads(spec.code)
        table = spec_code["table"]
        params = {"format": "JSON", **spec_code.get("params", {})}
        payload = _http.get(f"{_BASE}/{table}", params=params).json()

        time_dim = payload["dimension"]["time"]["category"]["index"]
        # JSON-stat index -> period; values keyed by flattened position.
        periods = sorted(time_dim, key=lambda p: time_dim[p])
        position_to_period = {time_dim[p]: p for p in periods}

        values = payload["value"]
        records = {
            position_to_period[int(pos)]: val
            for pos, val in values.items()
            if int(pos) in position_to_period
        }
        if not records:
            raise ValueError(f"Eurostat returned no data for {table}")
        series = pd.Series(records)
        index = pd.to_datetime(series.index.str.replace("M", "-"), errors="coerce")
        series.index = index
        return self._series(series.values, series.index, spec.name).sort_index()
