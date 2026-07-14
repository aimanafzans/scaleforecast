"""
ScaleForecast CLI entry point.

Hosts the main menu loop and dispatch to the appropriate controller for
each option.  Delegates to :mod:`scaleforecast.cli.app.run`.
"""

from __future__ import annotations

import multiprocessing
import sys

from rich.prompt import Prompt

from scaleforecast.cli.console import console
from scaleforecast.cli.components import render_error_panel, render_main_menu, MAIN_MENU_ITEMS
from scaleforecast.cli.controllers.base import BackToMenu
from scaleforecast.cli.session import SessionState


def _print_header() -> None:
    """Clear the terminal before rendering the main menu."""
    console.clear()


def _read_menu_choice() -> str:
    """Display the styled main menu and prompt for a 1–6 choice."""
    render_main_menu()
    while True:
        choice = Prompt.ask("Enter your choice")
        valid = {num for num, _ in MAIN_MENU_ITEMS}
        if choice in valid:
            return choice
        console.print(f"[bad]Please enter a number from 1 to {max(valid)}.[/bad]")


def run() -> None:
    """Top-level CLI entry point: header, menu loop, dispatch."""
    if sys.platform == "win32":
        multiprocessing.freeze_support()

    session = SessionState()
    _print_header()

    # Controllers are imported lazily so that a fast `python -m scaleforecast`
    # for testing doesn't pay the startup cost of every sub-module.
    def _controller(option: str):
        from scaleforecast.cli.controllers import (
            generate, manage, forecast, reports, benchmark,
        )
        return {
            "1": generate.run,
            "2": manage.run,
            "3": forecast.run,
            "4": reports.run,
            "5": benchmark.run,
        }.get(option)

    while True:
        try:
            choice = _read_menu_choice()
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print("[warn]Exiting ScaleForecast. Goodbye![/warn]")
            return

        if choice == "6":
            console.print("[warn]Exiting ScaleForecast. Goodbye![/warn]")
            return

        handler = _controller(choice)
        if handler is None:
            console.print("[bad]Unknown choice.[/bad]")
            continue

        try:
            handler(session)
        except BackToMenu:
            pass
        except KeyboardInterrupt:
            console.print("[warn]Interrupted — returning to main menu.[/warn]")
        except Exception as exc:  # noqa: BLE001
            suggestion = _suggest_for(exc)
            render_error_panel(str(exc), suggestion=suggestion)
            console.print()
            input("Press Enter to continue...")

        # Clear and re-show header before re‑rendering the menu.
        _print_header()


def _suggest_for(exc: Exception) -> str | None:
    """
    Map a few common error types/discovery clues to a plain-language remediation
    hint shown alongside the red error panel.
    """
    msg = str(exc).lower()
    exc_name = type(exc).__name__.lower()
    if "no dataset" in msg or "datasets found" in msg:
        return "Generate one first via Option 1 (Generate Mock SKU Dataset)."
    if "no report" in msg or "reports found" in msg:
        return "Run a forecast first via Option 3 (Run Demand Forecast)."
    if "interpreter" in msg or "python3.13t" in msg:
        return (
            "Install the free-threaded Python build to enable Concurrent (No GIL): "
            "python.org -> free-threaded installer, or 'pyenv install 3.13t'."
        )
    if "not found" in msg:
        return "The selected file may have been moved or deleted. Try refreshing the list."
    if "column" in msg:
        return (
            "The CSV file may be in an older format or missing a required column. "
            "Try regenerating it via Option 1."
        )
    if "permission" in msg or "access denied" in msg:
        return "Close any programs that may have the file open (e.g. Excel) and try again."
    if "memory" in msg or "memoryerror" in exc_name:
        return "Try a smaller dataset or fewer worker threads/processes."
    return None


__all__ = ["run"]