"""
Benchmark orchestrator for ScaleForecast.

Runs the same forecasting workload across multiple execution techniques,
data sizes, and repeated trials. Collects the full 7-metric suite per run
and computes mean ± standard deviation for time-based metrics.

Per PRD Section 7.1:
  - Each (technique × size) combination runs N times (default 3, recommended 5).
  - Worker count is fixed and documented.
  - Interpreter build is auto-detected and recorded in output metadata.
  - Warm-up runs may be discarded (configurable).
"""

import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable, Optional

from scaleforecast.executors.sequential import run as run_seq
from scaleforecast.executors.concurrent_gil import run as run_gil
from scaleforecast.executors.concurrent_nogil import run as run_nogil
from scaleforecast.executors.parallel_multiprocessing import run as run_mp
from scaleforecast.interpreter_detection import (
    FREE_THREADED_ON_PATH,
    IS_FREE_THREADED,
    get_available_techniques,
    get_interpreter_info,
)
from scaleforecast.metrics_collector import collect
from scaleforecast import config
from scaleforecast.constants import (
    TECHNIQUE_LABELS,
    DEFAULT_REPEATS as _CONST_DEFAULT_REPEATS,
    DEFAULT_MAX_WORKERS,
    WARMUP_RUNS as _CONST_WARMUP_RUNS,
)

TECHNIQUE_REGISTRY: dict[str, dict[str, Any]] = {
    "sequential": {
        "label": TECHNIQUE_LABELS["sequential"],
        "fn": run_seq,
        "available": True,
    },
    "concurrent_gil": {
        "label": TECHNIQUE_LABELS["concurrent_gil"],
        "fn": run_gil,
        "available": True,
    },
    "concurrent_nogil": {
        "label": TECHNIQUE_LABELS["concurrent_nogil"],
        "fn": run_nogil,
        "available": IS_FREE_THREADED or FREE_THREADED_ON_PATH,
    },
    "parallel_multiprocessing": {
        "label": TECHNIQUE_LABELS["parallel_multiprocessing"],
        "fn": run_mp,
        "available": True,
    },
}

_CPU_COUNT = os.cpu_count() or 1
# Re-exported for callers that still do `from scaleforecast.benchmark import DEFAULT_*`.
DEFAULT_WORKERS = min(_CPU_COUNT, DEFAULT_MAX_WORKERS)
DEFAULT_REPEATS = _CONST_DEFAULT_REPEATS
WARMUP_RUNS = _CONST_WARMUP_RUNS


def available_techniques() -> list[str]:
    """Return keys of techniques available in the current interpreter session."""
    return [k for k, v in TECHNIQUE_REGISTRY.items() if v["available"]]


def _find_interpreter(name: str) -> Optional[str]:
    """Find a Python interpreter binary. Searches PATH first, then known install locations."""
    path = shutil.which(name)
    if path is not None:
        return path
    if sys.platform == "win32" and not name.endswith(".exe"):
        path = shutil.which(name + ".exe")
        if path is not None:
            return path

    # Search known install directories on Windows (most recent first)
    known_dirs = []
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        python_base = os.path.join(local_appdata, "Programs", "Python")
        if os.path.isdir(python_base):
            # Sort subdirectories descending so Python314 is searched before Python313
            try:
                entries = sorted(os.listdir(python_base), reverse=True)
            except OSError:
                entries = []
            for entry in entries:
                full = os.path.join(python_base, entry)
                if os.path.isdir(full):
                    known_dirs.append(full)
    known_dirs.extend([
        "C:\\Python313",
        "C:\\Python314",
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Python313"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Python314"),
    ])

    exe_name = name if name.endswith(".exe") or sys.platform != "win32" else name + ".exe"
    for base in known_dirs:
        if os.path.isdir(base):
            candidate = os.path.join(base, exe_name)
            if os.path.isfile(candidate):
                return candidate

    return None


def _resolve_subprocess_cmd(tech_key: str) -> Optional[list[str]]:
    """
    Build the subprocess command for a concurrent technique.

    Returns a list like ['python', '-X', 'gil=1', '-m', 'scaleforecast._runner', ...]
    or None if no suitable interpreter is available.
    """
    standard = (
        _find_interpreter("python") or _find_interpreter("python3")
        or _find_interpreter("python3.14")
    )
    freethreaded = _find_interpreter("python3.13t")

    # Sequential, Concurrent (With GIL), and Multiprocessing all need
    # GIL enabled → use standard interpreter, or free-threaded with -X gil=1.
    if tech_key in ("sequential", "concurrent_gil", "parallel_multiprocessing"):
        if standard:
            return [standard, "-m", "scaleforecast._runner"]
        if freethreaded:
            return [freethreaded, "-X", "gil=1", "-m", "scaleforecast._runner"]
        return None

    if tech_key == "concurrent_nogil":
        if freethreaded:
            return [freethreaded, "-m", "scaleforecast._runner"]
        return None

    return None


