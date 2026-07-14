"""
Chart generator for ScaleForecast benchmark results.

Produces 8 charts for ITT440 academic presentations (PRD Section 8.2 +
Phase 5 extensions):
  1. Time vs. Data Size (line chart, log-scale x-axis, ±1σ error bars)
  2. Speedup vs. Data Size (line chart, reference line at 1.0, ±1σ error bars)
  3. CPU Utilization Comparison (grouped bar chart across all dataset sizes)
  4. Overhead vs. Compute Time Breakdown (stacked bar chart)
  5. Peak Memory Usage Comparison (bar chart at largest dataset)
  6. Efficiency vs. Data Size (line chart, reference line at 100%)
  7. Throughput vs. Data Size (line chart, log-scale x-axis)
  8. Per-Dataset Time Comparison (grouped bar chart — all techniques per dataset)

When ``presentation_mode=True`` (default), charts use 300 DPI and
presentation-grade font sizes (12pt).  All charts include a metadata
subtitle showing Python version, GIL status, CPU count, and worker count.

All charts are saved to the benchmarks/ directory as PNG + SVG files.
"""

import os
from datetime import datetime
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from scaleforecast import config
from scaleforecast.constants import (
    TECHNIQUE_COLORS,
    TECHNIQUE_LABELS,
    TECHNIQUE_DEFAULT_COLOR,
    CHART_DPI,
    CHART_DPI_PRESENTATION,
    CHART_FIGSIZE,
    CHART_FIGSIZE_WIDE,
    CHART_MARKER_SIZE,
    CHART_LINE_WIDTH,
    CHART_GRID_ALPHA,
    CHART_ALPHA_OVERLAY,
    CHART_HATCH,
    CHART_FONT_SIZE_LEGEND,
    CHART_FONT_SIZE_LEGEND_PRESENTATION,
    CHART_FONT_SIZE_TICKS,
    CHART_FONT_SIZE_TICKS_PRESENTATION,
    CHART_FONT_SIZE_ANNOTATE,
    CHART_FONT_SIZE_ANNOTATE_PRESENTATION,
    CHART_FONT_SIZE_LEGEND_SMALL,
    CHART_BAR_WIDTH,
    CHART_CPU_YLIM_FLOOR,
    CHART_CPU_YLIM_PAD,
    CHART_AXIS_PAD,
    CHART_ROTATION,
    CHART_TIMESTAMP_FORMAT,
    CHART_FILENAME_PREFIX,
    CHART_FILENAME_SUFFIX,
)

TECHNIQUE_DISPLAY_ORDER: tuple[str, ...] = (
    "sequential",
    "concurrent_gil",
    "concurrent_nogil",
    "parallel_multiprocessing",
)
"""Explicit left-to-right ordering of technique bars in categorical charts."""


def _extract_chart_data(benchmark_results: dict) -> dict[str, dict[str, dict]]:
    """
    Extract structured data from benchmark results for charting.

    Returns: ``{ technique_key: { dataset_label: aggregated_metrics } }``
    """
    from scaleforecast.benchmark import _get_dataset_label, _extract_dataset_size_int

    data: dict[str, dict[str, dict]] = {}
    for ds_path, tech_dict in benchmark_results.get("per_dataset", {}).items():
        ds_label = _get_dataset_label(ds_path)
        for tech_key, agg in tech_dict.items():
            if tech_key not in data:
                data[tech_key] = {}
            ds_size = agg.get("dataset_size", 0)
            if not ds_size:
                ds_size = _extract_dataset_size_int(ds_path)
            data[tech_key][ds_label] = {**agg, "size": ds_size}
    return data


def _find_largest_dataset(chart_data: dict[str, dict[str, dict]]) -> str:
    """Return the dataset LABEL with the largest numeric size."""
    max_size = 0
    max_label = ""
    for ds_dict in chart_data.values():
        for label, agg in ds_dict.items():
            s = agg.get("size", 0)
            if s > max_size:
                max_size = s
                max_label = label
    return max_label


def _ordered_tech_keys(chart_data: dict) -> list[str]:
    """Return technique keys in display order, filtered to those actually present."""
    return [k for k in TECHNIQUE_DISPLAY_ORDER if k in chart_data]


def _sort_labels_by_size(ds_dict: dict[str, dict]) -> list[str]:
    """Sort dataset labels by their numeric size field."""
    return sorted(ds_dict.keys(), key=lambda lbl: ds_dict[lbl].get("size", 0))


def _metadata_subtitle(results: dict, presentation: bool) -> str:
    """Build a metadata subtitle string from benchmark results."""
    meta = results.get("metadata", {})
    py_ver = meta.get("python_version", "unknown")
    gil = "GIL enabled" if meta.get("gil_enabled", True) else "Free-threaded"
    cpu = meta.get("cpu_count_logical", os.cpu_count() or 1)
    workers = meta.get("num_workers", 0)
    lines = [
        f"Python {py_ver}  |  {gil}  |  {cpu} logical CPUs  |  {workers} workers"
    ]
    if presentation:
        lines.append("ScaleForecast — ITT440 Concurrent & Parallel Programming")
    return "\n".join(lines)


