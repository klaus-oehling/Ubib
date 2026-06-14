"""Bloomberg -- via the ``xbbg`` library.

This replaces the legacy "Bloomberg bridge" with the lightweight, terminal-based
``xbbg`` package. It must run on a machine with a Bloomberg terminal/license and
the ``blpapi`` runtime; ``xbbg`` is an optional dependency
(``pip install ubib[bloomberg]``).

Catalog convention
------------------
``code`` is ``"TICKER,FIELD"`` -- e.g. ``"MXNSNOML Index,PX_LAST"``.
Field overrides may be appended as extra comma-separated ``key=value`` pairs:
``"US0003M Index,PX_LAST,BEST_FPERIOD_OVERRIDE=1FY"``.

``xbbg`` here returns a `narwhals` dataframe:

* ``bdp(...)``  -> columns ``[ticker, field, value]``
* ``bdh(...)``  -> columns ``[ticker, date, field, value]``

For time series we use ``bdh`` and reduce the long frame to one series.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .base import Source


def _to_pandas(frame) -> pd.DataFrame:
    """Normalise an xbbg result (narwhals or pandas) to a pandas DataFrame."""
    if isinstance(frame, pd.DataFrame):
        return frame
    for attr in ("to_pandas", "to_native"):
        if hasattr(frame, attr):
            converted = getattr(frame, attr)()
            if isinstance(converted, pd.DataFrame):
                return converted
            return pd.DataFrame(converted)
    return pd.DataFrame(frame)


class Bloomberg(Source):
    id = "bloomberg"

    def fetch(self, spec, config):
        try:
            from xbbg import blp
        except ImportError as exc:  # pragma: no cover - needs a terminal
            raise RuntimeError(
                "Bloomberg requires the 'xbbg' extra: pip install ubib[bloomberg]"
            ) from exc

        ticker, field, *override_parts = [p.strip() for p in str(spec.code).split(",")]
        overrides = dict(
            part.split("=", 1) for part in override_parts if "=" in part
        )

        start = spec.params.get("start", "1900-01-01")
        end = spec.params.get("end", dt.date.today().isoformat())
        raw = blp.bdh(tickers=ticker, flds=field, start_date=start, end_date=end, **overrides)

        frame = _to_pandas(raw)
        frame.columns = [str(c).lower() for c in frame.columns]
        if {"date", "value"}.issubset(frame.columns):
            if "field" in frame.columns:
                frame = frame[frame["field"] == field]
            index = pd.to_datetime(frame["date"])
            return self._series(frame["value"], index, spec.name).sort_index()

        # Fallback: classic xbbg wide frame (MultiIndex columns ticker/field).
        series = frame.iloc[:, 0]
        return self._series(series.values, frame.index, spec.name).sort_index()
