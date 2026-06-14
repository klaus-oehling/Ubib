"""Cielo -- ICVA retail index (investor-relations page). FRAGILE: validate live."""

from __future__ import annotations

import pandas as pd
from bs4 import BeautifulSoup

from . import _http
from ._excel import read_excel
from .base import Source


class Cielo(Source):
    """Cielo ICVA spreadsheet linked from the IR page.

    ``params['link_text']`` (optional) narrows which anchor to follow.
    """

    id = "cielo"

    def fetch(self, spec, config):
        url = ("https://ri.cielo.com.br/en/financial-information/"
               "indice-cielo-do-varejo-ampliado-icva/")
        soup = BeautifulSoup(_http.get(url, verify=False).text, "html.parser")
        match = spec.params.get("link_text", ".xls")
        link = next((a["href"] for a in soup.find_all("a", href=True)
                     if match in a["href"]), None)
        if not link:
            raise ValueError("Cielo: no ICVA spreadsheet link found")
        frame = read_excel(_http.get(link, verify=False).content)
        index = pd.to_datetime(frame.iloc[:, 0])
        return self._series(frame.iloc[:, spec.params.get("value_col", 1)], index,
                            spec.name).sort_index()
