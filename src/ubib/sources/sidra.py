"""IBGE -- SIDRA (Sistema IBGE de Recuperacao Automatica)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


def _parse_period(values: pd.Series) -> pd.DatetimeIndex:
    text = values.astype(str)
    length = text.str.len().max()
    if length >= 6:
        return pd.to_datetime(text, format="%Y%m") + pd.offsets.MonthEnd(0)
    return pd.to_datetime(text, format="%Y")


class SIDRA(Source):
    """SIDRA table values. ``code`` is the SIDRA query path after ``/values/``.

    The first element of the JSON response is a header row and is dropped.
    """

    id = "sidra"

    def fetch(self, spec, config):
        code = str(spec.code).split(";")[0].strip()
        url = f"https://apisidra.ibge.gov.br/values/{code}"
        response = _http.get(url, verify=False)
        records = response.json()
        if not records or len(records) < 2:
            raise ValueError(f"SIDRA returned no data for {code}")
        data = pd.DataFrame(records[1:])
        index = _parse_period(data["D1C"])
        return self._series(data["V"], index, spec.name)
