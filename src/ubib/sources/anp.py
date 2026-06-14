"""ANP -- Agencia Nacional do Petroleo (Brazil). FRAGILE: validate live."""

from __future__ import annotations

from bs4 import BeautifulSoup

from . import _http
from ._excel import read_excel, series_from_frame
from .base import Source


class ANP(Source):
    """ANP statistical spreadsheets discovered from the data page.

    ``code`` is a substring used to find the download link; ``params`` carries
    ``sheet``/``value_col``/``date_col``.
    """

    id = "anp"

    def fetch(self, spec, config):
        page = _http.get("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos",
                         verify=False)
        soup = BeautifulSoup(page.text, "html.parser")
        link = next((a["href"] for a in soup.find_all("a", href=True)
                     if str(spec.code) in a["href"]), None)
        if not link:
            raise ValueError(f"ANP: no download link matched '{spec.code}'")
        content = _http.get(link, verify=False).content
        frame = read_excel(content, sheet=spec.params.get("sheet", 0))
        return series_from_frame(frame, spec.params.get("value_col", 1),
                                 spec.params.get("date_col", 0), spec.name)
