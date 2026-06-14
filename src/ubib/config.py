"""Configuration handling for Ubib.

The library itself stores **no** keys, paths or secrets. It only knows the
*shape* of a configuration (which API-key and credential fields exist); the
actual values are supplied by the user and saved in a single TOML file, by
default ``~/.ubib/config.toml`` (override with the ``UBIB_CONFIG`` env var).

You configure Ubib once, from Python::

    import ubib
    ubib.define_config(
        data_dir=r"D:/economic_data",
        api_keys={"fred": "...", "bls": "..."},
        credentials={"bcch_user": "...", "bcch_password": "..."},
    )

After that, every ``ubib.load(...)`` call reads those values. A blank template
of the file's structure ships at ``ubib/data/config.template.toml``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10 fallback
    import tomli as _toml  # type: ignore[no-redef]

#: Default home for the config file and (suggested) data cache.
DEFAULT_HOME = Path.home() / ".ubib"

#: API-key field names the library understands (the "shape" -- no values).
API_KEY_NAMES = ("fred", "bls", "bea", "inegi", "banxico", "us_census")

#: Credential field names the library understands (the "shape" -- no values).
CREDENTIAL_NAMES = ("bcch_user", "bcch_password")


@dataclass
class Config:
    """Resolved Ubib configuration."""

    config_path: Path
    data_dir: Path
    api_keys: dict[str, str] = field(default_factory=dict)
    credentials: dict[str, str] = field(default_factory=dict)

    def api_key(self, source: str) -> str | None:
        value = self.api_keys.get(source.lower())
        return value or None

    def credential(self, name: str) -> str | None:
        value = self.credentials.get(name.lower())
        return value or None

    def series_path(self, source: str, name: str) -> Path:
        return self.data_dir / source.lower() / f"{_safe_filename(name)}.parquet"


def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join("_" if ch in bad else ch for ch in str(name)).strip()


def config_location() -> Path:
    """Path to the config file (honours ``UBIB_CONFIG``)."""
    override = os.environ.get("UBIB_CONFIG")
    if override:
        return Path(override).expanduser()
    return DEFAULT_HOME / "config.toml"


def template_text() -> str:
    """Return the shipped blank config template (for reference only)."""
    return (resources.files("ubib") / "data" / "config.template.toml").read_text(
        encoding="utf-8"
    )


def _toml_value(value) -> str:
    text = "" if value is None else str(value)
    if "'" in text:  # fall back to a basic string with escapes
        text = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{text}"'
    return f"'{text}'"  # literal string -> no backslash escaping (good for Windows paths)


def _render(data_dir, api_keys: dict, credentials: dict) -> str:
    lines = [
        "# Ubib configuration (written by ubib.define_config).",
        f"data_dir = {_toml_value(data_dir)}",
        "",
        "[api_keys]",
    ]
    for key in sorted(api_keys):
        lines.append(f"{key} = {_toml_value(api_keys[key])}")
    lines += ["", "[credentials]"]
    for key in sorted(credentials):
        lines.append(f"{key} = {_toml_value(credentials[key])}")
    return "\n".join(lines) + "\n"


def define_config(
    data_dir: str | Path,
    *,
    api_keys: dict[str, str] | None = None,
    credentials: dict[str, str] | None = None,
    config_path: str | Path | None = None,
) -> None:
    """Create (or overwrite) the Ubib config file.

    Writes ``~/.ubib/config.toml`` and returns nothing. Use :func:`get_config`
    to read the configuration back.

    Parameters
    ----------
    data_dir:
        Folder where downloaded series are cached (one parquet file per series).
    api_keys:
        Mapping of source id -> API key, e.g. ``{"fred": "...", "bls": "..."}``.
        Recognised names: see :data:`API_KEY_NAMES`.
    credentials:
        Mapping of credential name -> value (e.g. ``bcch_user``).
        Recognised names: see :data:`CREDENTIAL_NAMES`.
    config_path:
        Where to write the file. Defaults to ``UBIB_CONFIG`` or
        ``~/.ubib/config.toml``.
    """
    path = Path(config_path).expanduser() if config_path else config_location()
    path.parent.mkdir(parents=True, exist_ok=True)

    api_keys = {k.lower(): str(v) for k, v in (api_keys or {}).items()}
    credentials = {k.lower(): str(v) for k, v in (credentials or {}).items()}

    path.write_text(_render(str(Path(data_dir).expanduser()), api_keys, credentials),
                    encoding="utf-8")
    reset_config_cache()


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load the saved configuration.

    Raises :class:`RuntimeError` if no config exists yet -- call
    :func:`define_config` first.
    """
    path = config_location()
    if not path.exists():
        raise RuntimeError(
            f"No Ubib config found at {path}. Create one first, e.g.:\n"
            "    import ubib\n"
            "    ubib.define_config(data_dir=r'D:/economic_data',\n"
            "                       api_keys={'fred': '...', 'bls': '...'})"
        )

    with path.open("rb") as fh:
        raw = _toml.load(fh)

    data_dir = Path(raw.get("data_dir", "")).expanduser()
    if not str(raw.get("data_dir", "")):
        raise RuntimeError(f"'data_dir' is empty in {path}; set it via define_config().")
    data_dir.mkdir(parents=True, exist_ok=True)

    api_keys = {k.lower(): str(v) for k, v in raw.get("api_keys", {}).items()}
    credentials = {k.lower(): str(v) for k, v in raw.get("credentials", {}).items()}
    return Config(config_path=path, data_dir=data_dir, api_keys=api_keys, credentials=credentials)


def reset_config_cache() -> None:
    """Clear the cached config (after editing the file or in tests)."""
    get_config.cache_clear()
