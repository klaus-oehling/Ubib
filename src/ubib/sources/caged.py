"""CAGED / Novo CAGED -- formal employment (Brazil, MTE/PDET). FRAGILE: validate live."""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import _http
from ._excel import read_excel, series_from_frame
from .base import Source


class CAGED(Source):
    """Novo CAGED workbook discovered from the PDET page.

    ``params`` carries ``sheet``/``value_col``/``date_col``.
    """

    id = "caged"

    def fetch(self, spec, config):
        base = "http://pdet.mte.gov.br"
        soup = BeautifulSoup(_http.get(f"{base}/novo-caged", verify=False).content,
                            "html.parser")
        anchors = soup.find_all("ul", class_="n5")[0].find_all("a")
        link = base + anchors[spec.params.get("link_index", 2)]["href"]
        frame = read_excel(_http.get(link, verify=False).content,
                          sheet=spec.params.get("sheet", 0))
        return series_from_frame(
            frame, spec.params.get("value_col", 1), spec.params.get("date_col", 0), spec.name
        )
