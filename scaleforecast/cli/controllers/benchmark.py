"""
Option 5: Run Performance Benchmark.

Uses ``rich.live.Live`` for a live-updating results table during execution.
Session defaults for workers, repeats, and technique are pre-filled at
the prompts.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from scaleforecast import config
from scaleforecast.benchmark import (
    DEFAULT_REPEATS, DEFAULT_WORKERS, TECHNIQUE_REGISTRY,
    run_benchmark, save_benchmark_results,
)
from scaleforecast.chart_generator import generate_all_charts
from scaleforecast.cli.console import console
from scaleforecast.cli.components import (
    print_fastest_slowest, print_variation_legend, render_dataset_table,
    render_live_benchmark_table, render_results_table, render_section_header,
)
from scaleforecast.cli.controllers.base import select_many_datasets
from scaleforecast.cli.session import SessionState
from scaleforecast.data_manager import list_datasets
from scaleforecast.interpreter_detection import (
    get_available_techniques,
)
from scaleforecast.models import TechniqueInfo


def run(session: SessionState) -> None:
    """Drive the Option 5 (Run Performance Benchmark) sub-flow."""
    render_section_header("Run Performance Benchmark")

    # 1. Pick datasets.
    datasets = list_datasets()
    selected = select_many_datasets(
        datasets, prompt_label="Select datasets (comma-separated, or A for all)",
    )
    if selected is None:
        return
    ds_paths = [ds.filepath for ds in selected]

    # 2. Pick techniques with session defaults applied.
    console.print()
    console.print("[heading]Select techniques to benchmark[/heading]")
    techniques = get_available_techniques()

    tech_keys_available: dict[int, str] = {}
    unavailable_techs: dict[str, TechniqueInfo] = {}
    num = 1
    for t in techniques:
        if t.available:
            tech_keys_available[num] = t.key
            marker = ""
            if session.last_technique_key and t.key == session.last_technique_key:
                marker = "  (last used)"
            console.print(f"  [bold accent]{num}.[/bold accent]  {t.label}{marker}")
            num += 1
        else:
            unavailable_techs[t.key] = t
            console.print(f"  [muted_line]  {t.label}[/muted_line]")
            if t.unavailable_reason:
                console.print(f"     [muted_line]{t.unavailable_reason}[/muted_line]")
    console.print("  [bold accent]A.  Select all available[/bold accent]")
    console.print("  [muted_line]B.  Back[/muted_line]")

    # Compute a sensible default prompt:
    #  - If the session has a last-used technique, default to just that number.
    #  - Otherwise default to "A" (all).
    default_tech_prompt = "A"
    if session.last_technique_key:
        for idx, key in tech_keys_available.items():
            if key == session.last_technique_key:
                default_tech_prompt = str(idx)
                break

    tech_choice = Prompt.ask("Select techniques (comma-separated, or A for all)",
                             default=default_tech_prompt)
    choice_stripped = tech_choice.strip().upper()
    if choice_stripped in ("B", "BACK", "Q", "QUIT"):
        return
    if choice_stripped == "A":
        selected_techs = list(tech_keys_available.values())
    else:
        selected_techs = []
        try:
            indices = [int(x.strip()) for x in tech_choice.split(",") if x.strip()]
        except ValueError:
            console.print("[bad]Invalid input. Use comma-separated numbers or 'A'.[/bad]")
            return
        for idx in indices:
            if idx not in tech_keys_available:
                console.print(f"[bad]Invalid or unavailable technique: {idx}[/bad]")
                return
            selected_techs.append(tech_keys_available[idx])
    if not selected_techs:
        console.print("[bad]No valid techniques selected.[/bad]")
        return

    # 3. Repeats + workers — session defaults pre-filled.
    default_repeats = session.last_num_repeats or DEFAULT_REPEATS
    default_workers = session.last_num_workers or DEFAULT_WORKERS
    num_repeats = IntPrompt.ask("Runs per technique", default=default_repeats)
    if num_repeats < 1:
        num_repeats = 1
    num_workers = IntPrompt.ask("Workers", default=default_workers)

    # 4. Config summary + confirmation.
    console.print()
    summary_body = (
        f"  Datasets:    {len(selected)}\n"
        f"  Techniques:  {[TECHNIQUE_REGISTRY[t]['label'] for t in selected_techs]}\n"
        f"  Repeats:     {num_repeats}\n"
        f"  Workers:     {num_workers}"
    )
    console.print(Panel(summary_body, title="[heading]Benchmark Configuration[/heading]",
                        border_style="cyan", padding=(1, 2)))

    if not Confirm.ask("Proceed with benchmark?", default=True):
        return

    # 5. Run benchmark with a live-updating results table (replaces old
    #    Progress spinner+bar).  ``run_benchmark`` is called once across all
    #    datasets; the ``technique_callback`` progressively fills each
    #    dataset's table as techniques complete.
    console.print()
    console.print("[muted_line]Running benchmark...[/muted_line]")

    from scaleforecast.benchmark import _get_dataset_label

    # Track per-dataset completed techniques so the Live table can render.
    _per_ds_completed: dict[str, dict[str, dict]] = {}
    _per_ds_running: dict[str, str | None] = {}

    _live_ref: Optional[Live] = None
    _active_ds: list[str] = []

    def _on_technique(tech_key: str, ds_path: str, agg: dict) -> None:
        """Fires after one technique finishes all repeats for a dataset."""
        ds_map = _per_ds_completed.setdefault(ds_path, {})
        ds_map[tech_key] = agg
        _per_ds_running[ds_path] = _next_tech(tech_key)
        if ds_path == _active_ds[-1] if _active_ds else None and _live_ref is not None:
            _refresh_live(_live_ref, ds_path, _active_ds if _active_ds else [])

    def _next_tech(tech_key: str) -> str | None:
        try:
            idx = selected_techs.index(tech_key)
            return selected_techs[idx + 1] if idx + 1 < len(selected_techs) else None
        except ValueError:
            return None

    def _refresh_live(live: Live, ds_path: str, all_ds: list[str]) -> None:
        completed = _per_ds_completed.get(ds_path, {})
        ds_label = _get_dataset_label(ds_path)
        title = f"Live Benchmark — {ds_label}"
        if len(all_ds) > 1:
            idx = all_ds.index(ds_path) + 1 if ds_path in all_ds else 0
            title += f" (dataset {idx}/{len(all_ds)})"
        live.update(render_live_benchmark_table(
            selected_techs, completed,
            dataset_label=title,
            running_tech=_per_ds_running.get(ds_path),
        ))
        live.refresh()

    # Pre-populate running state: first technique of first dataset.
    for dp in ds_paths:
        _per_ds_running[dp] = selected_techs[0] if selected_techs else None

    with Live(console=console, auto_refresh=False) as live:
        _live_ref = live
        if ds_paths:
            _active_ds = ds_paths
            _refresh_live(live, ds_paths[0], ds_paths)

        bench_results = run_benchmark(
            dataset_paths=ds_paths,
            technique_keys=selected_techs,
            num_repeats=num_repeats,
            num_workers=num_workers,
            technique_callback=_on_technique,
        )

        # Final update: all rows "Complete" for the last dataset.
        if ds_paths:
            last_ds = ds_paths[-1]
            _per_ds_running[last_ds] = None
            final_agg = bench_results["per_dataset"].get(last_ds, {})
            _per_ds_completed[last_ds] = final_agg
            _refresh_live(live, last_ds, ds_paths)

    console.print()
    console.print("[ok]Benchmark complete![/ok]")

    # 6. Render the per-dataset TUI table AFTER the live session.
    variation_legend_shown = False
    for ds_path in ds_paths:
        ds_label = _get_dataset_label(ds_path)
        tech_dict = bench_results["per_dataset"].get(ds_path, {})

        console.print()
        console.print(f"[heading]Results for {ds_label}[/heading]")
        render_results_table(
            tech_dict, selected_techs, unavailable_techs, dataset_label=ds_label,
        )

        if not variation_legend_shown:
            print_variation_legend()
            variation_legend_shown = True

        print_fastest_slowest(tech_dict, selected_techs)

    # 8. Post-benchmark opt-in prompts (charts, CSV, JSON).
    #    All output from this run goes into a timestamped subfolder so
    #    multiple benchmark runs don't mix files.
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(str(config.BENCHMARKS_DIR), f"benchmark_{run_timestamp}")
    os.makedirs(run_dir, exist_ok=True)

    console.print()
    if Confirm.ask("Generate charts?", default=True):
        try:
            chart_paths = generate_all_charts(bench_results, output_dir=run_dir)
            for p in chart_paths:
                console.print(f"  [ok]Saved:[/ok] {os.path.basename(p)}")
        except Exception as e:
            console.print(f"[bad]Chart generation failed: {e}[/bad]")

    console.print()
    if Confirm.ask("Save summary CSV?", default=True):
        json_path, csv_path = save_benchmark_results(bench_results, output_dir=run_dir)
        console.print(f"  [ok]Saved:[/ok] {os.path.basename(csv_path)}")
    else:
        csv_path = None

    console.print()
    if Confirm.ask("Save raw results JSON?", default=True):
        if csv_path is None:
            json_path, _ = save_benchmark_results(bench_results, output_dir=run_dir)
        console.print(f"  [ok]Saved:[/ok] {os.path.basename(json_path)}")

    # Record the session defaults so subsequent runs start from these.
    session.last_num_repeats = num_repeats
    session.last_num_workers = num_workers
    if selected_techs:
        session.last_technique_key = selected_techs[0]

    console.print()
    input("Press Enter to return to the main menu...")


__all__ = ["run"]