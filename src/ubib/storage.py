"""On-disk storage for Ubib series.

Storage model (one rule, no exceptions):

* **One series == one parquet file.**
* Every file has a :class:`~pandas.DatetimeIndex` named ``Date`` and a single
  value column named after the series.
* Files live under ``<data_dir>/<source>/<series>.parquet``.

This replaces the legacy double-write (raw JSON *and* pickle) with a single,
columnar, language-agnostic format.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import Config, get_config

log = logging.getLogger("ubib.storage")


def _path(source: str, name: str, config: Config | None = None) -> Path:
    config = config or get_config()
    return config.series_path(source, name)


def exists(source: str, name: str, config: Config | None = None) -> bool:
    """Return ``True`` if ``name`` is already cached on disk."""
    return _path(source, name, config).exists()


def save(series: pd.Series, source: str, name: str, config: Config | None = None) -> Path:
    """Persist ``series`` as a single-column parquet file.

    The series is coerced to a clean ``Date``-indexed, numeric, de-duplicated,
    sorted series before writing.
    """
    series = normalize(series, name)
    path = _path(source, name, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame(name).to_parquet(path, engine="pyarrow")
    log.info("saved %s (%d obs) -> %s", name, len(series), path)
    return path


def load(source: str, name: str, config: Config | None = None) -> pd.Series:
    """Read a cached series from disk.

    Raises :class:`FileNotFoundError` if the series has not been downloaded yet.
    """
    path = _path(source, name, config)
    if not path.exists():
        raise FileNotFoundError(
            f"'{name}' is not cached yet. Call load(..., update=True) to download it."
        )
    frame = pd.read_parquet(path, engine="pyarrow")
    series = frame.iloc[:, 0]
    series.name = name
    series.index.name = "Date"
    return series


def normalize(series: pd.Series, name: str) -> pd.Series:
    """Return a clean, canonical version of ``series``.

    * datetime index named ``Date``
    * numeric values
    * duplicates removed (last wins)
    * sorted ascending
    """
    series = series.copy()
    series.name = name
    series.index = pd.to_datetime(series.index)
    series.index.name = "Date"
    series = pd.to_numeric(series, errors="coerce")
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series


def delete(source: str, name: str, config: Config | None = None) -> None:
    """Remove a cached series if present."""
    path = _path(source, name, config)
    if path.exists():
        path.unlink()
        log.info("deleted %s", path)
