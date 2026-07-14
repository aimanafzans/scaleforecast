"""
Option 1: Generate Mock SKU Dataset.

Generates a timestamped CSV of synthetic SKU records.  Supports 5 volume
tiers + custom count, configurable category distribution, and deterministic
seeding.  Press B at any prompt to cancel.
"""

from __future__ import annotations

import os

from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn,
)
from rich.prompt import Prompt

from scaleforecast.cli.console import console
from scaleforecast.cli.components import render_section_header
from scaleforecast.cli.controllers.base import is_back
from scaleforecast.cli.session import SessionState
from scaleforecast.data_generator import (
    generate_dataset, get_dataset_info,
    VOLUME_TIERS, DEFAULT_CATEGORY_DISTRIBUTION, CATEGORIES,
)

def run(session: SessionState) -> None:
    """Drive the Option 1 (Generate Mock SKU Dataset) sub-flow."""
    render_section_header("Generate Mock SKU Dataset")

    while True:
        body_lines = "\n".join(
            f"  [bold accent]{i}.[/bold accent]  {count:,} SKUs"
            for i, count in VOLUME_TIERS.items()
        ) + "\n  [bold accent]6.  Custom SKU count[/bold accent]" \
          + "\n  [muted_line]B.  Back[/muted_line]"
        console.print(Panel(body_lines, title="[heading]Volume Tiers[/heading]",
                            border_style="border", padding=(1, 2)))

        tier = Prompt.ask("[prompt]Select tier[/prompt]")
        if is_back(tier):
            return
        if tier == "6":
            custom = Prompt.ask("[prompt]Enter custom SKU count (or B to cancel)[/prompt]",
                                default="10000")
            if is_back(custom):
                return
            try:
                num_skus = int(custom)
                if num_skus < 1:
                    console.print("[bad]SKU count must be >= 1.[/bad]")
                    return
            except ValueError:
                console.print("[bad]Invalid number.[/bad]")
                return
        elif tier in VOLUME_TIERS:
            num_skus = VOLUME_TIERS[tier]
        else:
            console.print("[bad]Invalid tier selection. Enter 1-6 or B.[/bad]")
            return

        console.print()
        cat_choice = Prompt.ask(
            "[prompt]Use default category distribution? (y/n/B)[/prompt]",
            default="y",
        )
        if is_back(cat_choice):
            return
        use_default = cat_choice.strip().lower().startswith("y") if cat_choice.strip() else True
        if use_default:
            cat_dist = DEFAULT_CATEGORY_DISTRIBUTION
        else:
            cat_dist = {}
            console.print("Enter percentage (0–100) for each category (B to use defaults):")
            for cat in CATEGORIES:
                default_pct = int(DEFAULT_CATEGORY_DISTRIBUTION.get(cat, 0) * 100)
                ans = Prompt.ask(f"  [prompt]{cat}[/prompt]", default=str(default_pct))
                if is_back(ans):
                    console.print("[muted_line]Using default category distribution.[/muted_line]")
                    cat_dist = DEFAULT_CATEGORY_DISTRIBUTION
                    break
                try:
                    cat_dist[cat] = int(ans) / 100.0
                except ValueError:
                    console.print("[bad]Invalid number, using default.[/bad]")
                    cat_dist = DEFAULT_CATEGORY_DISTRIBUTION
                    break

        seed_str = Prompt.ask("[prompt]Random seed (Enter=random, B=back)[/prompt]", default="")
        if is_back(seed_str):
            return
        seed = int(seed_str) if seed_str.strip() else None

        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:,}/{task.total:,}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Generating dataset...", total=num_skus)

            def _update(current, total):
                progress.update(task, completed=current)

            filepath = generate_dataset(
                num_skus=num_skus,
                category_distribution=cat_dist,
                seed=seed,
                progress_callback=_update,
            )

        info = get_dataset_info(filepath)
        console.print()
        console.print(f"[ok]Dataset generated:[/ok]  {os.path.basename(filepath)}")
        console.print(f"    Records: {info['sku_count']:,}")
        console.print(f"    File size: {info['file_size_mb']} MB")

        session.last_dataset_path = filepath
        session.last_dataset_filename = os.path.basename(filepath)

        console.print()
        console.print("  [bold accent]1.  Generate another dataset[/bold accent]")
        console.print("  [muted_line]B.  Return to main menu[/muted_line]")
        choice = Prompt.ask("[prompt]Select an option[/prompt]", default="1")
        if is_back(choice):
            return


__all__ = ["run"]