def _compute_mean_stdev(values: list[float]) -> tuple[float, float]:
    """Return (mean, stdev) for a list of values. Returns (0, 0) for empty or single-value lists."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n == 1:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


def _extract_dataset_size_int(filepath: str) -> int:
    """
    Parse the raw integer SKU count from a dataset filename.

    Filenames follow the convention ``sku_dataset_<N>_<YYYYMMDD>_<HHMM>.csv``
    (see :mod:`scaleforecast.data_generator`).  Returns 0 if the filename
    does not match the convention or the size portion is not an integer.

    This is used so :mod:`scaleforecast.chart_generator` can read the raw
    integer from the aggregation dict (via the ``dataset_size`` field)
    rather than round-tripping a *display label* (e.g. ``"500K SKUs"``)
    back into a number -- a fragile string-replace pipeline that was the
    source of a real chart bug.
    """
    import re
    basename = os.path.basename(filepath)
    m = re.match(r"sku_dataset_(\d+)_\d+_\d+\.csv$", basename)
    if m:
        return int(m.group(1))
    # Fallback: try to parse any leading integer after the prefix.
    m = re.match(r"sku_dataset_(\d+)", basename)
    if m:
        return int(m.group(1))
    return 0


def _aggregate_runs(run_metrics: list[dict], dataset_size: int = 0) -> dict[str, Any]:
    """
    Aggregate a list of per-run metric dicts into a summary with
    mean ± stdev for numeric fields.

    ``dataset_size`` is the raw integer SKU count of the underlying dataset.
    It is stored in the aggregation dict so chart generation can sort / scale
    by raw data size without re-parsing a display label back into a number.
    """
    if not run_metrics:
        return {}

    numeric_keys = [
        "wall_time", "compute_time", "overhead_time",
        "speedup", "efficiency", "throughput",
        "cpu_overall_percent", "peak_memory_mb", "avg_memory_mb",
        "child_process_memory_mb",
    ]

    agg = {
        "num_runs": len(run_metrics),
        "num_records": run_metrics[0].get("num_records", 0),
        "num_workers": run_metrics[0].get("num_workers", 0),
        "technique": run_metrics[0].get("technique", ""),
        "interpreter_label": run_metrics[0].get("interpreter_label", ""),
        "gil_warning": run_metrics[0].get("gil_warning", ""),
        # Raw integer dataset size (0 if unparsable) -- avoids lossy
        # display-label -> int round-trips downstream (chart generator).
        "dataset_size": dataset_size,
    }

    for key in numeric_keys:
        values = [m.get(key, 0.0) for m in run_metrics]
        mean, stdev = _compute_mean_stdev(values)
        agg[key] = mean
        agg[f"{key}_stdev"] = stdev

    return agg


def _get_dataset_label(filepath: str) -> str:
    """Extract a short label from a dataset filepath for display."""
    basename = os.path.basename(filepath)
    parts = basename.replace(".csv", "").split("_")
    if len(parts) >= 3 and parts[0] == "sku" and parts[1] == "dataset":
        size = parts[2]
        try:
            n = int(size)
            if n >= 1_000_000:
                return f"{n // 1_000_000}M SKUs"
            elif n >= 1_000:
                return f"{n // 1_000}K SKUs"
        except ValueError:
            pass
        return f"{size} SKUs"
    return basename


def run_benchmark(
    dataset_paths: list[str],
    technique_keys: list[str],
    num_repeats: int = DEFAULT_REPEATS,
    num_workers: int = DEFAULT_WORKERS,
    progress_callback: Optional[Callable] = None,
    technique_callback: Optional[Callable] = None,
) -> dict[str, Any]:
    """
    Run the full benchmark suite across specified datasets and techniques.

    Args:
        dataset_paths: List of paths to dataset CSV files.
        technique_keys: List of technique keys (e.g. ['sequential', 'concurrent_gil']).
            Only available techniques will be run; unavailable ones are tracked.
        num_repeats: Number of repeated runs per (technique × dataset) combination.
        num_workers: Number of threads/processes for parallel techniques.
        progress_callback: Optional callable(phase, current, total) for progress.
        technique_callback: Optional callable(tech_key, ds_path, agg_dict) fired
            immediately after a technique finishes all its repeats for a dataset,
            enabling a ``rich.live.Live`` incremental results table.

    Returns:
        Dict with keys:
          - metadata: interpreter info, machine specs, timestamp
          - per_dataset: dict of dataset_path → { technique_key → aggregated_metrics }
          - raw_runs: list of all individual run metric dicts
          - unavailable_techniques: list of technique keys requested but unavailable
    """
    if not dataset_paths:
        raise ValueError("At least one dataset path is required.")
    if num_repeats < 1:
        raise ValueError("num_repeats must be >= 1.")

    all_available = available_techniques()
    unavailable = [k for k in technique_keys if k not in all_available]
    technique_keys = [k for k in technique_keys if k in all_available]

    if not technique_keys:
        raise ValueError("No available techniques selected for benchmarking.")

    metadata = {
        **get_interpreter_info(),
        "num_workers": num_workers,
        "num_repeats": num_repeats,
        "warmup_runs_discarded": WARMUP_RUNS,
        "timestamp": datetime.now().isoformat(),
        "machine": sys.platform,
    }

    raw_runs: list[dict] = []
    all_aggregated: dict[str, dict] = {}
    gil_warnings: dict[str, list[str]] = {}

    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    total_combos = len(dataset_paths) * len(technique_keys)
    combo_idx = 0

    for ds_path in dataset_paths:
        dataset_label = _get_dataset_label(ds_path)
        dataset_size = _extract_dataset_size_int(ds_path)
        ds_aggregated: dict[str, dict] = {}

        # Run Sequential first to establish baseline_time for speedup calc.
        # All techniques now run via subprocess for consistent interpreter pinning.
        baseline_time: Optional[float] = None
        if "sequential" in technique_keys:
            seq_runs = []
            for rep in range(num_repeats):
                combo_idx += 1
                if progress_callback:
                    progress_callback("run", combo_idx, total_combos * num_repeats)
                m = _run_subprocess_technique(
                    "sequential", ds_path, dataset_label, rep,
                    1, None, _project_root,
                )
                raw_runs.append(m)
                seq_runs.append(m)
            baseline_time = sum(r["wall_time"] for r in seq_runs) / len(seq_runs) if seq_runs else None
            ds_aggregated["sequential"] = _aggregate_runs(seq_runs, dataset_size)
            if technique_callback:
                technique_callback("sequential", ds_path, ds_aggregated["sequential"])

        for tech_key in technique_keys:
            if tech_key == "sequential":
                continue
            workers = num_workers if tech_key != "sequential" else 1
            tech_runs = []
            for rep in range(num_repeats):
                combo_idx += 1
                if progress_callback:
                    progress_callback("run", combo_idx, total_combos * num_repeats)
                m = _run_subprocess_technique(
                    tech_key, ds_path, dataset_label, rep,
                    workers, baseline_time, _project_root,
                )
                raw_runs.append(m)
                tech_runs.append(m)
            ds_aggregated[tech_key] = _aggregate_runs(tech_runs, dataset_size)
            if technique_callback:
                technique_callback(tech_key, ds_path, ds_aggregated[tech_key])

        all_aggregated[ds_path] = ds_aggregated

    return {
        "metadata": metadata,
        "per_dataset": all_aggregated,
        "raw_runs": raw_runs,
        "unavailable_techniques": unavailable,
        "gil_warnings": gil_warnings,
    }


def _run_subprocess_technique(
    tech_key: str,
    ds_path: str,
    dataset_label: str,
    run_index: int,
    num_workers: int,
    baseline_time: Optional[float],
    project_root: str,
) -> dict[str, Any]:
    """
    Execute a concurrent technique via subprocess isolation so the GIL state
    is controlled independently of the parent interpreter.

    Returns a metrics dict in the same format as metrics_collector.collect().
    """
    cmd = _resolve_subprocess_cmd(tech_key)
    if cmd is None:
        raise RuntimeError(f"No interpreter available for technique '{tech_key}'")

    cmd.extend(["--technique", tech_key, "--dataset-path", ds_path, "--workers", str(num_workers)])

    env = os.environ.copy()
    env["SCALEFORECAST_ROOT"] = project_root
    env["PYTHONPATH"] = project_root

    t_start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
    t_end = time.perf_counter()

    if proc.returncode != 0:
        raise RuntimeError(
            f"Runner subprocess failed for '{tech_key}' (exit {proc.returncode}):\n"
            f"STDERR: {proc.stderr[:500]}"
        )

    try:
        runner_output = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Runner subprocess produced invalid JSON for '{tech_key}':\n"
            f"STDOUT: {proc.stdout[:500]}"
        )

    wall_time = t_end - t_start
    compute_time = runner_output.get("compute_time", wall_time)
    records = runner_output.get("records_processed", 0)
    gil_enabled_in_subprocess = runner_output.get("gil_enabled", None)

    speedup = 1.0
    efficiency = 1.0
    if baseline_time and baseline_time > 0 and wall_time > 0:
        speedup = baseline_time / wall_time
        efficiency = speedup / max(num_workers, 1)

    gil_warning = ""
    # Sequential, Concurrent (With GIL), and Multiprocessing should all
    # report GIL enabled.  Only Concurrent (No GIL) should report disabled.
    expects_gil = tech_key != "concurrent_nogil"
    if expects_gil:
        if gil_enabled_in_subprocess is False:
            gil_warning = (
                f"WARNING: GIL state mismatch for '{tech_key}' — expected "
                "GIL enabled in subprocess but runner reports disabled."
            )
        elif gil_enabled_in_subprocess is None:
            gil_warning = "WARNING: Could not determine GIL state from subprocess runner."
    else:
        if gil_enabled_in_subprocess is True:
            gil_warning = (
                "WARNING: GIL state mismatch for 'concurrent_nogil' — expected "
                "GIL disabled in subprocess but runner reports enabled. "
                "Results reflect GIL-bound threading."
            )

    return {
        "technique": tech_key,
        "dataset": dataset_label,
        "dataset_path": ds_path,
        "run_index": run_index,
        "num_records": records,
        "num_workers": num_workers,
        "wall_time": wall_time,
        "compute_time": compute_time,
        "overhead_time": wall_time - compute_time,
        "speedup": speedup,
        "efficiency": efficiency,
        "throughput": records / wall_time if wall_time > 0 else 0.0,
        "cpu_overall_percent": runner_output.get("cpu_usage_percent", 0.0),
        "cpu_per_core": [],
        "peak_memory_mb": runner_output.get("peak_memory_mb", 0.0),
        "avg_memory_mb": runner_output.get("peak_memory_mb", 0.0),
        "child_process_memory_mb": 0.0,
        "interpreter_label": (
            "GIL-enabled" if gil_enabled_in_subprocess else "Free-threaded"
        ),
        "executor_timing": {
            "compute_time": compute_time,
            "overhead_time": wall_time - compute_time,
            "total_time": wall_time,
        },
        "gil_warning": gil_warning,
        "runner_gil_enabled": gil_enabled_in_subprocess,
        "runner_python_version": runner_output.get("python_version", ""),
    }


def save_benchmark_results(
    results: dict[str, Any],
    output_dir: Optional[str] = None,
) -> tuple[str, str]:
    """
    Save benchmark results to disk as JSON (raw runs) and CSV (aggregated table).

    Args:
        results: The dict returned by run_benchmark().
        output_dir: Directory for output files. Defaults to scaleforecast/benchmarks/.

    Returns:
        (json_path, csv_path) of saved files.
    """
    if output_dir is None:
        output_dir = str(config.BENCHMARKS_DIR)
    config.ensure_dir(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"benchmark_raw_{timestamp}.json")
    csv_path = os.path.join(output_dir, f"benchmark_summary_{timestamp}.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    csv_rows = []
    for ds_path, tech_dict in results["per_dataset"].items():
        dataset_label = _get_dataset_label(ds_path)
        for tech_key, agg in tech_dict.items():
            label = TECHNIQUE_REGISTRY.get(tech_key, {}).get("label", tech_key)
            csv_rows.append({
                "Dataset": dataset_label,
                "Technique": label,
                "Average Time (s)": round(agg.get("wall_time", 0), 4),
                "Typical Variation (±s)": round(agg.get("wall_time_stdev", 0), 4),
                "Speedup": round(agg.get("speedup", 0), 4),
                "Efficiency (%)": round(agg.get("efficiency", 0) * 100, 1),
                "Throughput (rec/s)": round(agg.get("throughput", 0), 1),
                "Avg CPU Usage (%)": round(agg.get("cpu_overall_percent", 0), 1),
                "Setup Overhead (s)": round(agg.get("overhead_time", 0), 4),
                "Peak Memory (MB)": round(agg.get("peak_memory_mb", 0), 1),
                "Num Workers": agg.get("num_workers", 0),
                "Num Records": agg.get("num_records", 0),
                "Interpreter": agg.get("interpreter_label", ""),
                "GIL Warning": agg.get("gil_warning", ""),
            })
    if csv_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)

    return json_path, csv_path