def _font_size(base: int, pres: int, presentation: bool) -> int:
    return pres if presentation else base


def generate_all_charts(
    benchmark_results: dict[str, Any],
    output_dir: Optional[str] = None,
    *,
    presentation_mode: bool = True,
) -> list[str]:
    """
    Generate all benchmark charts and save as PNG + SVG files.

    Args:
        benchmark_results: The dict returned by benchmark.run_benchmark().
        output_dir: Directory for chart files. Defaults to scaleforecast/benchmarks/.
        presentation_mode: If True, use 300 DPI and larger fonts suitable
            for projection/slides.

    Returns:
        List of paths to generated files (PNG and SVG).
    """
    if output_dir is None:
        output_dir = str(config.BENCHMARKS_DIR)
    config.ensure_dir(output_dir)

    timestamp = datetime.now().strftime(CHART_TIMESTAMP_FORMAT)
    chart_data = _extract_chart_data(benchmark_results)

    chart_funcs = [
        _chart_time_vs_size,
        _chart_speedup_vs_size,
        _chart_cpu_util,
        _chart_overhead_breakdown,
        _chart_memory,
        _chart_efficiency_vs_size,
        _chart_throughput_vs_size,
    ]

    paths: list[str] = []
    for func in chart_funcs:
        png_path = func(chart_data, output_dir, timestamp,
                        results=benchmark_results,
                        presentation=presentation_mode)
        paths.append(png_path)

    return paths


def _style_and_save(
    fig, ax, filepath: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Apply common styling and save the figure."""
    legend_fs = _font_size(CHART_FONT_SIZE_LEGEND, CHART_FONT_SIZE_LEGEND_PRESENTATION, presentation)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=legend_fs, loc="best")
    ax.grid(True, alpha=CHART_GRID_ALPHA)
    if results:
        sub = _metadata_subtitle(results, presentation)
        tick_fs = _font_size(CHART_FONT_SIZE_TICKS, CHART_FONT_SIZE_TICKS_PRESENTATION, presentation)
        fig.text(0.5, 0.01, sub, ha="center", va="bottom",
                 fontsize=tick_fs, style="italic", color="gray")
        fig.subplots_adjust(bottom=0.12)
    dpi = CHART_DPI_PRESENTATION if presentation else CHART_DPI
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return filepath


# ── Chart 1: Time vs. Data Size ────────────────────────────────────────────

def _chart_time_vs_size(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 1: Time vs. Data Size — line chart with ±1σ error bars."""
    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)

    for tech_key in _ordered_tech_keys(chart_data):
        ds_dict = chart_data[tech_key]
        sizes = []
        times = []
        stdevs = []
        for ds_label in _sort_labels_by_size(ds_dict):
            agg = ds_dict[ds_label]
            s = agg.get("size", 0)
            if s > 0:
                sizes.append(s)
                times.append(agg.get("wall_time", 0))
                stdevs.append(agg.get("wall_time_stdev", 0))
        if sizes:
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            ax.errorbar(sizes, times, yerr=stdevs if any(stdevs) else None,
                        fmt="o-", label=label, color=color,
                        markersize=CHART_MARKER_SIZE, linewidth=CHART_LINE_WIDTH,
                        capsize=4)

    ax.set_xscale("log")
    ax.set_title("Execution Time vs. Dataset Size")
    _style_time_labels(ax)
    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}time_vs_size_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)


def _style_time_labels(ax) -> None:
    ax.set_xlabel("Number of SKUs (log scale)")
    ax.set_ylabel("Wall-Clock Time (s)")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))


# ── Chart 2: Speedup vs. Data Size ─────────────────────────────────────────

