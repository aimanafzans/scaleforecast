"""
Centralised constants for ScaleForecast.

All tunable thresholds, display names, chart settings, and filename
conventions live here so they can be referenced by name and changed in one
place instead of being scattered as inline literals.
"""

from __future__ import annotations

# ── Forecasting engine parameters ──────────────────────────────────────────

Z_SCORE: float = 1.65
"""Service-level z-score (~95% confidence) used in safety-stock formula."""

MA_WINDOWS: tuple[int, int] = (7, 30)
"""Short and long moving-average windows (days) reported per SKU."""

DEMAND_STD_DDOF: int = 1
"""Delta degrees of freedom for demand std in safety-stock calculation."""

DEFAULT_LEAD_TIME_DAYS: int = 7
"""Fallback lead time when a SKU record omits the field (compute layer)."""

DEFAULT_MIN_LEAD_TIME: int = 1
"""Minimum lead-time enforced inside _safety_stock (avoids sqrt(0))."""

# ── Data generation parameters ──────────────────────────────────────────────

DAILY_SALES_WINDOW: int = 90
"""Length (days) of the trailing daily-sales window simulated per SKU."""

WRITE_CHUNK_SIZE: int = 50_000
"""Number of SKU rows written to CSV per flush during dataset generation."""

# Sinusoidal seasonal pattern parameters used by _generate_daily_sales.

MODERATE_SEASONAL_AMPLITUDE: float = 0.3
"""Fraction of base_mean used as sinusoid amplitude for moderate-variance SKUs."""

MODERATE_SEASONAL_PERIOD: int = 45
"""Period (days) of the moderate seasonal sinusoid."""

HIGH_SEASONAL_AMPLITUDE: float = 0.6
"""Fraction of base_mean used as sinusoid amplitude for high-variance SKUs."""

HIGH_SEASONAL_PERIOD: int = 30
"""Period (days) of the high-variance seasonal sinusoid."""

SPIKE_MULTIPLIER_LOW: float = 1.5
"""Lower bound for random spike-event magnitude (× base_mean)."""

SPIKE_MULTIPLIER_HIGH: float = 4.0
"""Upper bound for random spike-event magnitude (× base_mean)."""

SPIKE_COUNT_RANGE: tuple[int, int] = (1, 4)
"""Half-open range [low, high) of spike events per high-variance SKU."""

# Days-of-supply distribution for deriving current_stock (PRD Section 5.2a).
# Each tuple is (weight, min_days, max_days). Weights are relative frequencies.
DAYS_OF_SUPPLY_TIERS: list[tuple[float, int, int]] = [
    (0.10, 0, 10),      # Critically understocked
    (0.20, 11, 29),     # Lean inventory
    (0.55, 30, 60),     # Healthy stock (typical)
    (0.15, 61, 90),     # Overstocked / bulk-bought
]

# ── Stockout-risk classification thresholds ───────────────────────────────

RISK_CRITICAL_RATIO: float = 0.5
"""current_stock < RISK_CRITICAL_RATIO * reorder_point  → Critical."""

RISK_VOLATILITY_THRESHOLD: float = 0.5
"""current_stock < reorder_point AND volatility > threshold → High."""

AT_RISK_LEVELS: tuple[str, ...] = ("Medium", "High", "Critical")
"""Stockout-risk levels considered "at risk" for filtering and reporting."""

RISK_SEVERITY_ORDER: dict[str, int] = {"Critical": 0, "High": 1, "Medium": 2}
"""Sort key for at-risk SKUs by severity (Critical first)."""

# ── Display precision (rounding at the display / CSV boundary) ────────────
#
# The forecast engine returns raw full-precision floats. To keep the on-disk
# CSV byte-identical to the historical (pre-Phase-2) format, the report
# generator rounds the listed columns before writing CSV.

