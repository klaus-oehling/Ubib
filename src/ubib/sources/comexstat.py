"""MDIC -- ComexStat (Brazilian foreign-trade statistics)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class ComexStat(Source):
    """ComexStat metric as a monthly total.

    ``code`` is ``flow/discriminator/value`` or
    ``flow/filterField/filterValue/discriminator/value``. The chosen ``value``
    metric is summed by month.
    """

    id = "comexstat"

    def fetch(self, spec, config):
        last_year = _http.get(
            "https://api-comexstat.mdic.gov.br/general/dates/years", verify=False
        ).json()["data"]["max"]
        parts = str(spec.code).split("/")
        if len(parts) == 5:
            flow, fil_field, fil_value, disc, value = parts
            filters = [{"filter": fil_field, "values": [int(fil_value)]}]
            details = [fil_field, disc]
        else:
            flow, disc, value = parts
            filters = []
            details = [disc]
        body = {
            "flow": flow,
            "monthDetail": True,
            "period": {"from": "1997-01", "to": f"{last_year}-12"},
            "filters": filters,
            "details": details,
            "metrics": [value],
        }
        payload = _http.post(
            "https://api-comexstat.mdic.gov.br/general",
            params={"language": "pt"},
            json=body,
            verify=False,
        ).json()
        data = pd.DataFrame(payload["data"]["list"])
        date = data["year"].astype(str) + "-" + data["monthNumber"].astype(str).str.zfill(2)
        data["Date"] = pd.to_datetime(date, format="%Y-%m") + pd.offsets.MonthEnd(0)
        totals = data.groupby("Date")[value].apply(lambda s: pd.to_numeric(s).sum())
        return self._series(totals.values, totals.index, spec.name).sort_index()
