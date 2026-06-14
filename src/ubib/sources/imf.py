"""IMF -- International Monetary Fund.

NOTE: the IMF migrated its data platform in 2025. This adapter targets the
legacy SDMX-JSON CompactData service that many catalogs still reference; if the
IMF fully retires it, point ``code`` at the new SDMX 2.1 endpoint instead. Flag
this source for live verification.
"""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class IMF(Source):
    """IMF series. ``code`` is ``DATASET/KEY`` (e.g. ``"IFS/M.US.PMP_IX"``)."""

    id = "imf"

    def fetch(self, spec, config):
        url = f"http://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/{spec.code}"
        payload = _http.get(url, verify=False).json()
        obs = payload["CompactData"]["DataSet"]["Series"]["Obs"]
        data = pd.DataFrame(obs)
        index = pd.to_datetime(data["@TIME_PERIOD"])
        return self._series(data["@OBS_VALUE"], index, spec.name).sort_index()
