"""On-disk storage for Ubib series.

Storage model:

* **One catalog entry == one parquet file** under ``<data_dir>/<source>/<name>.parquet``.
* Most entries are a single time series (one value column).
* Some entries (e.g. a SIDRA query spanning many categories) resolve to a wide
  table -- a ``DatetimeIndex`` with one column per item. These round-trip too;
  because parquet can't store a ``MultiIndex`` on the columns, multi-level
  column labels are flattened on save and rebuilt on load.

A single value column is returned as a :class:`~pandas.Series`; multiple columns
are returned as a :class:`~pandas.DataFrame`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import Config, get_config

log = logging.getLogger("ubib.storage")

_SEP = "␟"  # unit-separator: joins MultiIndex column levels for parquet


def _path(source: str, name: str, config: Config | None = None) -> Path:
    config = config or get_config()
    return config.series_path(source, name)


def exists(source: str, name: str, config: Config | None = None) -> bool:
    """Return ``True`` if ``name`` is already cached on disk."""
    return _path(source, name, config).exists()


def normalize(data, name: str):
    """Return a clean, canonical version of a Series or DataFrame.

    * datetime index named ``Date``
    * numeric values
    * duplicate dates removed (last wins), sorted ascending
    """
    data = data.copy()
    data.index = pd.to_datetime(data.index)
    data.index.name = "Date"
    if isinstance(data, pd.Series):
        data = pd.to_numeric(data, errors="coerce")
        data.name = name
    else:
        data = data.apply(pd.to_numeric, errors="coerce")
    data = data[~data.index.duplicated(keep="last")].sort_index()
    return data


def save(data, source: str, name: str, config: Config | None = None) -> Path:
    """Persist a Series or DataFrame as one parquet file."""
    data = normalize(data, name)
    frame = data.to_frame(name) if isinstance(data, pd.Series) else data.copy()

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [_SEP.join(map(str, tup)) for tup in frame.columns]
    else:
        frame.columns = [str(c) for c in frame.columns]

    path = _path(source, name, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, engine="pyarrow")
    log.info("saved %s (%d rows x %d cols) -> %s", name, frame.shape[0], frame.shape[1], path)
    return path


def load(source: str, name: str, config: Config | None = None):
    """Read a cached entry from disk (Series if one column, else DataFrame)."""
    path = _path(source, name, config)
    if not path.exists():
        raise FileNotFoundError(
            f"'{name}' is not cached yet. Call load(..., update=True) to download it."
        )
    frame = pd.read_parquet(path, engine="pyarrow")
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "Date"

    if any(_SEP in str(c) for c in frame.columns):
        frame.columns = pd.MultiIndex.from_tuples(
            [tuple(str(c).split(_SEP)) for c in frame.columns],
            names=["Codigo", "Descrição"],
        )
        return frame
    if frame.shape[1] == 1:
        series = frame.iloc[:, 0]
        series.name = name
        return series
    return frame


def delete(source: str, name: str, config: Config | None = None) -> None:
    """Remove a cached entry if present."""
    path = _path(source, name, config)
    if path.exists():
        path.unlink()
        log.info("deleted %s", path)
