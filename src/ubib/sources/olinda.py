"""Banco Central do Brasil -- Olinda / Focus market-expectations API.

Focus data is two-dimensional (the *survey date* and the period being forecast),
so each Ubib series fixes a measure and a horizon and returns one value per
survey date.

``code`` is the indicator name (e.g. ``"IPCA"``); an optional ``";detail"``
suffix maps to the BCB ``IndicadorDetalhe`` (e.g. ``"Balança comercial;Saldo"``).

``params`` controls exactly what is read:

* ``endpoint`` -- ``"annual"`` (default), ``"monthly"``, ``"twelve_months"`` or
  ``"selic"``.
* ``stat`` -- statistic column: ``"Mediana"`` (default) or ``"Media"``.
* ``horizon`` -- for annual: ``"current"`` (default) or an explicit year (int).
* ``base_calculo`` -- ``0`` (default, 30-day base, the headline) or ``1`` (5-day).
* ``smoothed`` -- for ``twelve_months``: ``True`` (default, suavizada) or ``False``.
* ``detail`` -- overrides the ``IndicadorDetalhe`` derived from ``code``.

Olinda's OData service needs a literal ``$`` and ``%20``-encoded spaces, so the
query string is built by hand.
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
        base = int(spec.params.get("base_calculo", 0))

        indicator, _, code_detail = str(spec.code).partition(";")
        indicator = indicator.strip()
        detail = spec.params.get("detail", code_detail.strip() or None)

        if endpoint == "selic":
            resource = "ExpectativasMercadoSelic"
            select = f"Data,Reuniao,{stat}"
            flt = f"baseCalculo eq {base}"
        elif endpoint == "twelve_months":
            resource = "ExpectativasMercadoInflacao12Meses"
            smoothed = "S" if spec.params.get("smoothed", True) else "N"
            select = f"Indicador,Data,Suavizada,{stat}"
            flt = (f"Indicador eq '{indicator}' and baseCalculo eq {base} "
                   f"and Suavizada eq '{smoothed}'")
        elif endpoint == "monthly":
            resource = "ExpectativaMercadoMensais"
            select = f"Indicador,Data,DataReferencia,{stat}"
            flt = f"Indicador eq '{indicator}' and baseCalculo eq {base}"
        else:  # annual
            resource = "ExpectativasMercadoAnuais"
            select = f"Indicador,Data,DataReferencia,{stat}"
            flt = f"Indicador eq '{indicator}' and baseCalculo eq {base}"
        if detail:
            flt += f" and IndicadorDetalhe eq '{detail}'"

        query = (
            f"$format=json&$select={quote(select, safe=',')}"
            f"&$filter={quote(flt, safe='')}&$top=100000"
        )
        url = f"{_BASE}/{resource}?{query}"
        records = _http.get(url, verify=False).json()["value"]
        if not records:
            raise ValueError(f"Olinda returned no data for {indicator}")

        data = pd.DataFrame(records)
        data["Data"] = pd.to_datetime(data["Data"])

        if endpoint in ("selic", "twelve_months"):
            data = data.sort_values("Data").drop_duplicates("Data", keep="last")
            return self._series(data[stat], data["Data"], spec.name).sort_index()

        # annual / monthly: pick the requested reference horizon
        horizon = spec.params.get("horizon", "current")
        ref_year = data["DataReferencia"].astype(str).str[-4:].astype(int)
        if horizon == "current":
            mask = ref_year == data["Data"].dt.year
        else:
            mask = ref_year == int(horizon)
        data = data[mask].sort_values("Data").drop_duplicates("Data", keep="last")
        return self._series(data[stat], data["Data"], spec.name).sort_index()
