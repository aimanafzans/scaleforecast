# NUR AIMAN AFZAN BIN AZHAR

![Uploading image.png…](https://github.com/aimanafzans/scaleforecast/blob/main/assets/scaleforecast-logo.png)

# ScaleForecast: Multi-Technique Demand Forecasting Engine

### 📝 *ITT440 - INDIVIDUAL ASSIGNMENT*

**👨‍🎓 NAME : NUR AIMAN AFZAN BIN AZHAR**

**🎓 STUDENT ID : 2025226838**

**👥 GROUP : M3CS2554C**

**GITHUB LINK : [ITT440 - GITHUB](https://github.com/aimanafzans/scaleforecast)**

**YOUTUBE LINK : [ITT440 - INDIVIDUAL ASSIGNMENT](https://youtu.be/VqJLgOwQ_0E)**

---

## 📝 Project Overview

ScaleForecast is a menu-driven Python application that forecasts e-commerce demand — moving averages, volatility, safety stock, reorder points, and stockout risk — across catalogs of up to 2,000,000+ SKUs. It also benchmarks that exact forecasting workload across four Python execution strategies: **Sequential**, **Concurrent (With GIL)**, **Concurrent (No GIL)**, and **Multiprocessing**.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Key Features](#key-features)
- [Execution Techniques](#execution-techniques)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [How to Run](#how-to-run)
- [Usage Walkthrough](#usage-walkthrough)
- [Sample Output](#sample-output)
- [Benchmark Methodology](#benchmark-methodology)
- [Results](#results)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Design Notes](#design-notes)
- [Demonstration Video](#demonstration-video)

---

## Problem Statement

Small and mid-sized e-commerce sellers often lack the tooling to forecast demand and identify at-risk-of-stockout products as their catalog grows into hundreds of thousands of SKUs. Computing rolling statistics — moving averages, demand volatility, safety stock, reorder points — across a large product catalog with long sales histories is CPU-bound and becomes a real bottleneck when done sequentially.

This project investigates **which Python concurrency or parallelism strategy actually accelerates this class of workload, by how much, and at what cost** — measured with real, repeatable benchmarks rather than assumptions.

## Key Features

ScaleForecast's main menu has five options. Only the fifth is about benchmarking — the rest are the actual product:

| # | Feature | Description |
|---|---|---|
| 1 | **Generate Mock SKU Dataset** | Synthetic SKU datasets at configurable volumes (10K → 2M+), with category-specific 90-day sales patterns and a realistic stock-derivation model |
| 2 | **Manage / Delete Datasets** | List, inspect, and remove generated datasets |
| 3 | **Run Demand Forecast** | Computes moving averages, volatility, safety stock, reorder point, and stockout risk per SKU, using any of the four execution techniques |
| 4 | **View Forecast Reports** | Category-level demand summaries, restock recommendations, and at-risk SKUs sorted by severity |
| 5 | **Run Performance Benchmark** | Times the same forecasting workload across all four techniques, with a full 7-metric suite and generated charts |

## Execution Techniques

All four techniques call the **exact same** `forecast_skus()` computation — no logic is duplicated per technique, so the comparison is fair.

| Technique | How it runs | What it demonstrates |
|---|---|---|
| **Sequential** | Single-threaded baseline | Reference point for all other measurements |
| **Concurrent (With GIL)** | `threading`, standard CPython (GIL enabled) | CPU-bound Python threads do **not** parallelize under the GIL |
| **Concurrent (No GIL)** | `threading`, free-threaded CPython 3.13 (`python3.13t`, PEP 703) | Genuine multi-core threading once the GIL is removed |
| **Multiprocessing** | `multiprocessing.Pool`, separate OS processes | True parallelism, at the cost of memory duplication |

## System Requirements

- **Python 3.13 or later** (standard build) — required to run the application at all
- **Python 3.13t (free-threaded build)** — optional, but required to unlock and correctly measure "Concurrent (No GIL)". Without it, that technique is disabled with an in-app explanation rather than silently mislabeling results.
- OS: developed and tested on Windows; should run on any platform with both interpreters available
- ~4 GB free disk space if generating the largest (2M SKU) dataset tier
- Dependencies: `numpy`, `pandas`, `psutil`, `matplotlib`, `rich` (see `requirements.txt`)

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

### 2. Install the standard Python 3.13+ interpreter

If you don't already have it: [python.org/downloads](https://www.python.org/downloads/)

### 3. Install dependencies

```bash
pip install -r scaleforecast/requirements.txt
```

### 4. (Optional but recommended) Install the free-threaded Python build

This unlocks and correctly benchmarks **Concurrent (No GIL)**.

**Windows:**
1. Download the Python 3.13 installer from [python.org/downloads](https://www.python.org/downloads/).
2. Run it and choose **"Customize installation"** (not the quick install).
3. Check **"Download free-threaded binaries"**.
4. Complete the install — this adds `python3.13t.exe` alongside your existing `python.exe` without affecting it.
5. Verify:
   ```powershell
   py -0p
   py -3.13t -c "import sys; print(sys._is_gil_enabled())"
   ```
   The second command should print `False`.

**macOS / Linux (via pyenv):**
```bash
pyenv install 3.13t
```

If the free-threaded build isn't installed, the app still runs fully — "Concurrent (No GIL)" is simply disabled in the benchmark menu with an explanation, and every other feature (including the other three techniques) works normally.

## How to Run

From the project root (the folder containing the `scaleforecast/` package):

```bash
# Standard run
python -m scaleforecast.main

# Run with the free-threaded interpreter to unlock Concurrent (No GIL)
python3.13t -m scaleforecast.main
```

> Benchmark results are **identical regardless of which interpreter launches the app** — every technique is dispatched to its own subprocess with an explicitly pinned interpreter. See [Design Notes](#design-notes).

## Usage Walkthrough

1. **Generate a dataset** (Option 1) — pick a volume tier (10K / 100K / 500K / 1M / 2M) or enter a custom SKU count.
2. **Run a forecast** (Option 3) — pick a dataset and a technique; the system computes per-SKU forecasts and saves a report.
3. **View the report** (Option 4) — see restock recommendations and at-risk SKUs sorted by severity.
4. **Run a benchmark** (Option 5) — pick one or more datasets and techniques, set the number of repeated runs, and get a full results table plus optional charts and CSV/JSON exports.

## Sample Output

**Startup menu** — with automatic GIL/interpreter detection and plain-language prompts:

![Startup menu](docs/screenshots/01_startup_menu.png)

**Benchmark results table** — full technique names, plain-language metric labels, fastest/slowest summary:

![Benchmark results table](docs/screenshots/02_benchmark_results_table.png)

**Category-level demand summary** (from a forecast report):

![Category demand summary](docs/screenshots/03_category_demand_summary.png)

**At-risk SKUs, sorted by severity:**

![At-risk SKUs report](docs/screenshots/04_at_risk_skus_report.png)

## Benchmark Methodology

Each (technique × dataset size) combination is run multiple times (default 3, configurable), and results are aggregated as mean and typical run-to-run variation. Seven metrics are collected per run:

| Metric | What it measures |
|---|---|
| **Average Time (s)** | Wall-clock time to process the full dataset |
| **Typical Variation (±s)** | Run-to-run consistency across repeats |
| **Speedup** | Sequential time ÷ this technique's time |
| **Efficiency (%)** | Speedup ÷ number of workers — how well each worker actually contributed |
| **Throughput (rec/s)** | Records processed per second |
| **Avg CPU Usage (%)** | Share of total machine capacity consumed by the technique's own process(es), normalized so all four techniques are on the same 0–100% scale |
| **Setup Overhead (s)** | Fixed cost (subprocess spawn, interpreter startup, data load) separated from compute time |
| **Peak Memory (MB)** | Highest memory footprint reached during the run |

Every technique — including Sequential and Multiprocessing — runs in its own subprocess with an explicitly pinned interpreter, so results are reproducible regardless of which interpreter launches the main application. See [Design Notes](#design-notes) for why this matters.

## Results

Full-scale benchmark at **2,000,000 SKUs**, 3 repeats per technique, 8 workers:

| Technique | Avg Time (s) | Speedup | Efficiency | Avg CPU Usage | Peak Memory |
|---|---|---|---|---|---|
| Sequential | 148.12 | 1.00× | 100.0% | 6.2% | 1,719 MB |
| Concurrent (With GIL) | 150.29 | 0.99× | 12.3% | 6.2% | 1,733 MB |
| Concurrent (No GIL) | 86.47 | 1.71× | 21.4% | 45.6% | 3,575 MB |
| Multiprocessing | 51.62 | 2.87× | 35.9% | 42.3% | 3,960 MB |

**Speedup vs. Sequential:**

![Speedup vs dataset size](docs/screenshots/05_chart_speedup_vs_size.png)

**Time vs. dataset size:**

![Time vs dataset size](docs/screenshots/06_chart_time_vs_size.png)

**CPU utilization by technique** — the mechanistic proof behind the speedup numbers:

![CPU utilization comparison](docs/screenshots/07_chart_cpu_utilization.png)

**Peak memory by technique** — the tradeoff multiprocessing pays for its speed:

![Peak memory comparison](docs/screenshots/08_chart_peak_memory.png)

### Key findings

- **Concurrent (With GIL) shows no real speedup** (0.99×) — the expected result for CPU-bound Python threading under the GIL, confirmed by measurement rather than assumed.
- **Concurrent (No GIL) delivers a genuine 1.71× speedup** once threads can run Python bytecode truly in parallel under the free-threaded build.
- **Multiprocessing is fastest overall (2.87×)**, at the cost of roughly double the memory footprint — each worker process holds its own independent copy of its data chunk.
- CPU usage numbers back this up directly: the two GIL-bound techniques barely exceed 6% of total system capacity, while the two genuinely parallel techniques reach 40%+.

## Project Structure

```
scaleforecast/
├── main.py                   # Entry point
├── forecast_engine.py        # Shared forecasting computation (used by all 4 techniques)
├── _runner.py                # Subprocess runner — executes one technique under a pinned interpreter
├── benchmark.py               # Benchmark orchestration, subprocess dispatch, metrics aggregation
├── interpreter_detection.py  # GIL / free-threaded interpreter detection
├── data_generator.py         # Synthetic SKU dataset generation
├── data_manager.py           # Dataset listing / deletion
├── report_generator.py       # Forecast report generation
├── chart_generator.py        # Benchmark chart generation (matplotlib)
├── metrics_collector.py      # CPU / memory measurement helpers
├── models.py                 # Shared dataclasses and enums
├── constants.py               # Centralised thresholds, labels, and tunables
├── config.py                  # Filesystem paths and filename validation
├── executors/                 # Per-technique execution wrappers (used by Option 3)
│   ├── sequential.py
│   ├── concurrent_gil.py
│   ├── concurrent_nogil.py
│   └── parallel_multiprocessing.py
├── cli/                       # Menu, controllers, and terminal UI (rich-powered)
│   ├── app.py
│   └── controllers/
├── data/                       # Generated datasets (git-ignored)
├── reports/                    # Generated forecast reports (git-ignored)
└── benchmarks/                 # Benchmark results and charts (git-ignored)

tests/                          # pytest test suite
PRD.md                          # Full product requirements document
```

## Testing

```bash
pip install pytest
pytest tests/
```

The test suite covers dataset generation, the forecasting engine, interpreter detection, the CLI, and benchmark aggregation logic.

## Design Notes

**Why every technique runs in its own subprocess.** The Global Interpreter Lock's state is fixed for an entire Python process at interpreter startup — it cannot be toggled per function call. Early in development, this caused a real correctness bug: when the whole app was launched with the free-threaded interpreter, *every* thread inside it — including the ones meant to demonstrate "With GIL" behavior — actually ran GIL-disabled, silently invalidating the comparison.

The fix: every technique is dispatched to its own subprocess with an interpreter explicitly pinned for that technique — standard Python for Sequential, Concurrent (With GIL), and Multiprocessing; `python3.13t` for Concurrent (No GIL) — regardless of which interpreter launched the main application. Each subprocess self-reports its actual GIL state (`sys._is_gil_enabled()`), and the benchmark cross-checks it against what was expected, surfacing a visible warning on any mismatch rather than trusting the label silently. This was verified to produce identical results whether the app itself is launched with `python`, `python3.13`, or `python3.13t`.

**Why `current_stock` isn't purely random.** Stock levels are derived from each SKU's own average daily sales via a randomized days-of-supply multiplier, rather than generated independently. This keeps the at-risk-of-stockout rate in a realistic 5–20% range instead of the ~50% that results from fully independent random stock values, and produces a defensible, category-correlated risk pattern (see Results).

Full design rationale, requirements, and decision history are documented in [`PRD.md`](PRD.md).

---

