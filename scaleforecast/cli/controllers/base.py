"""
Shared controller base helpers for the ScaleForecast CLI.

Each controller (generate, manage, forecast, reports, benchmark) is a thin
adapter between an in-domain module (e.g. :mod:`scaleforecast.data_generator`)
and the rich renderers in :mod:`scaleforecast.cli.components`.

This module gathers the small bits of controller logic that recur across
every option: back-navigation, graceful Ctrl-C handling, dataset selection
selectors, and "list-or-empty" guards.
"""

from __future__ import annotations

from typing import Optional, Sequence

from rich.prompt import Prompt

from scaleforecast.cli.console import console
from scaleforecast.cli.components import render_dataset_table
from scaleforecast.models import DatasetInfo


class BackToMenu(Exception):
    """Raised by controllers to break out early and return to the main menu."""


def is_back(value: str) -> bool:
    """Return True if *value* means the user wants to go back/cancel."""
    return value.strip().upper() in ("B", "BACK", "Q", "QUIT")


def select_dataset_by_number(
    datasets: Sequence[DatasetInfo],
    *,
    prompt_label: str = "Select a dataset",
) -> Optional[DatasetInfo]:
    """
    Show a numbered datasets table and ask the user to pick one.

    Returns the chosen :class:`DatasetInfo`, or ``None`` if the user typed
    ``B``/back or entered an invalid index.
    """
    if not datasets:
        console.print("[warn]No datasets found.[/warn]  "
                      "Generate one first (Option 1).")
        return None

    render_dataset_table(datasets, title="Available Datasets")
    console.print()
    console.print("  Enter the [accent]#[/accent] of a dataset, or [muted_line]B[/muted_line] to go back.")

    choice = Prompt.ask(prompt_label, default="B")
    if choice.strip().upper() in ("B", "BACK", "Q", "QUIT"):
        return None
    try:
        idx = int(choice) - 1
    except ValueError:
        console.print("[bad]Invalid input. Please enter a number or B.[/bad]")
        return None
    if not (0 <= idx < len(datasets)):
        console.print(f"[bad]Invalid number. Pick 1–{len(datasets)}.[/bad]")
        return None
    return datasets[idx]


def select_many_datasets(
    datasets: Sequence[DatasetInfo],
    *,
    prompt_label: str = "Select datasets (comma-separated, or A for all)",
) -> Optional[list[DatasetInfo]]:
    """
    Show a numbered datasets table and ask the user to pick one or many.

    Returns a list of :class:`DatasetInfo`, or ``None`` if the user typed
    ``B``/back. Empty selections are rejected with a red message and a
    re-prompt.
    """
    if not datasets:
        console.print("[warn]No datasets found.[/warn]  "
                      "Generate one first (Option 1).")
        return None

    render_dataset_table(datasets, title="Available Datasets")
    console.print()
    console.print("  Enter the [accent]#[/accent]s comma-separated, "
                  "[accent]A[/accent] for all, or [muted_line]B[/muted_line] to go back.")

    choice = Prompt.ask(prompt_label, default="B")
    choice_stripped = choice.strip().upper()
    if choice_stripped in ("B", "BACK", "Q", "QUIT"):
        return None
    if choice_stripped == "A":
        return list(datasets)
    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",") if x.strip()]
    except ValueError:
        console.print("[bad]Invalid input.  Use comma-separated numbers or 'A'.[/bad]")
        return None
    selected: list[DatasetInfo] = []
    for idx in indices:
        if not (0 <= idx < len(datasets)):
            console.print(f"[bad]Invalid index {idx + 1}.[/bad]")
            return None
        selected.append(datasets[idx])
    if not selected:
        console.print("[bad]No datasets selected.[/bad]")
        return None
    return selected


__all__ = [
    "BackToMenu",
    "is_back",
    "select_dataset_by_number",
    "select_many_datasets",
]