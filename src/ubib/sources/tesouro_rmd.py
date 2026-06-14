"""Tesouro Nacional -- Relatorio Mensal da Divida (RMD). FRAGILE: validate live."""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import _http
from ._excel import extract_from_zip, read_excel, series_from_frame
from .base import Source


class TesouroRMD(Source):
    """Monthly public-debt report annex.

    ``params`` carries ``sheet``/``value_col``/``date_col`` for the chosen table.
    """

    id = "tesouro_rmd"

    def fetch(self, spec, config):
        page = _http.get(
            "https://www.tesourotransparente.gov.br/publicacoes/"
            "relatorio-mensal-da-divida-rmd/",
            verify=False,
        )
        soup = BeautifulSoup(page.content, "html.parser")
        link = soup.select(".anexos:has(a)")[0].find_all("a")[0]["href"]
        inner = _http.get(link, verify=False)
        frame_url = BeautifulSoup(inner.content, "html.parser").frame["src"]
        content = _http.get(frame_url, verify=False).content
        content = extract_from_zip(content, spec.params.get("member_suffix", ".xlsx"))
        frame = read_excel(content, sheet=spec.params.get("sheet", 0))
        return series_from_frame(
            frame, spec.params.get("value_col", 1), spec.params.get("date_col", 0), spec.name
        )
