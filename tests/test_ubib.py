"""Offline tests for Ubib (no network required).

Run with:  pytest -q
"""

from __future__ import annotations

import pandas as pd
import pytest

from ubib import catalog, storage
from ubib.sources import available_sources
from ubib.transform.frequency import detect_frequency, to_period_end


def test_shipped_catalog_loads():
    names = catalog.names()
    assert len(names) > 100
    # every source referenced by the catalog must be a registered adapter
    assert catalog.sources().issubset(set(available_sources()))


def test_params_json_parsing():
    td = [n for n in catalog.names() if catalog.get(n).source == "tesouro_direto"]
    assert td, "expected at least one tesouro_direto series"
    assert isinstance(catalog.get(td[0]).params, dict)


def test_storage_normalize_dedup_and_sort():
    idx = pd.to_datetime(["2020-03-31", "2020-01-31", "2020-02-29", "2020-02-29"])
    raw = pd.Series([3, 1, 2, 2.5], index=idx)
    s = storage.normalize(raw, "X")
    assert list(s.index.strftime("%Y-%m")) == ["2020-01", "2020-02", "2020-03"]
    assert s.loc["2020-02-29"] == 2.5  # last duplicate wins
    assert s.index.name == "Date"


def test_frequency_detection():
    monthly = pd.Series(range(60), index=pd.date_range("2015-01-15", periods=60, freq="MS"))
    daily = pd.Series(range(400), index=pd.date_range("2020-01-01", periods=400, freq="D"))
    assert detect_frequency(monthly) == "M"
    assert detect_frequency(daily) == "D"


def test_to_period_end_resamples_to_month_end():
    monthly = pd.Series(range(3), index=pd.to_datetime(["2020-01-10", "2020-02-10", "2020-03-10"]))
    pe = to_period_end(monthly, "M")
    assert list(pe.index.day) == [31, 29, 31]



def test_unknown_series_raises():
    with pytest.raises(KeyError):
        catalog.get("does-not-exist")
