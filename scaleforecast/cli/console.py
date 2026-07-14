"""
Shared :mod:`rich` console and theme helpers for the ScaleForecast CLI.

All controllers import the single ``console`` instance from here so styling
is consistent across every menu / panel / table.  Centralising the Console
avoids the trap of each sub-module constructing its own ``Console()``
(which would subtly disagree on width / theme / unicode detection in edge
cases such as a piped non-tty stdout).
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

# A small theme so colours are NAME'd rather than re-typed inline around
# the codebase.  Any controller wanting "the success colour" asks for
# ``console.print("[ok]done[/ok]")`` rather than hardcoding green etc.
SCALEFORECAST_THEME = Theme({
    "ok": "bold green",
    "warn": "bold yellow",
    "bad": "bold red",
    "info": "cyan",
    "accent": "bold cyan",
    "title": "bold",
    "warn_line": "yellow",
    "muted": "dim",
    "muted_line": "dim",
    "heading": "bold cyan underline",
    "border": "bright_black",
    "prompt": "bright_cyan",
    "row_alt": "dim",
    "speedup": "bold green",
    "slowdown": "yellow",
})

console: Console = Console(theme=SCALEFORECAST_THEME)
"""The single shared :class:`rich.console.Console` used across the CLI."""


__all__ = ["console", "SCALEFORECAST_THEME"]