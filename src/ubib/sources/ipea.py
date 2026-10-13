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

        # Séries regionais devolvem uma linha por território (NIVNOME/TERCODIGO),
        # o que duplicaria as datas. Quando houver o agregado nacional
        # (NIVNOME vazio), mantém apenas ele.
        if "NIVNOME" in data.columns:
            national = data["NIVNOME"].astype(str).str.strip() == ""
            if national.any():
                data = data[national]

        # VALDATA vem em ISO 8601 com fuso. O Brasil teve horário de verão até
        # 2019, então uma série longa mistura offsets (-02:00 e -03:00) e o
        # pandas devolveria um índice object. utc=True normaliza; em seguida o
        # fuso é removido para o índice ficar ingênuo, como nas demais fontes.
        index = pd.to_datetime(data["VALDATA"], utc=True).dt.tz_localize(None).dt.normalize()
        values = pd.to_numeric(data["VALVALOR"], errors="coerce")

        series = self._series(values, index, spec.name).sort_index()
        return series[~series.index.duplicated(keep="last")]
