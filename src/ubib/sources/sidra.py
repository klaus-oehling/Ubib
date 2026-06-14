"""IBGE -- SIDRA (Sistema IBGE de Recuperacao Automatica)."""

from __future__ import annotations

import pandas as pd

from . import _http
from .base import Source

# Words that identify the time dimension in SIDRA's header row.
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
    """SIDRA table values. ``code`` is the SIDRA query path after ``/values/``.

    SIDRA returns a header row (the first element) mapping each column to a
    label. We use it to locate the *time* column rather than assuming a fixed
    position, then parse the period codes (``YYYYMM`` or ``YYYY``).
    """

    id = "sidra"

    def fetch(self, spec, config):
        code = str(spec.code).split(";")[0].strip()
        url = f"https://apisidra.ibge.gov.br/values/{code}"
        records = _http.get(url, verify=False).json()
        if not records or len(records) < 2:
            raise ValueError(f"SIDRA returned no data for {code}")

        header = records[0]
        period_key = None
        for key, label in header.items():
            if (
                key.endswith("C")
                and isinstance(label, str)
                and "(Código)" in label
                and any(w in label for w in _TIME_WORDS)
            ):
                period_key = key
                break

        data = pd.DataFrame(records[1:])
        if period_key is None:
            # Fallback: pick the code column whose values look like periods.
            for key in [c for c in data.columns if c.endswith("C")]:
                frac = data[key].astype(str).str.fullmatch(r"(19|20)\d{2}(\d{2})?").mean()
                if frac > 0.8:
                    period_key = key
                    break
        if period_key is None:
            raise ValueError(f"SIDRA: could not locate the time column for {code}")

        index = data[period_key].map(_period_to_datetime)
        return self._series(data["V"], index, spec.name).sort_index()
