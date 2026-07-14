"""
Session state for the ScaleForecast CLI.

A single :class:`SessionState` instance is created at app startup and
passed to every controller. It holds "last used" defaults so the user
doesn't have to re-select common settings on every operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionState:
    """In-memory defaults shared across controllers within a CLI session."""

    last_technique_key: Optional[str] = None
    """Most recently selected execution technique (Option 3 / Option 5)."""

    last_num_workers: Optional[int] = None
    """Most recently used worker count (Option 5)."""

    last_num_repeats: Optional[int] = None
    """Most recently used repeats count (Option 5)."""

    last_dataset_path: Optional[str] = None
    """Most recently processed dataset filepath (any of Options 3 / 5)."""

    last_dataset_filename: Optional[str] = None
    """Filename companion to ``last_dataset_path`` (for display defaults)."""


__all__ = ["SessionState"]