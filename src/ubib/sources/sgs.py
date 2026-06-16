"""Banco Central do Brasil -- SGS (Sistema Gerenciador de Series Temporais)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import _http
from .base import Source


class SGS(Source):
    """SGS series. ``code`` is the numeric series id (e.g. ``"432"``).

    The SGS API limits each request for *daily* series to ~10 years, so we
    always download in decade windows and concatenate -- this is safe for any
    frequency.
    """

    id = "sgs"

    def fetch(self, spec, config):
        code = str(spec.code).split(";")[0].strip()
        frames = []
        start_year = 1920  # match full BCB history (some series start in the 1980s)
        end_year = dt.date.today().year + 1
        for year in range(start_year, end_year, 10):
            url = (
                f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
                f"?formato=json&dataInicial=01/01/{year}&dataFinal=31/12/{year + 9}"
            )
            response = _http.get(url, verify=False)
            try:
                chunk = response.json()
            except ValueError:
                continue
            if chunk:
                frames.append(pd.DataFrame(chunk))
        if not frames:
            raise ValueError(f"SGS returned no data for code {code}")
        data = pd.concat(frames, ignore_index=True)
        index = pd.to_datetime(data["data"], format="%d/%m/%Y")
        return self._series(data["valor"], index, spec.name)
