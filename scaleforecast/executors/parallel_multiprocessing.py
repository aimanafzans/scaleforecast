"""
Parallel (multiprocessing) executor for ScaleForecast.

Uses multiprocessing.Pool to distribute forecast_engine.forecast_skus() work
across OS-level processes, bypassing the GIL entirely. Each worker process
receives a chunk of SKU records, computes the forecast independently, and
returns results via inter-process communication (pickling).

The key tradeoff: process spawn + data pickling overhead is substantial at
small data sizes, but becomes negligible relative to compute time at large
volumes (Amdahl's Law).
"""

import math
import multiprocessing
import time
from typing import Any

import pandas as pd

from scaleforecast.forecast_engine import forecast_skus


def _worker(chunk: list[dict]) -> list[dict]:
    """Pool worker: forecast a single chunk of SKU records."""
    return forecast_skus(chunk)


def run(
    filepath: str,
    num_workers: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Execute demand forecasting using multiprocessing.Pool.

    Loads the dataset, splits records into num_workers chunks, distributes
    chunks to a process pool, and combines results.

    Args:
        filepath: Path to the dataset CSV.
        num_workers: Number of worker processes in the pool.

    Returns:
        (results, timing) where:
          - results: combined forecast result dicts from all workers
          - timing: dict with keys 'compute_time', 'overhead_time', 'total_time'
            where overhead_time captures pool creation + data serialisation.
    """
    t0 = time.perf_counter()

    df = pd.read_csv(filepath)
    records = df.to_dict("records")

    t_load = time.perf_counter()

    chunk_size = math.ceil(len(records) / num_workers)
    chunks = [records[i:i + chunk_size] for i in range(0, len(records), chunk_size)]
    chunks = [c for c in chunks if c]

    t_pool_start = time.perf_counter()

    with multiprocessing.Pool(processes=num_workers) as pool:
        chunk_results = pool.map(_worker, chunks)

    t_end = time.perf_counter()

    combined = []
    for cr in chunk_results:
        combined.extend(cr)

    timing = {
        "compute_time": t_end - t_pool_start,
        "overhead_time": (t_load - t0) + (t_pool_start - t_load),
        "total_time": t_end - t0,
    }

    return combined, timing
