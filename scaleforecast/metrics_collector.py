"""
Metrics collection utilities for ScaleForecast.

Wraps an executor run to collect all 7 benchmark metrics specified in PRD
Section 7: wall-clock time, speedup, efficiency, throughput, per-core CPU
utilization, overhead breakdown, and peak memory usage.

Uses psutil for CPU/memory sampling and time.perf_counter for high-resolution
timing. A background sampler thread polls CPU and memory at 100 ms intervals
during the executor's compute phase.
"""

import os
import threading
import time
from typing import Any, Callable, Optional

import psutil

from scaleforecast.interpreter_detection import IS_FREE_THREADED

_SAMPLE_INTERVAL = 0.1


class _SamplerThread(threading.Thread):
    """
    Background thread that samples per-core CPU utilization and process
    memory at a fixed interval while an executor is running.
    """

    def __init__(self, interval: float = _SAMPLE_INTERVAL):
        super().__init__(daemon=True)
        self.interval = interval
        self._stop_event = threading.Event()
        self.cpu_samples: list[list[float]] = []
        self.memory_samples: list[float] = []
        self.peak_memory_bytes: int = 0
        self.process = psutil.Process(os.getpid())

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cpu_per_core = psutil.cpu_percent(percpu=True)
                self.cpu_samples.append(cpu_per_core)
            except Exception:
                self.cpu_samples.append([])
            try:
                mem = self.process.memory_info().rss
                self.memory_samples.append(mem)
                if mem > self.peak_memory_bytes:
                    self.peak_memory_bytes = mem
            except Exception:
                pass
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=2)

    def avg_cpu_per_core(self) -> list[float]:
        """Average per-core CPU utilization across all samples."""
        if not self.cpu_samples:
            return []
        num_cores = len(self.cpu_samples[0]) if self.cpu_samples[0] else 0
        if num_cores == 0:
            return []
        avgs = []
        for core_idx in range(num_cores):
            vals = [s[core_idx] for s in self.cpu_samples if core_idx < len(s)]
            avgs.append(sum(vals) / len(vals) if vals else 0.0)
        return avgs

    def avg_cpu_overall(self) -> float:
        """Average CPU utilization across all cores and samples."""
        avgs = self.avg_cpu_per_core()
        if not avgs:
            return 0.0
        return sum(avgs) / len(avgs)

    def avg_memory_mb(self) -> float:
        """Average RSS memory in MB across all samples."""
        if not self.memory_samples:
            return 0.0
        return (sum(self.memory_samples) / len(self.memory_samples)) / (1024 * 1024)

    @property
    def peak_memory_mb(self) -> float:
        return self.peak_memory_bytes / (1024 * 1024)


def collect(
    executor_fn: Callable,
    filepath: str,
    num_workers: int = 4,
    sequential_baseline_time: Optional[float] = None,
) -> dict[str, Any]:
    """
    Run an executor and collect all 7 benchmark metrics.

    Args:
        executor_fn: An executor module's `run` function (e.g. sequential.run).
        filepath: Path to the dataset CSV.
        num_workers: Number of threads/processes to use.
        sequential_baseline_time: If provided, used to compute speedup/efficiency
            for non-sequential techniques. If None (sequential run), speedup=1.0.

    Returns:
        Dict containing all 7 metrics + metadata.
    """
    sampler = _SamplerThread()
    sampler.start()

    t_start = time.perf_counter()
    results, executor_timing = executor_fn(filepath, num_workers=num_workers)
    t_end = time.perf_counter()

    sampler.stop()

    wall_time = t_end - t_start
    compute_time = executor_timing.get("compute_time", wall_time)
    overhead_time = executor_timing.get("overhead_time", 0.0)
    num_records = len(results)

    speedup = 1.0
    efficiency = 1.0
    if sequential_baseline_time and sequential_baseline_time > 0 and wall_time > 0:
        speedup = sequential_baseline_time / wall_time
        efficiency = speedup / max(num_workers, 1)
    elif not sequential_baseline_time:
        speedup = 1.0
        efficiency = 1.0 / max(num_workers, 1) if num_workers > 0 else 1.0

    throughput = num_records / wall_time if wall_time > 0 else 0.0

    cpu_per_core = sampler.avg_cpu_per_core()
    cpu_overall = sampler.avg_cpu_overall()

    peak_memory_mb = sampler.peak_memory_mb
    avg_memory_mb = sampler.avg_memory_mb()

    for_mp_memory_mb = 0.0
    try:
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        child_rss = sum(c.memory_info().rss for c in children)
        for_mp_memory_mb = child_rss / (1024 * 1024)
    except Exception:
        pass

    return {
        "technique": "",
        "interpreter_label": "Free-threaded" if IS_FREE_THREADED else "GIL-enabled",
        "num_records": num_records,
        "num_workers": num_workers,
        "wall_time": wall_time,
        "compute_time": compute_time,
        "overhead_time": overhead_time,
        "speedup": speedup,
        "efficiency": efficiency,
        "throughput": throughput,
        "cpu_per_core": cpu_per_core,
        "cpu_overall_percent": cpu_overall,
        "peak_memory_mb": peak_memory_mb,
        "avg_memory_mb": avg_memory_mb,
        "child_process_memory_mb": for_mp_memory_mb,
        "executor_timing": executor_timing,
    }
