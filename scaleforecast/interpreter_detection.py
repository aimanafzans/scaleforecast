"""
Python interpreter and GIL detection for ScaleForecast.

Auto-detects whether the current interpreter runs with or without the
Global Interpreter Lock, whether a free-threaded build is available on
PATH, and which execution techniques are usable.

Module-level flags (``GIL_ENABLED``, ``IS_FREE_THREADED``, etc.) are set
eagerly on import via :func:`init`, which is idempotent.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional, Union

from scaleforecast.constants import PYTHON_FREETHREADED_CANDIDATES, DEFAULT_Z_FALLBACK
from scaleforecast.models import TechniqueInfo

# Detect python3.13t candidates from constants (was hardcoded twice here).


# -- Session-level flags -----------------------------------------------------

GIL_ENABLED: bool = True
"""True if the GIL is active (standard CPython build)."""

IS_FREE_THREADED: bool = False
"""True if running under a free-threaded CPython build (python3.13t)."""

FREE_THREADED_ON_PATH: bool = False
"""True if python3.13t is installed on the system PATH (even if not running it)."""

INTERPRETER_ID: str = "unknown"
"""Human-readable interpreter build identifier for logging/reporting."""

_INITIALIZED: bool = False
"""Tracks whether init() has run, used to make detection idempotent."""

# For unit testing: allows forcing GIL status to simulate both code paths.
_FORCE_GIL: Optional[bool] = None


def init() -> None:
    """
    Run interpreter detection exactly once.

    Safe to call multiple times -- subsequent calls are no-ops. Modules that
    rely on the session flags should call this at startup (e.g. main.py),
    but it is also called lazily by the accessors below so callers in
    library/test contexts do not need to remember to invoke it.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _detect_interpreter()
    _INITIALIZED = True


def _detect_interpreter() -> None:
    """
    Detect GIL status and interpreter build type.

    Uses ``sys._is_gil_enabled()`` (Python 3.13+) if available. Falls back
    to GIL-enabled default for Python < 3.13 or implementations lacking the
    attribute (see :data:`constants.DEFAULT_Z_FALLBACK`).
    """
    global GIL_ENABLED, IS_FREE_THREADED, INTERPRETER_ID, _FORCE_GIL
    global FREE_THREADED_ON_PATH

    version_str = sys.version

    if _FORCE_GIL is not None:
        GIL_ENABLED = _FORCE_GIL
    elif hasattr(sys, "_is_gil_enabled"):
        GIL_ENABLED = sys._is_gil_enabled()
    else:
        GIL_ENABLED = DEFAULT_Z_FALLBACK

    IS_FREE_THREADED = not GIL_ENABLED

    if "free-threading" in version_str.lower() or (
        hasattr(sys, "abiflags") and "t" in getattr(sys, "abiflags", "")
    ):
        INTERPRETER_ID = "Free-threaded CPython"
    elif not GIL_ENABLED:
        INTERPRETER_ID = "Free-threaded CPython (detected via _is_gil_enabled)"
    else:
        INTERPRETER_ID = "Standard CPython (GIL enabled)"

    INTERPRETER_ID += f" — {sys.version.split(chr(10))[0].strip()}"

    FREE_THREADED_ON_PATH = _check_free_threaded_on_path()


def get_interpreter_info() -> dict[str, Union[str, bool, int]]:
    """Return interpreter metadata for benchmark output and logging."""
    init()
    return {
        "interpreter_id": INTERPRETER_ID,
        "gil_enabled": GIL_ENABLED,
        "is_free_threaded": IS_FREE_THREADED,
        "free_threaded_on_path": FREE_THREADED_ON_PATH,
        "python_version": sys.version.split(chr(10))[0].strip(),
        "cpu_count_logical": _cpu_count(),
    }


def _check_free_threaded_on_path() -> bool:
    """Check whether python3.13t exists on the system PATH or in known install locations."""
    candidates = list(PYTHON_FREETHREADED_CANDIDATES)
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue

    # Also search known install directories on Windows (most-recent-first).
    known_dirs: list[str] = []
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        python_base = os.path.join(local_appdata, "Programs", "Python")
        if os.path.isdir(python_base):
            try:
                # Sort subdirectories descending so Python314 is searched before Python313
                entries = sorted(os.listdir(python_base), reverse=True)
            except OSError:
                entries = []
            for entry in entries:
                full = os.path.join(python_base, entry)
                if os.path.isdir(full):
                    known_dirs.append(full)

    for base in known_dirs:
        exe_path = os.path.join(base, "python3.13t.exe")
        if os.path.isfile(exe_path):
            return True

    return False


def get_available_techniques() -> list[TechniqueInfo]:
    """
    Return the list of execution techniques available in the current session.

    Each entry is a :class:`TechniqueInfo` dataclass with:

      - ``key``: internal technique identifier (e.g. "sequential")
      - ``label``: display name for menus
      - ``available``: ``True`` if the technique can run in this session
      - ``unavailable_reason``: explanation if ``available`` is False
    """
    init()
    return [
        TechniqueInfo(
            key="sequential",
            label="Sequential",
            available=True,
        ),
        TechniqueInfo(
            key="concurrent_gil",
            label="Concurrent (With GIL)",
            available=True,
        ),
        TechniqueInfo(
            key="concurrent_nogil",
            label="Concurrent (No GIL)",
            available=(IS_FREE_THREADED or FREE_THREADED_ON_PATH),
            unavailable_reason=_nogil_unavailable_reason(),
        ),
        TechniqueInfo(
            key="parallel_multiprocessing",
            label="Multiprocessing",
            available=True,
        ),
    ]


def _nogil_unavailable_reason() -> str:
    """Return the appropriate unavailable message for Concurrent (No GIL)."""
    init()
    if IS_FREE_THREADED:
        return ""
    if FREE_THREADED_ON_PATH:
        return (
            "Not available under this interpreter session. "
            "Restart with 'python3.13t -m scaleforecast.main' to enable it."
        )
    return (
        "Requires the free-threaded Python build (python3.13t). "
        "Install it from python.org (select the free-threaded installer) "
        "or via 'pyenv install 3.13t'."
    )


def _cpu_count() -> int:
    """Return logical CPU count, safe across platforms."""
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


# Run detection eagerly when imported as a library (preserves prior behaviour
# for any caller that reads the module-level flags at import time). Callers
# that import this module programmatically can ignore init() -- it is
# idempotent and the accessors also call it defensively.
init()