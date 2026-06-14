"""Frequency detection and period-end alignment.

The legacy library guessed a series' frequency from the spread of its index and
resampled to period-end. This is a clean reimplementation:

* :func:`detect_frequency` infers ``D``/``M``/``Q``/``A`` from the index.
* :func:`to_period_end` resamples to the (declared or detected) frequency,
  taking the last observation in each period -- except for daily data, which is
  left untouched.
"""

from __future__ import annotations

import pandas as pd

_RESAMPLE_RULE = {"M": "ME", "Q": "QE", "A": "YE"}


def detect_frequency(series: pd.Series) -> str:
    """Infer the frequency code of ``series`` from its DatetimeIndex."""
    index = pd.DatetimeIndex(series.index)
    if len(index) < 3:
        return "M"

    inferred = pd.infer_freq(index)
    if inferred:
        head = inferred[0]
        if head in ("B", "D"):
            return "D"
        if head in ("M",):
            return "M"
        if head in ("Q",):
            return "Q"
        if head in ("A", "Y"):
            return "A"

    # Fall back to counting distinct days/months, as the legacy code did.
    distinct_days = pd.Series(index.day).nunique()
    distinct_months = pd.Series(index.month).nunique()
    if distinct_days > 25:
        return "D"
    if distinct_months == 1:
        return "A"
    if distinct_months == 4:
        return "Q"
    return "M"


def to_period_end(series: pd.Series, frequency: str | None = None) -> pd.Series:
    """Align ``series`` to period-end at the given (or detected) frequency."""
    if series.empty:
        return series
    freq = (frequency or detect_frequency(series)).upper()
    if freq == "D":
        return series.sort_index()
    rule = _RESAMPLE_RULE.get(freq)
    if rule is None:
        return series.sort_index()
    return series.resample(rule).last().dropna(how="all")
