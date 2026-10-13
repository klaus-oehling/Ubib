"""Banco Central do Brasil -- SGS (Sistema Gerenciador de Series Temporais)."""

from __future__ import annotations

import datetime as dt
import time

import pandas as pd
from requests import HTTPError, RequestException

from . import _http
from .base import Source


class SGS(Source):
    """SGS series. ``code`` is the numeric series id (e.g. ``"432"``).

    Data is fetched in 10-year windows (the SGS API caps daily series at ~10
    years per request) from 1920 to today, then concatenated.

    A window with genuinely no observations returns HTTP 404; those are skipped
    (this is how a series that starts in, say, 2008 is handled without error).

    Transient failures are handled deliberately so they never *silently* truncate
    a series: under load the SGS API may time out, return a 5xx, or answer 200
    with a non-JSON error page (typically on the large, most-recent window). Each
    window is retried a few times, and if it still fails the whole load raises
    rather than dropping the window -- better a loud error and a rerun than a
    series that quietly ends early.
    """

    id = "sgs"

    _MAX_TRIES = 4
    _BACKOFF = 0.7  # segundos (multiplicado pela tentativa)

    def _fetch_window(self, code, year):
        """Return the window's JSON (possibly empty list), or ``None`` if the
        window genuinely has no data (HTTP 404). Raises on persistent failure."""
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
            f"?formato=json&dataInicial=01/01/{year}&dataFinal=31/12/{year + 9}"
        )
        last_exc = None
        for attempt in range(1, self._MAX_TRIES + 1):
            try:
                response = _http.get(url, verify=False)
            except HTTPError as exc:
                # 404 == genuinely no data in this window: skip, do not retry.
                if exc.response is not None and exc.response.status_code == 404:
                    return None
                last_exc = exc
            except RequestException as exc:  # timeout, conexão, etc.
                last_exc = exc
            else:
                try:
                    return response.json()
                except ValueError:
                    # 200 com corpo não-JSON (página de erro sob carga): transitório.
                    last_exc = ValueError(
                        f"SGS devolveu resposta não-JSON (código {code}, "
                        f"janela {year}-{year + 9})"
                    )
            if attempt < self._MAX_TRIES:
                time.sleep(self._BACKOFF * attempt)
        raise RuntimeError(
            f"SGS: falha ao baixar a janela {year}-{year + 9} do código {code} "
            f"após {self._MAX_TRIES} tentativas (dado não foi truncado "
            f"silenciosamente)."
        ) from last_exc

    def fetch(self, spec, config):
        code = str(spec.code).split(";")[0].strip()
        frames = []
        end_year = dt.date.today().year + 1
        for year in range(1920, end_year, 10):
            chunk = self._fetch_window(code, year)
            if chunk:
                frames.append(pd.DataFrame(chunk))

        if not frames:
            raise ValueError(f"SGS returned no data for code {code}")
        data = pd.concat(frames, ignore_index=True)
        index = pd.to_datetime(data["data"], format="%d/%m/%Y")
        return self._series(data["valor"], index, spec.name).sort_index()
