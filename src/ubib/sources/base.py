"""Abstract base class for all data-source adapters.

An adapter knows how to turn one catalog entry (:class:`ubib.catalog.SeriesSpec`)
into a single pandas :class:`~pandas.Series` indexed by date. It does **not**
worry about caching, frequency resampling or file layout -- the engine
(:mod:`ubib.api`) handles that uniformly for every source.

Implementing a new source therefore means writing one method::

    class MySource(Source):
        id = "mysource"

        def fetch(self, spec, config):
            ...
            return pandas_series
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ..config import Config
from ..catalog import SeriesSpec


class Source(ABC):
    """Base class for every data source."""

    #: Registry key. Must match the ``source`` column in the catalog.
    id: str = ""

    #: Set to ``True`` for sources that need a key from ``config.api_keys``.
    requires_key: bool = False

    @abstractmethod
    def fetch(self, spec: SeriesSpec, config: Config) -> pd.Series:
        """Download ``spec`` and return a raw, date-indexed series.

        The returned series may be unsorted or contain duplicates -- the engine
        normalizes it. It should *not* be resampled here unless the source
        format requires it to parse correctly.
        """
        raise NotImplementedError

    # -- convenience helpers available to every adapter -------------------- #

    @staticmethod
    def _series(values, index, name: str) -> pd.Series:
        series = pd.Series(list(values), index=pd.to_datetime(index), name=name)
        series.index.name = "Date"
        return series
