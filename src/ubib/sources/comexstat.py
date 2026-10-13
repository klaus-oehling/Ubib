"""MDIC -- ComexStat (Brazilian foreign-trade statistics).

A ComexStat query broken down by a dimension (country, ISIC division, HS
chapter, ...) returns *many* time series at once. This adapter therefore
returns a wide :class:`~pandas.DataFrame`: one row per month, one column per
category of the requested dimension. One catalog entry is enough to cover a
whole breakdown -- there is no need for one entry per country/sector pair.

``code`` is ``flow/detail/metric`` or, para recortar um subconjunto,
``flow/filterField/filterValue/detail/metric``:

* ``flow``   -- ``export`` or ``import``
* ``detail`` -- any ComexStat filter id (``country``, ``economicBlock``,
  ``section``, ``chapter``, ``BECLevel1``, ``BECLevel2``, ``ISICSection``,
  ``ISICDivision``, ``SITCSection``, ...)
* ``metric`` -- ``metricFOB`` (US$ FOB), ``metricKG`` (net weight) or, for
  imports, ``metricFreight`` / ``metricInsurance`` / ``metricCIF``

Examples::

    export/ISICDivision/metricFOB              # todas as divisões ISIC
    export/economicBlock/39/BECLevel1/metricFOB  # CGCE N1 só para a Ásia
    export/ISICSection/C/economicBlock/metricFOB # blocos só para transformação

O valor do filtro pode ser numérico (país, bloco) ou textual (``ISICSection``
usa ``A``/``B``/``C``/``D``).

Note: ``metricStatistic`` (Quantidade Estatística) is *not* usable here -- the
API requires ``ncm`` as the detail because its unit varies by product.
"""

from __future__ import annotations

import time

import pandas as pd
from requests import HTTPError, RequestException

from . import _http
from .base import Source

BASE = "https://api-comexstat.mdic.gov.br"


class ComexStat(Source):
    """ComexStat breakdown as a wide monthly DataFrame."""

    id = "comexstat"

    #: First year available in the ComexStat "general" database.
    START_YEAR = 1997

    #: A API limita requisições em sequência (HTTP 429). Como um catálogo com
    #: vários recortes baixa um atrás do outro, cada chamada é reenviada com
    #: espera crescente em vez de falhar.
    _MAX_TRIES = 5
    _BACKOFF = (11, 15, 25, 40)

    def _request(self, method, url, **kwargs):
        last = None
        for attempt in range(self._MAX_TRIES):
            try:
                return method(url, verify=False, **kwargs)
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in (429, 500, 502, 503, 504):
                    raise
                last = exc
            except RequestException as exc:
                last = exc
            if attempt < self._MAX_TRIES - 1:
                time.sleep(self._BACKOFF[min(attempt, len(self._BACKOFF) - 1)])
        raise RuntimeError(
            f"ComexStat: falha após {self._MAX_TRIES} tentativas em {url} "
            "(possível limite de requisições da API)."
        ) from last

    def fetch(self, spec, config):
        parts = [p.strip() for p in str(spec.code).split("/") if p.strip()]
        if len(parts) == 3:
            flow, detail, metric = parts
            filters = []
        elif len(parts) == 5:
            flow, fil_field, fil_value, detail, metric = parts
            try:                       # país/bloco usam id numérico; ISIC usa letra
                value = int(fil_value)
            except ValueError:
                value = fil_value
            filters = [{"filter": fil_field, "values": [value]}]
        else:
            raise ValueError(
                f"ComexStat: código inválido {spec.code!r}; esperado "
                "'flow/detail/metric' ou 'flow/filterField/filterValue/detail/metric'"
            )
        if metric == "metricStatistic":
            raise ValueError(
                "ComexStat: metricStatistic exige detalhamento por 'ncm' "
                "(a unidade varia por produto) e não pode ser agregada."
            )

        last_year = self._request(_http.get, f"{BASE}/general/dates/years").json()["data"]["max"]

        body = {
            "flow": flow,
            "monthDetail": True,
            "period": {"from": f"{self.START_YEAR}-01", "to": f"{last_year}-12"},
            "filters": filters,
            "details": [detail],
            "metrics": [metric],
        }
        payload = self._request(
            _http.post, f"{BASE}/general", params={"language": "pt"}, json=body
        ).json()

        records = (payload.get("data") or {}).get("list") or []
        if not records:
            raise ValueError(f"ComexStat returned no data for {spec.code}")

        data = pd.DataFrame(records)
        date = data["year"].astype(str) + "-" + data["monthNumber"].astype(str).str.zfill(2)
        data["Date"] = pd.to_datetime(date, format="%Y-%m") + pd.offsets.MonthEnd(0)

        # A coluna de rótulo tem o mesmo nome do detalhamento pedido; o código
        # correspondente vem como "co<Detalhe>". Prefere-se o rótulo textual.
        label = detail if detail in data.columns else None
        if label is None:
            candidates = [
                c for c in data.columns
                if c not in ("Date", "year", "monthNumber", metric)
                and not c.startswith("co")
            ]
            if not candidates:
                raise ValueError(
                    f"ComexStat: não encontrei a coluna de rótulo para {detail!r}"
                )
            label = candidates[0]

        data[metric] = pd.to_numeric(data[metric], errors="coerce")
        frame = data.pivot_table(
            index="Date", columns=label, values=metric, aggfunc="sum"
        )
        frame.index.name = "Date"
        frame.columns.name = None
        return frame.sort_index()
