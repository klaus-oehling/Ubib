"""INEGI -- Instituto Nacional de Estadistica y Geografia (Mexico)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class INEGI(Source):
    """INEGI indicator. ``code`` is the indicator id. Requires an API token."""

    id = "inegi"
    requires_key = True

    def fetch(self, spec, config):
        token = config.api_key("inegi")
        url = (
            "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/"
            f"INDICATOR/{spec.code}/en/0700/false/BIE/2.0/{token}?type=json"
        )
        series = _http.get(url, verify=False).json()["Series"][0]
        data = pd.DataFrame(series["OBSERVATIONS"])
        index = pd.to_datetime(data["TIME_PERIOD"])
        return self._series(data["OBS_VALUE"], index, spec.name).sort_index()
