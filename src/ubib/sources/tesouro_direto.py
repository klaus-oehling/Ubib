"""Tesouro Direto -- bond price/yield averages. FRAGILE: validate live."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _http
from ._excel import read_excel
from .base import Source


class TesouroDireto(Source):
    """Tesouro Direto workbook.

    ``code`` is the sisweb file id. ``spec.name`` should start with ``"PU"`` or
    ``"Yield"`` to select the average computed from the morning columns.
    """

    id = "tesouro_direto"

    def fetch(self, spec, config):
        url = f"https://sisweb.tesouro.gov.br/apex/cosis/sistd/obtem_arquivo/{spec.code}"
        content = _http.get(url, verify=False).content
        frame = read_excel(content, sheet=spec.params.get("sheet", 0))

        frame = frame.set_index(frame.columns[0])
        frame.columns = frame.iloc[0, :]
        frame = frame.iloc[1:, :]
        frame.index = pd.to_datetime(frame.index, dayfirst=True, errors="coerce")
        frame = frame[~frame.index.duplicated(keep="first")]
        pu = frame[["PU Base Manha", "PU Venda Manha"]].astype(float).mean(axis=1)
        yld = frame[["Taxa Compra Manha", "Taxa Venda Manha"]].astype(float).mean(axis=1)

        chosen = pu if spec.name.split("average")[0].strip() == "PU" else yld
        return self._series(chosen.values, chosen.index, spec.name).sort_index()
