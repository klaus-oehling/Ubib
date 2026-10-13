"""IBGE -- SIDRA (Sistema IBGE de Recuperacao Automatica).

A SIDRA query that fixes every dimension to a single value returns one time
series. A query that leaves a classification open (e.g. ``/C315/all/`` for all
IPCA sub-items) returns *many* series at once; in that case this adapter returns
a wide DataFrame with a ``(Codigo, Descrição)`` column per item and a
``DatetimeIndex`` -- exactly as if you had listed every item ticker.
"""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source

_TIME_WORDS = (
    "Mês", "Mes", "Ano", "Trimestre", "Semestre", "Bimestre",
    "Quinzena", "Dia", "Período", "Periodo",
)


def _period_to_datetime(value) -> pd.Timestamp:
    text = str(value).strip()
    if len(text) >= 6 and text[:6].isdigit():
        return pd.to_datetime(text[:6], format="%Y%m") + pd.offsets.MonthEnd(0)
    if len(text) == 4 and text.isdigit():
        return pd.to_datetime(text, format="%Y")
    return pd.NaT


class SIDRA(Source):
    """SIDRA table values. ``code`` is the query path after ``/values/``."""

    id = "sidra"

    def fetch(self, spec, config):
        code = str(spec.code).split(";")[0].strip()
        url = f"https://apisidra.ibge.gov.br/values/{code}"
        records = _http.get(url, verify=False).json()
        if not records or len(records) < 2:
            raise ValueError(f"SIDRA returned no data for {code}")

        header = records[0]
        data = pd.DataFrame(records[1:])

        # Locate the time (period) column from SIDRA's header labels.
        period_key = None
        for key, label in header.items():
            if (key.endswith("C") and isinstance(label, str)
                    and "(Código)" in label and any(w in label for w in _TIME_WORDS)):
                period_key = key
                break
        if period_key is None:
            for key in [c for c in data.columns if c.endswith("C")]:
                if data[key].astype(str).str.fullmatch(r"(19|20)\d{2}(\d{2})?").mean() > 0.8:
                    period_key = key
                    break
        if period_key is None:
            raise ValueError(f"SIDRA: could not locate the time column for {code}")

        # Identify "item" dimensions: non-time code columns with >1 distinct value.
        item_code_cols = [
            c for c in data.columns
            if c.endswith("C") and c != period_key and data[c].nunique() > 1
        ]

        periods = data[period_key].map(_period_to_datetime)

        if not item_code_cols:
            # Single series.
            return self._series(data["V"], periods, spec.name).sort_index()

        # Wide table: one column per item (code, name), index = period.
        data = data.assign(_Date=periods)
        data["_V"] = pd.to_numeric(data["V"], errors="coerce")
        name_cols = [c[:-1] + "N" for c in item_code_cols]
        columns = []
        out = {}
        for keys, sub in data.groupby(item_code_cols + name_cols, sort=False):
            keys = keys if isinstance(keys, tuple) else (keys,)
            n = len(item_code_cols)
            label = tuple(str(k) for k in (list(keys[:n]) + list(keys[n:])))  # codes..., names...
            # for a single item-dim this is (code, name)
            col_key = label if len(label) > 1 else label[0]
            out[col_key] = sub.set_index("_Date")["_V"]
            columns.append(col_key)

        frame = pd.DataFrame(out)
        frame.index.name = "Date"
        if len(item_code_cols) == 1:
            frame.columns = pd.MultiIndex.from_tuples(
                list(frame.columns), names=["Codigo", "Descrição"])
        return frame.sort_index()
