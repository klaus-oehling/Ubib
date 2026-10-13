"""Microdata access -- tables of individuals, not time series.

:func:`ubib.load` exists for series: it indexes by date, coerces everything to
a number and caches to parquet. Microdata is none of those things -- it is a
fixed-width file, no header, hundreds of megabytes, one person per row. Forcing
it through the series path would destroy it.

Microdata therefore has its own entry point, which downloads, unpacks and reads
the file::

    >>> import ubib
    >>> df = ubib.microdata("PNAD microdados - 202401_new")
    >>> df = ubib.microdata("PNAD microdados - 202401_new",
    ...                     columns=["Ano", "Trimestre", "VD4020"])

Splitting a fixed-width file into columns needs the variable dictionary, and
Ubib finds it on its own in every case IBGE published machine-readably: one
SAS input covers the whole quarterly series, the annual visita files name
theirs in the catalog, the 2001-2012 packages bundle theirs inside the data
zip, and 1992-1999 and 2013-2015 ship theirs in a sibling archive.

The exception is 1976-1990, documented only as Word files. Those entries say
so and point at :func:`microdata_files`; ``layout=`` accepts positions you
supply yourself. Nothing is ever guessed.

Files are kept under ``<data_dir>/microdados_pnad``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import _console, catalog
from .config import Config, get_config
from .sources import get_source
from .sources.microdados_pnad import (
    ALL,
    check_layout,
    merge_household_person,
    merge_keys,
    read,
    variables,
)

log = logging.getLogger("ubib.microdata")

__all__ = ["microdata", "microdata_files", "microdata_variables",
           "available_microdata", "microdata_dir", "read_microdata",
           "check_microdata_layout"]

#: Sources whose entries are microdata rather than time series.
_MICRODATA_SOURCES = ("microdados_pnad",)

#: Public aliases, so the reader and its sanity check can be used on any
#: fixed-width file.
read_microdata = read
check_microdata_layout = check_layout


def _check(name: str):
    """Validate the name and return ``(spec, adapter)``."""
    if not isinstance(name, str):
        raise TypeError(f"'series' must be an entry name (str), not {type(name)!r}")
    if not catalog.has(name):
        raise KeyError(
            f"'{name}' is not in the catalog. See ubib.available_microdata()."
        )
    spec = catalog.get(name)
    if spec.source not in _MICRODATA_SOURCES:
        raise ValueError(
            f"'{name}' is a series from source '{spec.source}', not microdata. "
            f"Use ubib.load('{name}')."
        )
    return spec, get_source(spec.source)


def _resolve_layout(spec, adapter, config, layout):
    """Return ``(layout, fetched)`` -- caller's layout, else the source's own."""
    if layout:
        return layout, False
    found = adapter.layout_for(spec, config)
    if found:
        return found, True
    raise ValueError(
        f"no machine-readable dictionary could be found for '{spec.name}', so "
        "its field positions are unknown. IBGE documented the 1976-1990 PNAD "
        "only as Word files.\n"
        "Either pass the positions in:\n"
        f"    ubib.microdata('{spec.name}', layout={{'V0101': (1, 4), ...}})\n"
        "or take the file and read it however you like:\n"
        f"    ubib.microdata_files('{spec.name}')"
    )


def _read_all(paths, spec, adapter, config, layout, columns, merge):
    """Read the package: one DataFrame, a merged one, or ``{role: DataFrame}``."""
    resolved, fetched = _resolve_layout(spec, adapter, config, layout)

    if len(paths) == 1:
        flat = resolved.get("single", resolved) if _by_role(resolved) else resolved
        return read(paths[0], flat, columns, verify_width=fetched)

    # household + person: each file has its own layout
    if not _by_role(resolved):
        raise ValueError(
            f"'{spec.name}' has a household file and a person file, which need "
            "one layout each: layout={'household': {...}, 'person': {...}}."
        )
    keys = merge_keys(resolved["household"], resolved["person"])

    # A column subset must still carry the identifiers, or the two files cannot
    # be joined. Asking for them is an implementation detail, so add them here
    # rather than making every caller remember that 1992 uses CONTROL and 2001
    # uses V0102.
    wanted = columns
    if merge and columns is not None and not (
        isinstance(columns, str) and columns.lower() == ALL
    ):
        asked = [columns] if isinstance(columns, str) else list(columns)
        unknown = [c for c in asked
                   if c not in resolved["household"] and c not in resolved["person"]]
        if unknown:
            raise KeyError(
                f"variables not in either dictionary for '{spec.name}': {unknown}. "
                f"List what exists with ubib.microdata_variables('{spec.name}')."
            )
        wanted = {
            role: _with_keys(asked, [pair[i] for pair in keys], resolved[role])
            for i, role in ((0, "household"), (1, "person"))
        }

    frames = {}
    for path in paths:
        role = _role_of(path)
        cols = wanted[role] if isinstance(wanted, dict) else wanted
        frames[role] = read(path, resolved[role], cols, verify_width=fetched)

    if not merge:
        return frames               # keys stay: you need them to join yourself
    merged = merge_household_person(frames["household"], frames["person"], keys)

    # The key columns were added so the two files could be joined. That is
    # plumbing, so they are dropped again unless they were actually asked for.
    if isinstance(wanted, dict):
        merged = merged[[c for c in asked if c in merged.columns]]
    return merged


def _with_keys(asked: list[str], keys: list[str], layout: dict) -> list[str]:
    """``asked`` narrowed to what this file holds, with its key columns first.

    A request spans both files -- V4742 lives on the person record, V0105 on the
    household one -- so each file gets the subset it actually has.
    """
    return keys + [c for c in asked if c in layout and c not in keys]


def _by_role(layout) -> bool:
    """True when the layout is ``{"household": {...}, "person": {...}}``."""
    return isinstance(layout, dict) and bool({"household", "person", "single"}
                                             & set(layout))


def _role_of(path: Path) -> str:
    stem = path.stem
    for role in ("household", "person"):
        if stem.endswith("_" + role):
            return role
    return stem


def microdata(series, *, columns=ALL, layout: dict | None = None,
              merge: bool = True, update: bool = False, verbose: bool = True,
              config: Config | None = None):
    """Download (if needed) and read microdata into a DataFrame.

    Parameters
    ----------
    series:
        A microdata entry name, or a list/dict of them.
    columns:
        ``"all"`` (default) or a list of variable names. Selecting a few
        variables is much faster and uses far less memory than reading all of
        them. You get back exactly the variables you name: the identifiers
        needed to join the household and person files are added internally and
        dropped again, unless you list them yourself.
    layout:
        ``{variable: (start, end[, dtype])}`` with 1-based positions. Required
        for the annual PNAD; for the continuous PNAD it is fetched from IBGE
        automatically and this argument only overrides it.
    merge:
        For the annual PNAD, which ships a household file and a person file,
        ``True`` (default) returns one table: every person with their
        household's attributes attached. ``False`` returns
        ``{"household": ..., "person": ...}`` unchanged. No effect on
        one-file packages.
    update:
        If ``True``, download again even if the file is already extracted.
    verbose:
        Print one line per entry, with a progress bar when there are several.
    config:
        Optional :class:`~ubib.config.Config`; defaults to the user's.

    Returns
    -------
    A :class:`~pandas.DataFrame` for a one-file package, and for a
    household + person package too when ``merge`` is left on. With
    ``merge=False``, ``{"household": DataFrame, "person": DataFrame}``. For
    several entries, ``{name: <any of the above>}``.
    """
    if not isinstance(update, bool):
        raise TypeError(f"'update' must be True or False, not {update!r}")
    config = config or get_config()

    if isinstance(series, str):
        spec, adapter = _check(series)
        paths = adapter.materialize(spec, config, update=update)
        frame = _read_all(paths, spec, adapter, config, layout, columns, merge)
        if verbose:
            _console.ok(f"{series}: {_shape_note(frame)}")
        return frame

    names = list(series.values()) if isinstance(series, dict) else list(series)
    labels = list(series.keys()) if isinstance(series, dict) else names
    pairs = list(zip(labels, names))
    for _, name in pairs:
        _check(name)                    # validate everything before downloading

    out = {}
    for label, name in _console.progress(pairs, desc="Loading microdata"):
        spec, adapter = _check(name)
        try:
            paths = adapter.materialize(spec, config, update=update)
            out[label] = _read_all(paths, spec, adapter, config, layout, columns, merge)
            if verbose:
                _console.ok(f"{name}: {_shape_note(out[label])}")
        except (RuntimeError, ValueError, KeyError, OSError) as exc:
            if verbose:
                _console.fail(f"{name}: {exc}")
    return out


def _shape_note(obj) -> str:
    if isinstance(obj, pd.DataFrame):
        return f"{len(obj):,} rows x {obj.shape[1]} columns"
    return ", ".join(f"{k} {len(v):,}x{v.shape[1]}" for k, v in obj.items())


def microdata_files(series, *, update: bool = False, verbose: bool = True,
                    config: Config | None = None):
    """Same download and unpacking as :func:`microdata`, but return the paths.

    Useful when you would rather read the file yourself, or when no variable
    dictionary is available for that year.
    """
    config = config or get_config()

    if isinstance(series, str):
        spec, adapter = _check(series)
        paths = adapter.materialize(spec, config, update=update)
        if verbose:
            _console.ok(f"{series}: {', '.join(p.name for p in paths)}")
        return paths[0] if len(paths) == 1 else paths

    names = list(series.values()) if isinstance(series, dict) else list(series)
    labels = list(series.keys()) if isinstance(series, dict) else names
    pairs = list(zip(labels, names))
    for _, name in pairs:
        _check(name)

    out: dict[str, Path | list[Path]] = {}
    for label, name in _console.progress(pairs, desc="Downloading microdata"):
        spec, adapter = _check(name)
        try:
            paths = adapter.materialize(spec, config, update=update)
            out[label] = paths[0] if len(paths) == 1 else paths
            if verbose:
                _console.ok(f"{name}: {', '.join(p.name for p in paths)}")
        except (RuntimeError, ValueError, OSError) as exc:
            if verbose:
                _console.fail(f"{name}: {exc}")
    return out


def microdata_variables(series: str, *, config: Config | None = None) -> pd.DataFrame:
    """What variables an entry has, with IBGE's own labels -- a table to search.

    Codes drift across the decades, so rather than remembering them, look them
    up::

        v = ubib.microdata_variables("PNAD microdados - 2011_old")
        v[v.label.str.contains("PER CAPITA", case=False, na=False)]

    Columns: ``file`` (household/person, when the year has two), ``name``,
    ``start``, ``end``, ``width``, ``dtype`` and ``label``. Needs no download
    beyond the dictionary itself.
    """
    config = config or get_config()
    spec, adapter = _check(series)
    layout = adapter.layout_for(spec, config)
    if not layout:
        raise ValueError(
            f"no machine-readable dictionary is published for '{series}', so "
            "its variables cannot be listed."
        )
    return variables(layout)


def available_microdata(source: str | None = None) -> list[str]:
    """Names of every microdata entry in the catalog."""
    sources = (source.lower(),) if source else _MICRODATA_SOURCES
    return [n for s in sources for n in catalog.names_for_source(s)]


def microdata_dir(source: str = "microdados_pnad", config: Config | None = None) -> Path:
    """Folder the microdata files for that source are written to."""
    config = config or get_config()
    return (Path(config.data_dir) / source.lower()).resolve()
