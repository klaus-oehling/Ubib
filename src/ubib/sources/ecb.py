"""ECB -- European Central Bank Data Portal (data-api.ecb.europa.eu).

Replaces the legacy ``bce`` source, which used the decommissioned SDW
(``sdw-wsrest.ecb.europa.eu``) endpoint.
"""

from __future__ import annotations

import io

import pandas as pd

from . import _http
from .base import Source


class ECB(Source):
    """ECB series. ``code`` is ``FLOW/KEY`` (e.g. ``"EXR/M.USD.EUR.SP00.A"``)."""

    id = "ecb"

    def fetch(self, spec, config):
        flow, _, key = str(spec.code).split(";")[0].partition("/")
        url = f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
        response = _http.get(url, params={"format": "csvdata"})
        data = pd.read_csv(io.StringIO(response.text))
        data = data[["TIME_PERIOD", "OBS_VALUE"]].dropna()
        index = pd.to_datetime(data["TIME_PERIOD"])
        return self._series(data["OBS_VALUE"], index, spec.name).sort_index()
