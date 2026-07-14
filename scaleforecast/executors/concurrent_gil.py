"""
Concurrent (GIL-bound threading) executor for ScaleForecast.

Uses the standard threading module to execute forecast_engine.forecast_skus()
across multiple threads. Under a standard (GIL-enabled) CPython build, these
threads are serialised by the GIL for CPU-bound work — this executor is the
demonstration of why threading does NOT accelerate CPU-bound Python code.
"""

import math
import threading
import time
from typing import Any

import pandas as pd

from scaleforecast.forecast_engine import forecast_skus


def _process_chunk(records: list[dict], results_out: list, index: int):
    """Worker target: forecast a chunk of records and store at results_out[index]."""
    results_out[index] = forecast_skus(records)


def run(
    filepath: str,
    num_workers: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Execute demand forecasting using GIL-bound threading.

    Splits the dataset into num_workers chunks, spawns one thread per chunk,
    and joins all threads. Under the GIL, threads take turns holding the
    interpreter lock, so CPU-bound work does not truly parallelise.

    Args:
        filepath: Path to the dataset CSV.
        num_workers: Number of threads to spawn.

    Returns:
        (results, timing) where:
          - results: combined forecast result dicts from all chunks
          - timing: dict with keys 'compute_time', 'overhead_time', 'total_time'
    """
    t0 = time.perf_counter()

    df = pd.read_csv(filepath)
    records = df.to_dict("records")

    t_load = time.perf_counter()

    chunk_size = math.ceil(len(records) / num_workers)
    chunks = [records[i:i + chunk_size] for i in range(0, len(records), chunk_size)]
    # Trim empty trailing chunks
    chunks = [c for c in chunks if c]

    results_out = [None] * len(chunks)
    threads = []

    t_thread_start = time.perf_counter()

    for i, chunk in enumerate(chunks):
        t = threading.Thread(target=_process_chunk, args=(chunk, results_out, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    t_end = time.perf_counter()

    combined = []
    for r in results_out:
        if r is not None:
            combined.extend(r)

    timing = {
        "compute_time": t_end - t_thread_start,
        "overhead_time": (t_load - t0) + (t_thread_start - t_load),
        "total_time": t_end - t0,
    }

    return combined, timing
