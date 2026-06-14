"""Helpers for the sources that download spreadsheets/zip files.

These government endpoints publish data as Excel files behind HTML pages. They
are inherently fragile (layouts and URLs change without notice). The helpers
here centralise the download + generic "read a column against a date column"
logic so each adapter stays small.

``params`` (from the catalog) drives parsing. Common keys:

* ``sheet`` -- worksheet name.
* ``value_col`` / ``date_col`` -- column letters or 0-based indices.
* ``skiprows`` / ``nrows`` -- row window.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd


def read_excel(content: bytes, sheet=0, **kwargs) -> pd.DataFrame:
    """Read an Excel workbook from raw bytes."""
    return pd.read_excel(io.BytesIO(content), sheet_name=sheet, **kwargs)


def extract_from_zip(content: bytes, suffix: str = ".xlsx") -> bytes:
    """Return the first member of a zip whose name ends with ``suffix``."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    for name in archive.namelist():
        if name.lower().endswith(suffix):
            return archive.read(name)
    raise FileNotFoundError(f"no '{suffix}' member found in archive")


def series_from_frame(frame: pd.DataFrame, value_col, date_col, name: str) -> pd.Series:
    """Build a Date-indexed series from two columns of ``frame``."""
    def pick(col):
        if isinstance(col, int):
            return frame.iloc[:, col]
        return frame[col]

    dates = pd.to_datetime(pick(date_col), errors="coerce")
    values = pd.to_numeric(pick(value_col), errors="coerce")
    series = pd.Series(values.values, index=dates, name=name)
    series.index.name = "Date"
    return series.dropna().sort_index()