REPORT_COLUMN_ROUND_2DP: tuple[str, ...] = (
    "avg_daily_demand", "ma_7day", "ma_30day",
    "demand_std", "safety_stock", "reorder_point",
)
"""Forecast metric columns that are displayed rounded to 2 decimal places."""

REPORT_COLUMN_ROUND_4DP: tuple[str, ...] = ("volatility",)
"""Volatility is rounded to 4 dp on disk / display (legacy convention)."""

# ── Benchmark / execution defaults ─────────────────────────────────────────

DEFAULT_REPEATS: int = 3
"""Default number of repeated runs per (technique x dataset) combination."""

DEFAULT_MAX_WORKERS: int = 8
"""Cap on number of workers/threads when defaulting to cpu_count()."""

WARMUP_RUNS: int = 0
"""Warm-up runs discarded before timed measurement (PRD Section 7.1)."""

# ── Chart rendering defaults ────────────────────────────────────────────────

CHART_DPI: int = 150
"""DPI used when saving all benchmark charts."""

CHART_DPI_PRESENTATION: int = 300
"""DPI used for presentation-quality chart exports."""

CHART_FIGSIZE: tuple[int, int] = (10, 6)
"""Default matplotlib figure size (W, H) in inches."""

CHART_FIGSIZE_WIDE: tuple[int, int] = (12, 6)
"""Wider figure for stacked / multi-series charts."""

CHART_MARKER_SIZE: int = 6
CHART_LINE_WIDTH: int = 2
CHART_GRID_ALPHA: float = 0.3
CHART_ALPHA_OVERLAY: float = 0.35
CHART_HATCH: str = "//"
CHART_FONT_SIZE_LEGEND: int = 9
CHART_FONT_SIZE_LEGEND_PRESENTATION: int = 12
CHART_FONT_SIZE_TICKS: int = 8
CHART_FONT_SIZE_TICKS_PRESENTATION: int = 11
CHART_FONT_SIZE_ANNOTATE: int = 9
CHART_FONT_SIZE_ANNOTATE_PRESENTATION: int = 12
CHART_FONT_SIZE_LEGEND_SMALL: int = 7
CHART_BAR_WIDTH: float = 0.2
CHART_CPU_YLIM_FLOOR: float = 10.0
CHART_CPU_YLIM_PAD: float = 1.2
CHART_AXIS_PAD: float = 0.5
CHART_ROTATION: int = 30

TECHNIQUE_COLORS: dict[str, str] = {
    "sequential": "#1f77b4",
    "concurrent_gil": "#ff7f0e",
    "concurrent_nogil": "#2ca02c",
    "parallel_multiprocessing": "#d62728",
}

TECHNIQUE_LABELS: dict[str, str] = {
    "sequential": "Sequential",
    "concurrent_gil": "Concurrent (With GIL)",
    "concurrent_nogil": "Concurrent (No GIL)",
    "parallel_multiprocessing": "Multiprocessing",
}

TECHNIQUE_DEFAULT_COLOR: str = "#333333"
"""Fallback color used by the chart generator for unknown technique keys."""

# ── File-name / directory conventions ──────────────────────────────────────

DATASET_FILENAME_PREFIX: str = "sku_dataset_"
DATASET_FILENAME_SUFFIX: str = ".csv"
REPORT_FILENAME_PREFIX: str = "forecast_report_"
REPORT_FILENAME_SUFFIX: str = ".csv"
CHART_FILENAME_PREFIX: str = "chart_"
CHART_FILENAME_SUFFIX: str = ".png"

DATASET_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M"
REPORT_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"
CHART_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"

DATASET_TIMESTAMP_PARSE_FORMAT: str = "%Y%m%d_%H%M"

# ── Interpreter / GIL detection ────────────────────────────────────────────

PYTHON_FREETHREADED_CANDIDATES: tuple[str, ...] = ("python3.13t", "python3.13t.exe")

DEFAULT_Z_FALLBACK: bool = True
"""Default GIL state assumed for Python < 3.13 without _is_gil_enabled()."""