"""
Standalone subprocess runner for ScaleForecast benchmark techniques.

Launched as a subprocess by benchmark.py to run a specific technique
(sequential, concurrent_gil, concurrent_nogil, or multiprocessing)
under a pinned interpreter with a controlled GIL state.  Accepts CLI
arguments, loads the dataset, executes the technique, measures CPU
usage, and outputs a JSON result dict to stdout.

Usage:
    python -m scaleforecast._runner --technique sequential --dataset-path <csv> --workers <N>
"""

import argparse
import json
import math
import multiprocessing
import os
import sys
import threading
import time

import numpy as np
import pandas as pd
import psutil

_project_root = os.environ.get("SCALEFORECAST_ROOT")
if _project_root and _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scaleforecast.forecast_engine import forecast_skus


# ── Worker functions for each technique ────────────────────────────────────

def _chunk_records(records: list, num_workers: int) -> list[list]:
    chunk_size = math.ceil(len(records) / num_workers)
    chunks = [records[i:i + chunk_size] for i in range(0, len(records), chunk_size)]
    return [c for c in chunks if c]


def _threaded_worker(chunk, results_out, index):
    results_out[index] = forecast_skus(chunk)


def _pool_worker(chunk):
    return forecast_skus(chunk)


# ── CPU measurement helpers ────────────────────────────────────────────────

def _process_tree_cpu_seconds() -> float:
    """Cumulative CPU seconds (user + system) for this process and all descendants."""
    proc = psutil.Process(os.getpid())
    try:
        ct = proc.cpu_times()
        total = ct.user + ct.system
    except psutil.NoSuchProcess:
        total = 0.0
    for child in proc.children(recursive=True):
        try:
            ct = child.cpu_times()
            total += ct.user + ct.system
        except psutil.NoSuchProcess:
            pass
    return total


def _cpu_percent_normalized(cpu_before: float, cpu_after: float, elapsed: float) -> float:
    """
    Compute normalised CPU usage from absolute CPU-second deltas.

    cpu_percent = (cpu_seconds / elapsed) * 100  gives the % of ONE core.
    Dividing by os.cpu_count() normalises to 0-100% of total system capacity
    so all techniques report on the same scale.
    """
    if elapsed <= 0:
        return 0.0
    raw_pct = ((cpu_after - cpu_before) / elapsed) * 100.0
    cores = os.cpu_count() or 1
    return raw_pct / cores


# ── Technique runners ─────────────────────────────────────────────────────

def _run_sequential(records: list, num_workers: int = 1) -> dict:
    cpu_before = _process_tree_cpu_seconds()
    t0 = time.perf_counter()
    results = forecast_skus(records)
    t1 = time.perf_counter()
    cpu_after = _process_tree_cpu_seconds()
    return {
        "records_processed": len(results),
        "compute_time": t1 - t0,
        "wall_time": t1 - t0,
        "cpu_usage_percent": _cpu_percent_normalized(cpu_before, cpu_after, t1 - t0),
    }


def _run_concurrent(records: list, num_workers: int) -> dict:
    chunks = _chunk_records(records, num_workers)
    results_out = [None] * len(chunks)
    threads = []

    for i, chunk in enumerate(chunks):
        t = threading.Thread(target=_threaded_worker, args=(chunk, results_out, i))
        threads.append(t)
        t.start()

    cpu_before = _process_tree_cpu_seconds()
    t0 = time.perf_counter()

    for t in threads:
        t.join()

    t1 = time.perf_counter()
    cpu_after = _process_tree_cpu_seconds()

    combined = []
    for r in results_out:
        if r is not None:
            combined.extend(r)

    return {
        "records_processed": len(combined),
        "compute_time": t1 - t0,
        "wall_time": t1 - t0,
        "cpu_usage_percent": _cpu_percent_normalized(cpu_before, cpu_after, t1 - t0),
    }


def _run_multiprocessing(records: list, num_workers: int) -> dict:
    chunks = _chunk_records(records, num_workers)

    with multiprocessing.Pool(processes=num_workers) as pool:
        worker_pids = [p.pid for p in pool._pool if p.pid is not None]

        pre_times: dict[int, float | None] = {}
        pre_memory: dict[int, int | None] = {}
        for pid in worker_pids:
            try:
                proc = psutil.Process(pid)
                ct = proc.cpu_times()
                pre_times[pid] = ct.user + ct.system
                pre_memory[pid] = proc.memory_info().rss
            except psutil.NoSuchProcess:
                pre_times[pid] = None
                pre_memory[pid] = None

        t0 = time.perf_counter()
        chunk_results = pool.map(_pool_worker, chunks)
        t1 = time.perf_counter()

        coordinator_rss = psutil.Process(os.getpid()).memory_info().rss
        total_cpu_seconds = 0.0
        total_worker_memory_bytes = 0
        failed_count = 0
        for pid in worker_pids:
            try:
                proc = psutil.Process(pid)
                ct = proc.cpu_times()
                post = ct.user + ct.system
                pre = pre_times.get(pid)
                if pre is not None:
                    delta = post - pre
                    if delta > 0:
                        total_cpu_seconds += delta

                post_rss = proc.memory_info().rss
                pre_rss = pre_memory.get(pid)
                if pre_rss is not None:
                    total_worker_memory_bytes += max(post_rss, pre_rss)
                else:
                    total_worker_memory_bytes += post_rss
            except psutil.NoSuchProcess:
                failed_count += 1

        if failed_count > 0:
            print(
                f"[_runner] WARNING: Could not measure metrics for "
                f"{failed_count}/{len(worker_pids)} multiprocessing workers "
                f"(processes already exited). Consider using a larger dataset.",
                file=sys.stderr,
            )

        peak_memory_bytes = coordinator_rss + total_worker_memory_bytes
        peak_memory_mb = peak_memory_bytes / (1024 * 1024)

    elapsed = t1 - t0
    cpu_cores = os.cpu_count() or 1
    cpu_usage_normalized = 0.0
    if elapsed > 0:
        raw_pct = (total_cpu_seconds / elapsed) * 100.0
        cpu_usage_normalized = raw_pct / cpu_cores

    combined = []
    for cr in chunk_results:
        combined.extend(cr)

    return {
        "records_processed": len(combined),
        "compute_time": t1 - t0,
        "wall_time": t1 - t0,
        "cpu_usage_percent": cpu_usage_normalized,
        "peak_memory_mb": peak_memory_mb,
    }


# ── Main ───────────────────────────────────────────────────────────────────

TECHNIQUE_RUNNERS = {
    "sequential": _run_sequential,
    "concurrent_gil": _run_concurrent,
    "concurrent_nogil": _run_concurrent,
    "parallel_multiprocessing": _run_multiprocessing,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--technique", required=True,
                        choices=["sequential", "concurrent_gil", "concurrent_nogil", "parallel_multiprocessing"])
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    gil_enabled = True
    if hasattr(sys, "_is_gil_enabled"):
        gil_enabled = sys._is_gil_enabled()

    t_load_start = time.perf_counter()
    df = pd.read_csv(args.dataset_path)
    records = df.to_dict("records")
    t_load_end = time.perf_counter()

    runner = TECHNIQUE_RUNNERS[args.technique]
    result = runner(records, args.workers)

    result["gil_enabled"] = gil_enabled
    result["python_version"] = sys.version.split("\n")[0].strip()
    result["load_time"] = t_load_end - t_load_start
    if "peak_memory_mb" not in result:
        result["peak_memory_mb"] = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

    json.dump(result, sys.stdout)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
