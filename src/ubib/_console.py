"""Console feedback for downloads: colored per-series messages + a progress bar.

Colors use ANSI codes (enabled on Windows via colorama when available). The
progress bar uses tqdm when available; both degrade gracefully to plain prints
if the optional packages aren't installed.
"""

from __future__ import annotations

import sys

_GREEN = "\033[1;32m"
_RED = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET = "\033[0m"

# Best-effort: make ANSI colors work in legacy Windows consoles.
try:  # pragma: no cover - environment dependent
    import colorama

    if hasattr(colorama, "just_fix_windows_console"):
        colorama.just_fix_windows_console()
    else:
        colorama.init()
except Exception:  # noqa: BLE001
    pass

try:  # pragma: no cover - optional dependency
    from tqdm.auto import tqdm

    _HAVE_TQDM = True
except Exception:  # noqa: BLE001
    _HAVE_TQDM = False


def _emit(message: str) -> None:
    # tqdm.write keeps messages from breaking an active progress bar.
    if _HAVE_TQDM:
        tqdm.write(message)
    else:
        print(message)
        sys.stdout.flush()


def ok(message: str) -> None:
    _emit(f"{_GREEN}✓ {message}{_RESET}")


def fail(message: str) -> None:
    _emit(f"{_RED}✗ {message}{_RESET}")


def warn(message: str) -> None:
    _emit(f"{_YELLOW}! {message}{_RESET}")


def progress(items, *, desc: str = "Loading"):
    """Wrap ``items`` in a tqdm bar when there's more than one and tqdm exists."""
    items = list(items)
    if _HAVE_TQDM and len(items) > 1:
        return tqdm(items, desc=desc, unit="series")
    return items
