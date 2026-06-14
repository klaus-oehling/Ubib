"""IPEADATA -- Instituto de Pesquisa Economica Aplicada (OData v4 API)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class IPEA(Source):
    """IPEADATA series. ``code`` is the SERCODIGO."""

    id = "ipea"

    def fetch(self, spec, config):
        code = str(spec.code).strip()
        url = (
            "http://www.ipeadata.gov.br/api/odata4/"
            f"ValoresSerie(SERCODIGO='{code}')"
        )
        response = _http.get(url, verify=False)
        records = response.json().get("value", [])
        if not records:
            raise ValueError(f"IPEA returned no data for {code}")
        data = pd.DataFrame(records)
        index = pd.to_datetime(data["VALDATA"])
        return self._series(data["VALVALOR"], index, spec.name)
