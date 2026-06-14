"""Banco de Mexico -- SIE API."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _http
from .base import Source


class Banxico(Source):
    """Banxico series. ``code`` is the series id (e.g. ``"SF43718"``)."""

    id = "banxico"
    requires_key = True

    def fetch(self, spec, config):
        token = config.api_key("banxico")
        url = (
            "https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
            f"{spec.code}/datos"
        )
        payload = _http.get(url, params={"token": token}, verify=False).json()
        data = pd.DataFrame(payload["bmx"]["series"][0]["datos"])
        index = pd.to_datetime(data["fecha"], format="%d/%m/%Y")
        values = pd.to_numeric(data["dato"].replace("N/E", np.nan), errors="coerce")
        return self._series(values, index, spec.name).sort_index()