def _chart_speedup_vs_size(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 2: Speedup vs. Data Size — line chart with ±1σ error bars."""
    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)

    for tech_key in _ordered_tech_keys(chart_data):
        if tech_key == "sequential":
            continue  # baseline — skip redundant flat line
        ds_dict = chart_data[tech_key]
        sizes = []
        speedups = []
        stdevs = []
        for ds_label in _sort_labels_by_size(ds_dict):
            agg = ds_dict[ds_label]
            s = agg.get("size", 0)
            if s > 0:
                sizes.append(s)
                speedups.append(agg.get("speedup", 0))
                stdevs.append(agg.get("speedup_stdev", 0))
        if sizes:
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            ax.errorbar(sizes, speedups, yerr=stdevs if any(stdevs) else None,
                        fmt="o-", label=label, color=color,
                        markersize=CHART_MARKER_SIZE, linewidth=CHART_LINE_WIDTH,
                        capsize=4)

    ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=1, alpha=0.7,
               label="Baseline (Speedup = 1)")
    ax.set_xscale("log")
    ax.set_title("Speedup vs. Dataset Size")
    _style_time_labels(ax)
    ax.set_ylabel("Speedup (× Sequential)")

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}speedup_vs_size_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)


# ── Chart 3: CPU Utilization ───────────────────────────────────────────────

def _chart_cpu_util(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 3: CPU Utilization — grouped bar chart across all dataset sizes."""
    annotate_fs = _font_size(CHART_FONT_SIZE_ANNOTATE, CHART_FONT_SIZE_ANNOTATE_PRESENTATION, presentation)

    all_labels: list[str] = []
    for ds_dict in chart_data.values():
        for lbl in _sort_labels_by_size(ds_dict):
            if lbl not in all_labels:
                all_labels.append(lbl)

    ordered_techs = _ordered_tech_keys(chart_data)
    width = CHART_BAR_WIDTH
    n_techs = max(len(ordered_techs), 1)
    offsets = np.linspace(-width * (n_techs - 1) / 2, width * (n_techs - 1) / 2, n_techs)
    x = np.arange(len(all_labels))

    fig, ax = plt.subplots(figsize=CHART_FIGSIZE_WIDE)
    for tech_key, offset in zip(ordered_techs, offsets):
        ds_dict = chart_data[tech_key]
        cpu_vals = [ds_dict.get(lbl, {}).get("cpu_overall_percent", 0) for lbl in all_labels]
        if any(v > 0 for v in cpu_vals):
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            bars = ax.bar(x + offset, cpu_vals, width * 0.8, label=label, color=color)
            for bar, val in zip(bars, cpu_vals):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + CHART_AXIS_PAD,
                            f"{val:.1f}%", ha="center", va="bottom",
                            fontsize=annotate_fs)

    ax.set_xticks(x)
    ax.set_xticklabels(all_labels, rotation=CHART_ROTATION, ha="right",
                       fontsize=_font_size(CHART_FONT_SIZE_TICKS, CHART_FONT_SIZE_TICKS_PRESENTATION, presentation))
    ax.set_ylabel("Avg CPU Utilization (%)")
    ax.set_title("CPU Utilization — All Dataset Sizes")
    all_vals = [v for tech_key in chart_data for v in [chart_data[tech_key].get(lbl, {}).get("cpu_overall_percent", 0) for lbl in all_labels]]
    max_val = max(all_vals) if all_vals else CHART_CPU_YLIM_FLOOR
    ax.set_ylim(0, max(max_val * CHART_CPU_YLIM_PAD, CHART_CPU_YLIM_FLOOR))

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}cpu_util_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)


# ── Chart 4: Overhead Breakdown ────────────────────────────────────────────

def _chart_overhead_breakdown(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 4: Overhead vs. Compute Time Breakdown — stacked bar chart."""
    tick_fs = _font_size(CHART_FONT_SIZE_TICKS, CHART_FONT_SIZE_TICKS_PRESENTATION, presentation)
    legend_fs = _font_size(CHART_FONT_SIZE_LEGEND_SMALL, CHART_FONT_SIZE_LEGEND_PRESENTATION, presentation)
    dpi = CHART_DPI_PRESENTATION if presentation else CHART_DPI

    all_labels: list[str] = []
    seen = set()
    for ds_dict in chart_data.values():
        for lbl in _sort_labels_by_size(ds_dict):
            if lbl not in seen:
                all_labels.append(lbl)
                seen.add(lbl)

    fig, ax = plt.subplots(figsize=CHART_FIGSIZE_WIDE)
    x = np.arange(len(all_labels))
    width = CHART_BAR_WIDTH
    ordered_techs = _ordered_tech_keys(chart_data)
    n_techs = max(len(ordered_techs), 1)
    offsets = np.linspace(-width * (n_techs - 1) / 2, width * (n_techs - 1) / 2, n_techs)

    for tech_key, offset in zip(ordered_techs, offsets):
        ds_dict = chart_data[tech_key]
        overheads = []
        computes = []
        present_labels = []
        for lbl in all_labels:
            if lbl in ds_dict:
                agg = ds_dict[lbl]
                overheads.append(agg.get("overhead_time", 0))
                computes.append(agg.get("compute_time", 0))
                present_labels.append(lbl)

        if present_labels:
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            pos = [xi + offset for xi in range(len(present_labels))]
            ax.bar(pos, computes, width * 0.8, label=f"{label} (Compute)", color=color)
            ax.bar(pos, overheads, width * 0.8, bottom=computes,
                   label=f"{label} (Overhead)", color=color,
                   alpha=CHART_ALPHA_OVERLAY, hatch=CHART_HATCH)

    ax.set_xticks(range(len(all_labels)))
    ax.set_xticklabels(all_labels, rotation=CHART_ROTATION, ha="right", fontsize=tick_fs)
    ax.set_ylabel("Time (s)")
    ax.set_title("Overhead vs. Compute Time Breakdown")
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=legend_fs, loc="upper left")
    ax.grid(True, alpha=CHART_GRID_ALPHA)
    if results:
        sub = _metadata_subtitle(results, presentation)
        fig.text(0.5, 0.01, sub, ha="center", va="bottom",
                 fontsize=tick_fs, style="italic", color="gray")
        fig.subplots_adjust(bottom=0.12)

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}overhead_breakdown_{timestamp}{CHART_FILENAME_SUFFIX}")
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return filepath


# ── Chart 5: Peak Memory ───────────────────────────────────────────────────

def _chart_memory(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 5: Peak Memory Usage — bar chart at the largest dataset."""
    annotate_fs = _font_size(CHART_FONT_SIZE_ANNOTATE, CHART_FONT_SIZE_ANNOTATE_PRESENTATION, presentation)
    max_label = _find_largest_dataset(chart_data)

    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
    techniques = []
    mem_vals = []
    colors = []
    for tech_key in _ordered_tech_keys(chart_data):
        if max_label in chart_data[tech_key]:
            techniques.append(TECHNIQUE_LABELS.get(tech_key, tech_key))
            mem_vals.append(chart_data[tech_key][max_label].get("peak_memory_mb", 0))
            colors.append(TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR))

    if techniques:
        bars = ax.bar(techniques, mem_vals, color=colors)
        for bar, val in zip(bars, mem_vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + CHART_AXIS_PAD,
                    f"{val:.0f} MB", ha="center", va="bottom",
                    fontsize=annotate_fs)

    ax.set_ylabel("Peak Memory (MB)")
    ax.set_title(f"Peak Memory Usage ({max_label})")

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}memory_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)


