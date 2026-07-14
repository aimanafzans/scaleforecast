"""
Reusable rich renderers for the ScaleForecast CLI.

All controllers use these shared renderers instead of building their own
tables and panels.  The single ``console`` instance from
:mod:`~scaleforecast.cli.console` ensures consistent styling everywhere.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from rich import box
from rich.align import Align
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from scaleforecast.cli.console import console
from scaleforecast.models import DatasetInfo, ReportInfo, TechniqueInfo


# ── Section header ─────────────────────────────────────────────────────────

def render_section_header(title: str) -> None:
    """Render a consistent section divider with *title* centred on a Rule."""
    console.print()
    console.print(Rule(title, style="border", characters="─"))
    console.print()


# ── Main menu ──────────────────────────────────────────────────────────────

MAIN_MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("1", "Generate Mock SKU Dataset"),
    ("2", "Manage / Delete Datasets"),
    ("3", "Run Demand Forecast (process a dataset)"),
    ("4", "View Forecast Reports"),
    ("5", "Run Performance Benchmark"),
    ("6", "Exit"),
)


def render_main_menu() -> None:
    """Centred, double-border main menu with sub-heading."""
    brand = "[bold cyan]ScaleForecast[/bold cyan] — Demand Forecasting"
    subtitle = "[muted]v1.0  •  A Multi-Technique Concurrent & Parallel Engine[/muted]"
    menu_lines = "\n\n".join(
        f"  [bold accent]{num}.[/bold accent]  {label}"
        for num, label in MAIN_MENU_ITEMS
    )
    body = f"{brand}\n{subtitle}\n\n{menu_lines}"
    panel = Panel(
        body,
        box=box.DOUBLE,
        border_style="border",
        padding=(1, 4),
    )
    console.print()
    console.print(Align.center(panel))
    console.print()


# ── Datasets table ─────────────────────────────────────────────────────────

def render_dataset_table(
    datasets: Sequence[DatasetInfo],
    *,
    title: str = "Available Datasets",
) -> None:
    """Render a d̃atasets table.  Used by Options 1, 2, 3 and 5."""
    table = Table(title=title, box=box.ROUNDED, row_styles=["", "dim"])
    table.add_column("#", style="muted_line", no_wrap=True)
    table.add_column("Filename", style="info")
    table.add_column("SKU Count", justify="right")
    table.add_column("Timestamp")
    table.add_column("Size (MB)", justify="right")

    for i, ds in enumerate(datasets, 1):
        table.add_row(
            str(i),
            ds.filename,
            f"{ds.sku_count:,}",
            ds.timestamp,
            f"{ds.file_size_mb:.2f}",
        )
    console.print(table)


# ── Technique menu (Option 3 pick-list) ────────────────────────────────────

def render_technique_menu(
    techniques: Sequence[TechniqueInfo],
    *,
    dataset_count: Optional[int] = None,
) -> dict[int, str]:
    """
    Render the execution-technique pick-list used by Option 3 as a flat
    numbered list under a Rule header.

    Unavailable techniques are dimmed with their reason.

    Args:
        techniques: Output of :func:`interpreter_detection.get_available_techniques`.
        dataset_count: SKU count of the currently-selected dataset, used to
            annotate the recommended technique.

    Returns:
        ``{displayed_number: technique_key}`` for mapping user input.
    """
    console.print()
    console.print(Rule("Select execution technique", style="border", characters="─"))
    console.print()

    tech_by_num: dict[int, str] = {}
    num = 1

    for t in techniques:
        if not t.available:
            console.print(f"  [muted_line]{num}. {t.label}[/muted_line]")
            if t.unavailable_reason:
                console.print(f"     [muted_line]{t.unavailable_reason}[/muted_line]")
            num += 1
            continue

        marker = ""
        if dataset_count is not None:
            if t.key == "sequential" and dataset_count < 100_000:
                marker = "  [ok](recommended)[/ok]"
            elif t.key == "parallel_multiprocessing" and dataset_count >= 100_000:
                marker = "  [ok](recommended for >100K SKUs)[/ok]"

        console.print(f"  [bold accent]{num}.[/bold accent]  {t.label}{marker}")
        tech_by_num[num] = t.key
        num += 1

    console.print("  [muted_line]B.  Back[/muted_line]")
    console.print()
    return tech_by_num


# ── Reports table (Option 4) ────────────────────────────────────────────────

def render_reports_table(reports: Sequence[ReportInfo]) -> None:
    """Render the generated-reports list (newest-first)."""
    table = Table(title="Generated Reports", box=box.ROUNDED, row_styles=["", "dim"])
    table.add_column("#", style="muted_line", no_wrap=True)
    table.add_column("Filename", style="info")
    table.add_column("Source Dataset")
    table.add_column("Technique")
    table.add_column("SKU Count", justify="right")
    table.add_column("At-Risk", justify="right")
    table.add_column("Date")

    for i, rpt in enumerate(reports, 1):
        date_text = rpt.date[:19] if rpt.date != "Unknown" else "Unknown"
        table.add_row(
            str(i),
            rpt.filename,
            rpt.source_dataset,
            rpt.technique,
            f"{rpt.sku_count:,}",
            str(rpt.at_risk_count),
            date_text,
        )
    console.print(table)


# ── Benchmark results table (Option 5) ─────────────────────────────────────

def render_results_table(
    tech_dict: dict[str, dict[str, Any]],
    sorted_tech_keys: list[str],
    unavailable_techs: dict[str, TechniqueInfo],
    *,
    dataset_label: str,
) -> None:
    """
    Render the post-benchmark TUI results table for one dataset.

    Speedup values are colour-coded: >= 1.0 in green, < 1.0 in yellow.
    """
    table = Table(
        title=f"Benchmark Results — {dataset_label}",
        box=box.ROUNDED,
        row_styles=["", "dim"],
    )
    table.add_column("Technique", style="info")
    table.add_column("Average Time (s)", justify="right")
    table.add_column("Typical Variation (±s)", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_column("Efficiency (%)", justify="right")
    table.add_column("Throughput (rec/s)", justify="right")
    table.add_column("Avg CPU Usage (%)", justify="right")
    table.add_column("Setup Overhead (s)", justify="right")
    table.add_column("Peak Memory (MB)", justify="right")

    for tech_key in sorted_tech_keys:
        agg = tech_dict.get(tech_key)
        if agg is not None:
            sp = agg.get("speedup", 0)
            speedup_str = (
                f"[speedup]{sp:.2f}x[/speedup]" if sp >= 1.0
                else f"[slowdown]{sp:.2f}x[/slowdown]"
            )
            table.add_row(
                _technique_label(tech_key),
                f"{agg.get('wall_time', 0):.3f}",
                f"{agg.get('wall_time_stdev', 0):.3f}",
                speedup_str,
                f"{agg.get('efficiency', 0) * 100:.1f}",
                f"{agg.get('throughput', 0):.0f}",
                f"{agg.get('cpu_overall_percent', 0):.1f}",
                f"{agg.get('overhead_time', 0):.3f}",
                f"{agg.get('peak_memory_mb', 0):.0f}",
            )
            warning = agg.get("gil_warning", "")
            if warning:
                console.print(f"  [bad]{warning}[/bad]")

    for tech_key, tech_info in unavailable_techs.items():
        table.add_row(
            f"[muted_line]{tech_info.label}[/muted_line]",
            "[muted_line]Unavailable[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
            "[muted_line]—[/muted_line]",
        )
        console.print(
            f"  [muted_line]{tech_info.label}: {tech_info.unavailable_reason}[/muted_line]"
        )

    console.print(table)


def render_live_benchmark_table(
    selected_techs: list[str],
    completed: dict[str, dict[str, Any]],
    *,
    dataset_label: str,
    running_tech: str | None = None,
) -> Table:
    """
    Build a one-page table for the ``rich.live.Live`` benchmark display.

    Args:
        selected_techs: Technique keys being benchmarked (in display order).
        completed: ``{ tech_key: aggregated_metrics_dict }``.
        dataset_label: Display label for the current dataset.
        running_tech: The technique currently executing, if any.

    Returns:
        A ``rich.Table`` suitable for use inside a ``Live`` loop.
    """
    table = Table(
        title=f"Live Benchmark — {dataset_label}",
        box=box.ROUNDED,
        row_styles=["", "dim"],
    )
    table.add_column("Technique", style="info", width=22)
    table.add_column("Status", width=14)
    table.add_column("Avg Time (s)", justify="right")
    table.add_column("Speedup", justify="right")
    table.add_column("Efficiency (%)", justify="right")
    table.add_column("CPU (%)", justify="right")
    table.add_column("Mem (MB)", justify="right")

    for tech_key in selected_techs:
        agg = completed.get(tech_key)
        if agg is not None:
            sp = agg.get("speedup", 0)
            speedup_str = (
                f"[speedup]{sp:.2f}x[/speedup]" if sp >= 1.0
                else f"[slowdown]{sp:.2f}x[/slowdown]"
            )
            table.add_row(
                _technique_label(tech_key),
                "[ok]Complete[/ok]",
                f"{agg.get('wall_time', 0):.3f}",
                speedup_str,
                f"{agg.get('efficiency', 0) * 100:.1f}",
                f"{agg.get('cpu_overall_percent', 0):.1f}",
                f"{agg.get('peak_memory_mb', 0):.0f}",
            )
        elif tech_key == running_tech:
            table.add_row(
                _technique_label(tech_key),
                "[accent]Running…[/accent]",
                "—", "—", "—", "—", "—",
            )
        else:
            table.add_row(
                _technique_label(tech_key),
                "[muted_line]Pending[/muted_line]",
                "—", "—", "—", "—", "—",
            )
    return table


def _technique_label(tech_key: str) -> str:
    """Translate an internal technique key to its full display label."""
    from scaleforecast.constants import TECHNIQUE_LABELS
    return TECHNIQUE_LABELS.get(tech_key, tech_key)


def print_variation_legend() -> None:
    """Print the one-line legend that must accompany the first results table."""
    console.print()
    console.print(
        "[muted_line]Variation shows how much timing differed across the repeated "
        "runs — smaller means more consistent results.[/muted_line]"
    )


def print_fastest_slowest(
    tech_dict: dict[str, dict[str, Any]],
    sorted_tech_keys: list[str],
) -> None:
    """
    Print the Fastest / Slowest summary line for one dataset's results.

    Concurrent (With GIL) gets the explicit "no meaningful improvement over
    Sequential, as expected under GIL contention" suffix when it is the
    slowest technique, per PRD Section 6.6.
    """
    from scaleforecast.constants import TECHNIQUE_LABELS

    times_by_tech = {
        k: v.get("wall_time", float("inf"))
        for k, v in tech_dict.items() if k in sorted_tech_keys
    }
    if not times_by_tech:
        return
    fastest_key = min(times_by_tech, key=times_by_tech.get)
    slowest_key = max(times_by_tech, key=times_by_tech.get)
    fastest_label = TECHNIQUE_LABELS.get(fastest_key, fastest_key)
    slowest_label = TECHNIQUE_LABELS.get(slowest_key, slowest_key)
    fastest_speedup = tech_dict[fastest_key].get("speedup", 1.0)

    console.print()
    if fastest_key == "sequential":
        console.print(f"[title]Fastest:[/title] {fastest_label} (baseline)")
    else:
        console.print(
            f"[title]Fastest:[/title] {fastest_label} "
            f"({fastest_speedup:.2f}x speedup over Sequential)"
        )

    if slowest_key != fastest_key:
        if slowest_key == "concurrent_gil":
            console.print(
                f"[title]Slowest:[/title] {slowest_label} — "
                f"no meaningful improvement over Sequential, as expected under GIL contention"
            )
        else:
            console.print(f"[title]Slowest:[/title] {slowest_label}")


# ── Paginator for long lists ───────────────────────────────────────────────

def paginate_table(
    table: Table,
    rows: Sequence[Sequence[str]],
    *,
    page_size: int = 50,
    prompt_label: str = "Page (Enter=n / p / q): ",
) -> None:
    """
    Interactive pager for a ``rich.Table``'s rows.

    Renders *rows* into *table* in pages of ``page_size`` rows at a time,
    prompting between pages.  This replaces the previous "cap at 20-30
    rows and print '... and N more'" footers used by the at-risk and
    restock lists in the reports handler, letting the user actually page
    through long results instead of seeing them truncated.

    Args:
        table: A pre-built ``rich.Table`` whose column headers will be reused
            on every page (rows are added page-by-page).
        rows: All the data rows to page through.
        page_size: Rows per page (default 50).
        prompt_label: Per-page prompt text shown to the user.
    """
    if not rows:
        console.print(table)  # shows just the header
        return

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page_idx = 0

    while True:
        start = page_idx * page_size
        end = start + page_size
        page_rows = rows[start:end]

        # Rebuild the table for this page (rich tables hold rows; we just
        # make a fresh Table per page so column styling stays consistent).
        page_table = Table(
            title=table.title,
            show_header=table.show_header,
            header_style=table.header_style,
        )
        for col in table.columns:
            page_table.add_column(
                col.header,
                style=col.style,
                justify=col.justify,
                no_wrap=col.no_wrap,
            )
        for row in page_rows:
            page_table.add_row(*row)

        console.print()
        console.print(
            f"[muted_line]Page {page_idx + 1} of {total_pages} "
            f"(showing rows {start + 1}–{min(end, total)} of {total})[/muted_line]"
        )
        console.print(page_table)

        if end >= total:
            console.print("[muted_line]  -- end of list --[/muted_line]")
            return

        nav = Prompt.ask(
            f"{prompt_label} (Enter=next / p=previous / b=back)",
            default="n",
        )
        nav = nav.strip().lower()
        if nav in ("b", "q", "back", "quit"):
            return
        elif nav == "p" and page_idx > 0:
            page_idx -= 1
        else:
            page_idx += 1


# ── Error panel ────────────────────────────────────────────────────────────

def render_error_panel(message: str, *, suggestion: Optional[str] = None) -> None:
    """
    Render a friendly red-bordered error panel.

    Used by the top-level error handler in :mod:`cli.app` -- replaces the
    bare ``except Exception: console.print(red)`` pattern.

    Args:
        message: The error description.
        suggestion: Optional plain-language remediation hint (e.g.
            "Try regenerating it via Option 1.").
    """
    body = f"[bad]Error[/bad]  {message}"
    if suggestion:
        body += f"\n\n[muted_line]Suggestion: {suggestion}[/muted_line]"
    console.print(Panel(body, title="[bad]ScaleForecast — Error[/bad]",
                        border_style="red", padding=(1, 2)))


__all__ = [
    "MAIN_MENU_ITEMS",
    "render_section_header",
    "render_main_menu",
    "render_dataset_table",
    "render_technique_menu",
    "render_reports_table",
    "render_results_table",
    "render_live_benchmark_table",
    "print_variation_legend",
    "print_fastest_slowest",
    "paginate_table",
    "render_error_panel",
]