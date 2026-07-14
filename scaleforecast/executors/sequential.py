"""
Sequential (single-threaded) executor for ScaleForecast.

Loads a SKU dataset and runs the shared forecast_engine.forecast_skus()
function on all records in a single-threaded loop. Serves as the baseline
execution technique for benchmarking.
"""

import time
from typing import Any

import pandas as pd

from scaleforecast.forecast_engine import forecast_skus


def run(
    filepath: str,
    num_workers: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Execute demand forecasting sequentially on all SKUs in the dataset.

    Args:
        filepath: Path to the dataset CSV.
        num_workers: Ignored for sequential execution (kept for uniform API).

    Returns:
        (results, timing) where:
          - results: list of forecast result dicts
          - timing: dict with keys 'compute_time', 'overhead_time', 'total_time'
    """
    t0 = time.perf_counter()

    df = pd.read_csv(filepath)
    records = df.to_dict("records")

    t_load = time.perf_counter()

    results = forecast_skus(records)

    t_end = time.perf_counter()

    timing = {
        "compute_time": t_end - t_load,
        "overhead_time": t_load - t0,
        "total_time": t_end - t0,
    }

    return results, timing
