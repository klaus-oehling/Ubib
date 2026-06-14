"""The series catalog (metadata).

The catalog is a single Excel workbook shipped inside the package
(``ubib/data/metadata.xlsx``) with one sheet, ``series`` -- one row per series:

    ============ =================================================================
    column       meaning
    ============ =================================================================
    ``name``     Unique key the user passes to :func:`ubib.load`.
    ``source``   Adapter id (``sgs``, ``sidra``, ``fred``, ``bloomberg`` ...).
    ``code``     Source-specific identifier (series id, ``TICKER,FIELD`` ...).
    ``params``   Optional JSON with extra parsing parameters (sheet/col/date for
                 spreadsheet sources, etc.). May be blank.
    ``frequency``Optional declared frequency (``D``/``M``/``Q``/``A``) overriding
                 auto-detection. May be blank.
    ``description`` Optional human-readable label / notes.
    ============ =================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class SeriesSpec:
    """A single catalog entry."""

    name: str
    source: str
    code: str
    params: dict = field(default_factory=dict)
    frequency: str | None = None
    description: str = ""


def _metadata_file() -> Path:
    """Locate the metadata workbook (shipped with the package)."""
    return Path(str(resources.files("ubib") / "data" / "metadata.xlsx"))


def _parse_params(raw) -> dict:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except (json.JSONDecodeError, ValueError):
        return {"raw": text}


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, SeriesSpec]:
    path = _metadata_file()
    series_df = pd.read_excel(path, sheet_name="series", engine="openpyxl")

    specs: dict[str, SeriesSpec] = {}
    for row in series_df.to_dict("records"):
        name = _clean(row.get("name"))
        source = _clean(row.get("source"))
        if not name or not source:
            continue
        specs[name] = SeriesSpec(
            name=name,
            source=source.lower(),
            code=_clean(row.get("code")) or "",
            params=_parse_params(row.get("params")),
            frequency=_clean(row.get("frequency")),
            description=_clean(row.get("description")) or "",
        )
    return specs


def reload() -> None:
    """Clear the cached catalog (after editing the workbook or in tests)."""
    _load_catalog.cache_clear()


def get(name: str) -> SeriesSpec:
    """Return the :class:`SeriesSpec` for ``name`` (raises ``KeyError``)."""
    try:
        return _load_catalog()[name]
    except KeyError as exc:
        raise KeyError(f"'{name}' is not in the metadata catalog") from exc


def has(name: str) -> bool:
    """Return ``True`` if ``name`` is a known series."""
    return name in _load_catalog()


def names() -> list[str]:
    """All series names in the catalog."""
    return list(_load_catalog())


def sources() -> set[str]:
    """The set of distinct sources referenced by the catalog."""
    return {spec.source for spec in _load_catalog().values()}


def names_for_source(source: str) -> list[str]:
    """All series belonging to ``source``."""
    source = source.lower()
    return [n for n, s in _load_catalog().items() if s.source == source]
