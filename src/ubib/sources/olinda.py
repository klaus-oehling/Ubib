"""Banco Central do Brasil -- Olinda / Focus market-expectations API.

Focus data is intrinsically two-dimensional (the *survey date* and the
*reference period* being forecast). To keep Ubib's "everything is a single
series" model, this adapter returns, for each survey date, the median forecast
for one chosen reference horizon.

``code`` is the indicator name (e.g. ``"IPCA"``). ``params`` may set:

* ``endpoint`` -- ``"annual"`` (default), ``"monthly"`` or ``"selic"``.
* ``horizon`` -- for annual: ``"current"`` (default, forecast for the survey's
  own year) or an explicit reference year as an integer.
* ``stat`` -- statistic to read (default ``"Mediana"``).

Note: Olinda's OData service requires a literal ``$`` and ``%20``-encoded
spaces, so the query string is built by hand rather than via ``requests``'
``params=`` (which would emit ``%24`` and ``+`` and trigger HTTP 400).
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from . import _http
from .base import Source

_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"


class Olinda(Source):
    id = "olinda"

    def fetch(self, spec, config):
        endpoint = spec.params.get("endpoint", "annual")
        stat = spec.params.get("stat", "Mediana")
        indicator = spec.code

        if endpoint == "selic":
            resource = "ExpectativasMercadoSelic"
            select = f"Data,Reuniao,{stat}"
            flt = "baseCalculo eq 0"
        elif endpoint == "monthly":
            resource = "ExpectativaMercadoMensais"
            select = f"Indicador,Data,DataReferencia,{stat}"
            flt = f"Indicador eq '{indicator}' and baseCalculo eq 0"
        else:
            resource = "ExpectativasMercadoAnuais"
            select = f"Indicador,Data,DataReferencia,{stat}"
            flt = f"Indicador eq '{indicator}'"

        # Build the OData query manually: literal '$', spaces as %20.
        query = (
            f"$format=json"
            f"&$select={quote(select, safe=',')}"
            f"&$filter={quote(flt, safe='')}"
            f"&$top=100000"
        )
        url = f"{_BASE}/{resource}?{query}"
        records = _http.get(url, verify=False).json()["value"]
        if not records:
            raise ValueError(f"Olinda returned no data for {indicator}")
        data = pd.DataFrame(records)
        data["Data"] = pd.to_datetime(data["Data"])

        if endpoint == "selic":
            data = data.sort_values("Data").drop_duplicates("Data", keep="last")
            return self._series(data[stat], data["Data"], spec.name).sort_index()

        horizon = spec.params.get("horizon", "current")
        ref_year = data["DataReferencia"].astype(str).str[:4].astype(int)
        if horizon == "current":
            mask = ref_year == data["Data"].dt.year
        else:
            mask = ref_year == int(horizon)
        data = data[mask].sort_values("Data").drop_duplicates("Data", keep="last")
        return self._series(data[stat], data["Data"], spec.name).sort_index()
