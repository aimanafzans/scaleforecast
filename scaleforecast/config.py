"""
Filesystem paths and security helpers for ScaleForecast.

``DATA_DIR``, ``REPORTS_DIR`` and ``BENCHMARKS_DIR`` are
:class:`pathlib.Path` objects relative to the package root.
``validate_filename()`` blocks path-traversal characters in
user-supplied filenames before they're joined onto managed directories.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Project directory layout ───────────────────────────────────────────────

PACKAGE_DIR: Path = Path(__file__).resolve().parent
"""Absolute path to the installed ``scaleforecast`` package directory."""

PROJECT_ROOT: Path = PACKAGE_DIR.parent
"""One level above the package — the user's project directory."""

DATA_DIR: Path = PACKAGE_DIR / "data"
"""Generated SKU dataset CSVs are written here."""

REPORTS_DIR: Path = PACKAGE_DIR / "reports"
"""Generated forecast-report CSVs are written here."""

BENCHMARKS_DIR: Path = PACKAGE_DIR / "benchmarks"
"""Generated benchmark summary CSVs, raw JSON and chart PNGs go here."""


def ensure_dir(path: str | os.PathLike[str] | Path) -> None:
    """Create *path* if it does not exist (idempotent, no error if it does)."""
    Path(path).mkdir(parents=True, exist_ok=True)


def ensure_dirs(*paths: str | os.PathLike[str] | Path) -> None:
    """Create all *paths* if missing. Convenience wrapper around :func:`ensure_dir`."""
    for p in paths:
        ensure_dir(p)


def ensure_default_dirs() -> None:
    """Create DATA_DIR, REPORTS_DIR and BENCHMARKS_DIR if missing."""
    ensure_dirs(DATA_DIR, REPORTS_DIR, BENCHMARKS_DIR)


# ── Filename validation (security) ─────────────────────────────────────────

# Characters whose presence in a bare filename should never be allowed when
# that filename is later joined with a managed directory: they can either
# escape the directory (path separators, drive separators on Windows) or
# traverse to a parent directory.
_FORBIDDEN_FILENAME_SEQUENCES: tuple[str, ...] = ("/", "\\", "..")
"""Substrings that disqualify a filename from being used for deletion."""


class InvalidFilenameError(ValueError):
    """Raised when a supplied filename is not a bare, safe basename."""


def validate_filename(filename: str) -> None:
    """
    Reject any *filename* that is not a bare, safe basename.

    A safe basename is one that, when joined to a managed directory, cannot
    escape that directory. Concretely this rejects names containing:

      - forward slash (``/``) — POSIX path separator
      - backslash (``\\``) — Windows path separator / drive escape
      - the literal substring ``..`` — parent-directory traversal

    Raises:
        InvalidFilenameError: if the filename is unsafe.

    Examples:
        >>> validate_filename("sku_dataset_1000_20260708.csv")
        >>> validate_filename("../evil.csv")
        Traceback (most recent call last):
            ...
        scaleforecast.config.InvalidFilenameError: ...
    """
    if not isinstance(filename, str):
        raise InvalidFilenameError(f"Filename must be a string, got {type(filename).__name__}.")
    if not filename:
        raise InvalidFilenameError("Filename must not be empty.")
    for token in _FORBIDDEN_FILENAME_SEQUENCES:
        if token in filename:
            raise InvalidFilenameError(
                f"Unsafe filename {filename!r}: contains {token!r} "
                "(path separators / parent-traversal are not allowed)."
            )


__all__ = [
    "PACKAGE_DIR",
    "PROJECT_ROOT",
    "DATA_DIR",
    "REPORTS_DIR",
    "BENCHMARKS_DIR",
    "ensure_dir",
    "ensure_dirs",
    "ensure_default_dirs",
    "InvalidFilenameError",
    "validate_filename",
]