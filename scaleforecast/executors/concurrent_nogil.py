"""
Concurrent (No-GIL threading) executor for ScaleForecast.

This module delegates to the same threading implementation as concurrent_gil.py.
The difference in behaviour (true parallelism for CPU-bound work) is determined
entirely by which CPython interpreter binary is running the script:

  - Standard python3.13   → GIL serialises threads (slow)
  - Free-threaded python3.13t → threads run in parallel (fast)

Per PRD Section 6.7, the system MUST detect which interpreter is active at
runtime and label results accordingly. This module is a thin wrapper that
imports the shared threaded execution logic.
"""

from scaleforecast.executors.concurrent_gil import run

__all__ = ["run"]
