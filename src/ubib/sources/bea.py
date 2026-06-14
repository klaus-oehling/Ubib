"""BEA -- U.S. Bureau of Economic Analysis."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source


class BEA(Source):
    """BEA series.

    ``code`` is ``DataSetName,TableName,Frequency,SeriesCode`` -- for example
    ``"NIPA,T10101,Q,A191RL"``. The series is filtered to the given SeriesCode.
    """

    id = "bea"
    requires_key = True

    def fetch(self, spec, config):
        key = config.api_key("bea")
        dataset, table, freq, series_code = [p.strip() for p in str(spec.code).split(",")]
        url = (
            f"https://apps.bea.gov/api/data/?&UserID={key}&method=GetData"
            f"&DataSetName={dataset}&TableName={table}&Frequency={freq}"
            "&Year=ALL&ResultFormat=json"
        )
        records = _http.get(url).json()["BEAAPI"]["Results"]["Data"]
        data = pd.DataFrame.from_records(records)
        data = data[data["SeriesCode"] == series_code][["TimePeriod", "DataValue"]].copy()
        if data.empty:
            raise ValueError(f"BEA returned no rows for {series_code}")

        period = data["TimePeriod"].astype(str)
        if freq == "M":
            index = pd.to_datetime(period.str.replace("M", "-"), format="%Y-%m")
        elif freq == "Q":
            quarter_month = period.str.split("Q").apply(lambda x: f"{x[0]}-{int(x[1]) * 3}")
            index = pd.to_datetime(quarter_month, format="%Y-%m")
        else:  # annual
            index = pd.to_datetime(period, format="%Y")
        values = pd.to_numeric(data["DataValue"].str.replace(",", ""), errors="coerce")
        return self._series(values, index, spec.name)
