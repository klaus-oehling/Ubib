"""Small HTTP helper shared by source adapters.

A single :class:`requests.Session` with sensible retries/backoff. SSL
verification is on by default; a handful of government endpoints with flaky
certificate chains opt out per-request via ``verify=False``.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

DEFAULT_TIMEOUT = 60
_USER_AGENT = "ubib/1.0"

# Several government endpoints have flaky certificate chains, so a few
# adapters call with verify=False on purpose. Silence the resulting (noisy
# but expected) warning rather than letting it spam every request.
import urllib3
urllib3.disable_warnings(InsecureRequestWarning)


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": _USER_AGENT})
    return session


_SESSION = _build_session()


def get(url: str, *, verify: bool = True, timeout: int = DEFAULT_TIMEOUT, **kwargs):
    """HTTP GET with retries. Raises for non-2xx responses."""
    response = _SESSION.get(url, verify=verify, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response


def post(url: str, *, verify: bool = True, timeout: int = DEFAULT_TIMEOUT, **kwargs):
    """HTTP POST with retries. Raises for non-2xx responses."""
    response = _SESSION.post(url, verify=verify, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response
