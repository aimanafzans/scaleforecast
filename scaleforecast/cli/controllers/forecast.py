"""
Option 3: Run Demand Forecast on a dataset.

Refactored from :mod:`scaleforecast.main._handle_forecast`.  Uses the shared
``select_dataset_by_number`` and ``render_technique_menu`` components, killing
the inline dataset-listing and technique-listing boilerplate that was
previously duplicated here.  Records session state for the last-used
technique and dataset so subsequent operations can default to them.
"""

from __future__ import annotations

import os
import time

from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from scaleforecast import config
from scaleforecast.cli.console import console
from scaleforecast.cli.components import render_section_header, render_technique_menu
from scaleforecast.cli.controllers.base import select_dataset_by_number
from scaleforecast.cli.session import SessionState
from scaleforecast.constants import TECHNIQUE_LABELS
from scaleforecast.data_manager import list_datasets
from scaleforecast.executors.concurrent_gil import run as run_gil
from scaleforecast.executors.concurrent_nogil import run as run_nogil
from scaleforecast.executors.parallel_multiprocessing import run as run_mp
from scaleforecast.executors.sequential import run as run_seq
from scaleforecast.interpreter_detection import get_available_techniques
from scaleforecast.report_generator import (
    at_risk_skus, generate_report, restock_recommendations,
)
from scaleforecast.benchmark import DEFAULT_WORKERS

# Maps technique key -> (label, executor.run).  Executors are still kept
# here as the in-process Option 3 path is intentionally simple and does not
# need subprocess isolation (only Option 5 / benchmark.py does).
EXECUTOR_MAP = {
    "sequential": (TECHNIQUE_LABELS["sequential"], run_seq),
    "concurrent_gil": (TECHNIQUE_LABELS["concurrent_gil"], run_gil),
    "concurrent_nogil": (TECHNIQUE_LABELS["concurrent_nogil"], run_nogil),
    "parallel_multiprocessing": (TECHNIQUE_LABELS["parallel_multiprocessing"], run_mp),
}


def run(session: SessionState) -> None:
    """Drive the Option 3 (Run Demand Forecast) sub-flow."""
    render_section_header("Run Demand Forecast")

    while True:
        datasets = list_datasets()
        ds = select_dataset_by_number(datasets, prompt_label="Select a dataset")
        if ds is None:
            return

        techniques = get_available_techniques()
        tech_by_num = render_technique_menu(techniques, dataset_count=ds.sku_count)
        default_tech = "1"
        if session.last_technique_key:
            for idx, key in tech_by_num.items():
                if key == session.last_technique_key:
                    default_tech = str(idx)
                    break
        tech_choice = Prompt.ask("[prompt]Select a technique[/prompt]", default=default_tech)
        if tech_choice.strip().upper() in ("B", "BACK", "Q", "QUIT"):
            continue
        try:
            tech_num = int(tech_choice)
            if tech_num not in tech_by_num:
                console.print("[bad]Invalid or unavailable technique selected.[/bad]")
                continue
            tech_key = tech_by_num[tech_num]
        except ValueError:
            console.print("[bad]Invalid input.[/bad]")
            continue

        tech_label, tech_fn = EXECUTOR_MAP[tech_key]

        console.print()
        with Progress(SpinnerColumn(), TextColumn(f"  Forecasting [accent]{ds.filename}[/accent]\u2026"),
                      console=console, transient=True) as progress:
            progress.add_task("", total=None)
            t0 = time.perf_counter()
            results, timing = tech_fn(ds.filepath, num_workers=DEFAULT_WORKERS)
            elapsed = time.perf_counter() - t0

        report_path = generate_report(results, ds.filename, tech_label)
        at_risk = at_risk_skus(results)
        recommendations = restock_recommendations(results)

        console.print()
        console.print(f"[ok]Forecast complete in {elapsed:.2f}s[/ok]")
        console.print(f"    Technique:                {tech_label}")
        console.print(f"    SKUs processed:           {len(results):,}")
        console.print(f"    At-risk SKUs (High/Crit): {len(at_risk):,}")
        console.print(f"    Restock recommendations:  {len(recommendations):,}")
        console.print(f"    Report saved:             {os.path.basename(report_path)}")

        session.last_technique_key = tech_key
        session.last_dataset_path = ds.filepath
        session.last_dataset_filename = ds.filename
        session.last_num_workers = DEFAULT_WORKERS

        console.print()
        input("Press Enter to return to the main menu...")
        return


__all__ = ["run"]