# ── Chart 6: Efficiency vs. Data Size ──────────────────────────────────────

def _chart_efficiency_vs_size(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 6: Efficiency vs. Data Size — line chart with 100% reference."""
    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)

    for tech_key in _ordered_tech_keys(chart_data):
        if tech_key == "sequential":
            continue
        ds_dict = chart_data[tech_key]
        sizes = []
        effs = []
        for ds_label in _sort_labels_by_size(ds_dict):
            agg = ds_dict[ds_label]
            s = agg.get("size", 0)
            if s > 0:
                sizes.append(s)
                effs.append(agg.get("efficiency", 0) * 100)
        if sizes:
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            ax.plot(sizes, effs, "o-", label=label, color=color,
                    markersize=CHART_MARKER_SIZE, linewidth=CHART_LINE_WIDTH)

    ax.axhline(y=100.0, color="gray", linestyle="--", linewidth=1, alpha=0.7,
               label="Ideal (100% Efficiency)")
    ax.set_xscale("log")
    ax.set_xlabel("Number of SKUs (log scale)")
    ax.set_ylabel("Efficiency (%)")
    ax.set_title("Parallel Efficiency vs. Dataset Size")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_ylim(bottom=0)

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}efficiency_vs_size_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)


# ── Chart 7: Throughput vs. Data Size ───────────────────────────────────────

def _chart_throughput_vs_size(
    chart_data: dict, output_dir: str, timestamp: str,
    *,
    results: Optional[dict] = None,
    presentation: bool = False,
) -> str:
    """Chart 7: Throughput vs. Data Size — line chart, log-scale x-axis."""
    fig, ax = plt.subplots(figsize=CHART_FIGSIZE)

    for tech_key in _ordered_tech_keys(chart_data):
        ds_dict = chart_data[tech_key]
        sizes = []
        tputs = []
        for ds_label in _sort_labels_by_size(ds_dict):
            agg = ds_dict[ds_label]
            s = agg.get("size", 0)
            if s > 0:
                sizes.append(s)
                tputs.append(agg.get("throughput", 0))
        if sizes:
            label = TECHNIQUE_LABELS.get(tech_key, tech_key)
            color = TECHNIQUE_COLORS.get(tech_key, TECHNIQUE_DEFAULT_COLOR)
            ax.plot(sizes, tputs, "o-", label=label, color=color,
                    markersize=CHART_MARKER_SIZE, linewidth=CHART_LINE_WIDTH)

    ax.set_xscale("log")
    ax.set_xlabel("Number of SKUs (log scale)")
    ax.set_ylabel("Throughput (records / second)")
    ax.set_title("Throughput vs. Dataset Size")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

    filepath = os.path.join(output_dir, f"{CHART_FILENAME_PREFIX}throughput_vs_size_{timestamp}{CHART_FILENAME_SUFFIX}")
    return _style_and_save(fig, ax, filepath, results=results, presentation=presentation)
