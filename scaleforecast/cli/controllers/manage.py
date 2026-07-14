"""
Option 2: Manage / Delete Datasets.

Refactored with a post-deletion loop: after deleting a dataset the table
refreshes so the user can delete another without returning to the main menu.
Path-traversal rejection is enforced inside
:func:`data_manager.delete_dataset` (Phase 1 hardening).
"""

from __future__ import annotations

from rich.prompt import Confirm, IntPrompt, Prompt

from scaleforecast.cli.console import console
from scaleforecast.cli.components import render_dataset_table, render_section_header
from scaleforecast.cli.controllers.base import is_back
from scaleforecast.cli.session import SessionState
from scaleforecast.data_manager import list_datasets, delete_dataset


def run(session: SessionState) -> None:
    """Drive the Option 2 (Manage / Delete Datasets) sub-flow."""
    render_section_header("Manage / Delete Datasets")

    while True:
        datasets = list_datasets()
        if not datasets:
            console.print("[warn]No datasets found in data/ directory.[/warn]")
            console.print()
            input("Press Enter to return to the main menu...")
            return

        render_dataset_table(datasets, title="Available Datasets")
        console.print()
        console.print("  [bold accent]1.  Delete a single dataset[/bold accent]")
        console.print("  [bold accent]ALL  all datasets[/bold accent]")
        console.print("  [muted_line]B.   Return to main menu[/muted_line]")

        choice = Prompt.ask("[prompt]Select an option[/prompt]", default="B")
        if is_back(choice):
            return

        if choice.strip().upper() == "ALL":
            if not Confirm.ask("[bad]Delete ALL datasets? This cannot be undone.[/bad]",
                               default=False):
                continue
            success, msg = delete_dataset("ALL")
            console.print(f"[ok]{msg}[/ok]" if success else f"[bad]{msg}[/bad]")
            continue

        if choice.strip() == "1":
            try:
                idx = IntPrompt.ask("Enter dataset number to delete") - 1
            except ValueError:
                console.print("[bad]Invalid input. Please enter a number.[/bad]")
                continue
            if not (0 <= idx < len(datasets)):
                console.print("[bad]Invalid selection.[/bad]")
                continue
            ds = datasets[idx]
            if Confirm.ask(f"Delete '{ds.filename}'?", default=False):
                success, msg = delete_dataset(ds.filename)
                console.print(f"[ok]{msg}[/ok]" if success else f"[bad]{msg}[/bad]")
            continue

        console.print("[bad]Unknown option. Please enter 1, ALL, or B.[/bad]")