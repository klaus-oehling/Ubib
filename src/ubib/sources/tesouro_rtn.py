"""Tesouro Nacional -- Resultado do Tesouro Nacional (RTN). FRAGILE: validate live."""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import _http
from ._excel import read_excel, series_from_frame
from .base import Source


class TesouroRTN(Source):
    """RTN bulletin annex. ``params`` carries ``sheet``/``value_col``/``date_col``."""

    id = "tesouro_rtn"

    def fetch(self, spec, config):
        page = _http.get(
            "https://www.tesourotransparente.gov.br/publicacoes/"
            "boletim-resultado-do-tesouro-nacional-rtn/",
            verify=False,
        )
        soup = BeautifulSoup(page.content, "html.parser")
        link = soup.select(".anexos:has(a)")[0].find_all("a")[2]["href"]
        inner = _http.get(link, verify=False)
        frame_url = BeautifulSoup(inner.content, "html.parser").frame["src"]
        content = _http.get(frame_url, verify=False).content
        frame = read_excel(content, sheet=spec.params.get("sheet", 0), skiprows=4, index_col=0)
        return series_from_frame(
            frame.T, spec.params.get("value_col", 1), spec.params.get("date_col", 0), spec.name
        )
