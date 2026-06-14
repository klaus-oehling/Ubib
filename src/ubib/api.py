"""The public Ubib API.

>>> import ubib
>>> ipca = ubib.load("Focus IPCA Bacen")                   # one cached series
>>> df = ubib.load(["10YTEASURY", "US GDP"], update=True)  # several, refreshed

A single series resolves to a :class:`pandas.Series`; a list/tuple/set or dict
of series resolves to a :class:`pandas.DataFrame`.

All options after ``series`` are keyword-only and type-checked, so a stray
positional or wrong-typed argument fails immediately.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pandas as pd

from . import catalog, storage
from .config import Config, get_config
from .sources import available_sources, get_source
from .transform.frequency import to_period_end

log = logging.getLogger("ubib")

__all__ = ["load", "update", "available_series", "available_sources", "info"]


def _format(series: pd.Series, *, frequency: str | None, format_index: bool,
            declared: str | None) -> pd.Series:
    """Apply the requested frequency / period-end formatting to a series.

    Works the same whether ``series`` came from a fresh download or the cache.
    """
    if frequency:
        return to_period_end(series, frequency)
    if format_index:
        return to_period_end(series, declared)   # declared=None -> auto-detect
    return series.sort_index()


def _fetch_one(name: str, *, update: bool, frequency: str | None,
               format_index: bool, config: Config) -> pd.Series:
    """Return a single series, downloading and caching it if needed."""
    spec = catalog.get(name)  # raises KeyError immediately for unknown names

    if update or not storage.exists(spec.source, name, config):
        raw = get_source(spec.source).fetch(spec, config)
        base = storage.normalize(raw, name)
        storage.save(base, spec.source, name, config)
    else:
        base = storage.load(spec.source, name, config)

    return _format(base, frequency=frequency, format_index=format_index,
                   declared=spec.frequency)


def _resolve_names(series) -> tuple[str, list[str]]:
    """Return ``(kind, names)`` where kind is 'single' or 'many'."""
    if isinstance(series, str):
        return "single", [series]
    if isinstance(series, dict):
        return "many", list(series.values())
    if isinstance(series, Iterable):
        return "many", list(series)
    raise TypeError(f"Unsupported series argument: {type(series)!r}")


def _validate(names: list[str]) -> None:
    """Raise immediately if any requested name is not in the catalog."""
    unknown = [n for n in names if not catalog.has(n)]
    if unknown:
        raise KeyError(
            f"Unknown series (not in the metadata catalog): {unknown}. "
            "Check spelling with ubib.available_series()."
        )


def load(
    series,
    *,
    update: bool = False,
    frequency: str | None = None,
    format_index: bool = True,
    config: Config | None = None,
):
    """Load one or more series.

    Parameters
    ----------
    series:
        A series name (``str``), a list/tuple/set of names, or a
        ``{label: name}`` dict.
    update:
        If ``True``, re-download from the source instead of reading the cache.
    frequency:
        Optional frequency override (``"D"``/``"M"``/``"Q"``/``"A"``). Applied
        on every call, cached reads included.
    format_index:
        If ``True`` (default), align to period-end at the declared/detected
        frequency. If ``False``, return the raw dates. Applied on every call.
    config:
        Optional :class:`~ubib.config.Config`; defaults to the user's config.

    Returns
    -------
    A :class:`pandas.Series` for a single series, otherwise a
    :class:`pandas.DataFrame`.
    """
    if not isinstance(update, bool):
        raise TypeError(f"'update' must be True or False, got {update!r}")
    if not isinstance(format_index, bool):
        raise TypeError(f"'format_index' must be True or False, got {format_index!r}")
    if frequency is not None and (
        not isinstance(frequency, str) or frequency.upper() not in {"D", "M", "Q", "A"}
    ):
        raise ValueError(
            f"'frequency' must be one of 'D', 'M', 'Q', 'A' or None, got {frequency!r}"
        )

    config = config or get_config()
    kind, names = _resolve_names(series)
    _validate(names)  # fast, network-free check for typos / bad input
    labels = list(series.keys()) if isinstance(series, dict) else names

    if kind == "single":
        return _fetch_one(names[0], update=update, frequency=frequency,
                          format_index=format_index, config=config)

    collected: dict[str, pd.Series] = {}
    for label, name in zip(labels, names):
        try:
            collected[label] = _fetch_one(name, update=update, frequency=frequency,
                                         format_index=format_index, config=config)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            log.warning("skipping '%s': %s", name, exc)

    if not collected:
        return pd.DataFrame()
    frame = pd.concat(collected.values(), axis=1)
    frame.columns = list(collected.keys())
    frame.index.name = "Date"
    return frame.sort_index()


def update(series, **kwargs):
    """Convenience wrapper for :func:`load` with ``update=True``."""
    return load(series, update=True, **kwargs)


def available_series() -> list[str]:
    """All series names known to the catalog."""
    return catalog.names()


def info(name: str) -> dict:
    """Return the catalog metadata for a series as a dict."""
    spec = catalog.get(name)
    return {
        "name": spec.name,
        "source": spec.source,
        "code": spec.code,
        "params": spec.params,
        "frequency": spec.frequency,
        "description": spec.description,
    }
