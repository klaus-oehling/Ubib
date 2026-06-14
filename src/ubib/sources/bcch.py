"""Banco Central de Chile -- SIETE REST web service."""

from __future__ import annotations

import json

import pandas as pd

from . import _http
from .base import Source


class BCCh(Source):
    """Central Bank of Chile series.

    ``code`` is JSON ``{"series_code": ...}``. Requires ``bcch_user`` and
    ``bcch_password`` in the config ``[credentials]`` section.
    """

    id = "bcch"

    def fetch(self, spec, config):
        user = config.credential("bcch_user")
        password = config.credential("bcch_password")
        if not user or not password:
            raise RuntimeError("Missing bcch_user/bcch_password in config [credentials].")
        c = json.loads(spec.code)
        url = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
        params = {
            "user": user,
            "pass": password,
            "function": "GetSeries",
            "timeseries": c["series_code"],
        }
        payload = _http.get(url, params=params, verify=False).json()
        obs = payload["Series"]["Obs"]
        data = pd.DataFrame(obs)
        index = pd.to_datetime(data["indexDateString"], format="%d-%m-%Y")
        values = pd.to_numeric(data["value"], errors="coerce")
        return self._series(values, index, spec.name).sort_index()
