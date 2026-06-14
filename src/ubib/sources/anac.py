"""ANAC -- Agencia Nacional de Aviacao Civil (Brazil). FRAGILE: validate live."""

from __future__ import annotations

import pandas as pd
from bs4 import BeautifulSoup

from . import _http
from ._excel import extract_from_zip, read_excel
from .base import Source


class ANAC(Source):
    """ANAC air-transport demand/supply data (published as a zipped workbook).

    ``params`` carries ``sheet``, ``skiprows``, ``nrows``, ``cols`` and the
    monthly ``start`` date used to rebuild the flattened series' index.
    """

    id = "anac"

    def fetch(self, spec, config):
        url = ("https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/"
               "mercado-do-transporte-aereo")
        soup = BeautifulSoup(_http.get(url, verify=False).text, "html.parser")
        anchor = soup.find("a", href=True)
        if anchor is None:
            raise ValueError("ANAC: no download link found on data page")
        content = extract_from_zip(_http.get(anchor["href"], verify=False).content, ".xlsx")
        frame = read_excel(
            content,
            sheet=spec.params.get("sheet", 0),
            skiprows=spec.params.get("skiprows", 0),
            nrows=spec.params.get("nrows"),
            usecols=spec.params.get("cols"),
            index_col=0,
        )
        flat = frame.values.flatten("C")
        index = pd.date_range(
            start=spec.params.get("start", "2000-01"), periods=len(flat), freq="M"
        )
        return self._series(flat, index, spec.name)
