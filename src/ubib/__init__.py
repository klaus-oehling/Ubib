"""Ubib -- a unified, systematic interface for importing economic data.

Quick start
-----------
>>> import ubib
>>> ubib.define_config(data_dir=r"D:/economic_data",
...                    api_keys={"fred": "...", "bls": "..."})
>>> s = ubib.load("10YTEASURY", update=True)

Nothing is written when you install or import the package, and the library holds
no keys of its own. You configure Ubib once with :func:`define_config`, which
writes ``~/.ubib/config.toml``; after that every :func:`load` call uses those
paths and keys.
"""

from __future__ import annotations

from .api import available_series, available_sources, info, load, update
from .microdata import (
    available_microdata,
    check_microdata_layout,
    microdata,
    microdata_dir,
    microdata_files,
    microdata_variables,
    read_microdata,
)
from .config import (
    API_KEY_NAMES,
    CREDENTIAL_NAMES,
    Config,
    define_config,
    get_config,
    template_text,
)

__version__ = "1.0.0"

__all__ = [
    "load",
    "update",
    "info",
    "available_series",
    "available_sources",
    "microdata",
    "microdata_files",
    "microdata_variables",
    "read_microdata",
    "check_microdata_layout",
    "available_microdata",
    "microdata_dir",
    "define_config",
    "get_config",
    "template_text",
    "API_KEY_NAMES",
    "CREDENTIAL_NAMES",
    "Config",
    "__version__",
]
