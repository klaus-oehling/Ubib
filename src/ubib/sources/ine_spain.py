"""INE -- Instituto Nacional de Estadistica (Spain)."""

from __future__ import annotations

import json

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import _http
from .base import Source


class INESpain(Source):
    """INE Spain series. ``code`` is JSON ``{"series_code": ..., "params": {...}}``."""

    id = "ine_spain"

    def fetch(self, spec, config):
        c = json.loads(spec.code)
        url = f"https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{c['series_code']}"
        payload = _http.get(url, params=c.get("params", {}), verify=False).json()
        data = pd.DataFrame(payload["Data"])[["Fecha", "Valor"]]
        index = pd.to_datetime(data["Fecha"], unit="ms") + relativedelta(months=1)
        return self._series(data["Valor"], index, spec.name).sort_index()
