"""
Mock SKU dataset generator for ScaleForecast.

Generates synthetic e-commerce SKU datasets at configurable volumes
with category-specific daily sales patterns over a 90-day trailing window.
Supports 5 predefined volume tiers (10K → 2M) plus custom N, deterministic
seeding, and chunked CSV writing for memory-safe generation of large tiers.
"""

import json
import os
from datetime import datetime
from typing import Optional, Callable

import numpy as np
import pandas as pd

from scaleforecast import config
from scaleforecast.constants import (
    DAILY_SALES_WINDOW,
    WRITE_CHUNK_SIZE,
    DAYS_OF_SUPPLY_TIERS,
    DATASET_FILENAME_PREFIX,
    DATASET_FILENAME_SUFFIX,
    DATASET_TIMESTAMP_FORMAT,
    DATASET_TIMESTAMP_PARSE_FORMAT,
    MODERATE_SEASONAL_AMPLITUDE,
    MODERATE_SEASONAL_PERIOD,
    HIGH_SEASONAL_AMPLITUDE,
    HIGH_SEASONAL_PERIOD,
    SPIKE_MULTIPLIER_LOW,
    SPIKE_MULTIPLIER_HIGH,
    SPIKE_COUNT_RANGE,
)


CATEGORIES: list[str] = [
    "Electronics",
    "Apparel",
    "Home & Living",
    "Groceries",
    "Beauty",
    "Toys",
    "Seasonal",
]

VOLUME_TIERS: dict[str, int] = {
    "1": 10_000,
    "2": 100_000,
    "3": 500_000,
    "4": 1_000_000,
    "5": 2_000_000,
}

DEFAULT_CATEGORY_DISTRIBUTION: dict[str, float] = {
    "Electronics": 0.20,
    "Apparel": 0.20,
    "Home & Living": 0.20,
    "Groceries": 0.15,
    "Beauty": 0.10,
    "Toys": 0.10,
    "Seasonal": 0.05,
}

CATEGORY_SALES_PARAMS: dict[str, dict] = {
    "Electronics": {"base_mean": 20, "base_std": 5, "variance_type": "low"},
    "Groceries": {"base_mean": 40, "base_std": 8, "variance_type": "low"},
    "Apparel": {"base_mean": 30, "base_std": 12, "variance_type": "moderate"},
    "Beauty": {"base_mean": 35, "base_std": 14, "variance_type": "moderate"},
    "Home & Living": {"base_mean": 15, "base_std": 8, "variance_type": "low"},
    "Toys": {"base_mean": 20, "base_std": 20, "variance_type": "high"},
    "Seasonal": {"base_mean": 12, "base_std": 30, "variance_type": "high"},
}

CATEGORY_COST_RANGE: dict[str, tuple[float, float]] = {
    "Electronics": (50.0, 2000.0),
    "Groceries": (2.0, 50.0),
    "Apparel": (15.0, 150.0),
    "Beauty": (5.0, 100.0),
    "Home & Living": (10.0, 500.0),
    "Toys": (5.0, 80.0),
    "Seasonal": (3.0, 60.0),
}

CATEGORY_LEAD_TIME: dict[str, tuple[int, int]] = {
    "Electronics": (3, 14),
    "Groceries": (1, 5),
    "Apparel": (7, 21),
    "Beauty": (3, 10),
    "Home & Living": (5, 20),
    "Toys": (7, 30),
    "Seasonal": (10, 45),
}


def _generate_daily_sales(
    rng: np.random.Generator,
    category: str,
    days: int = DAILY_SALES_WINDOW,
) -> list[int]:
    """
    Generate a simulated daily sales array for a SKU of a given category.

    Each category has a distinct sales pattern:
      - low variance: stable demand with minor noise
      - moderate variance: sinusoidal seasonal pattern + noise
      - high variance: strong sinusoidal pattern + random spike events
    """
    params = CATEGORY_SALES_PARAMS[category]
    base_mean = params["base_mean"]
    base_std = params["base_std"]
    variance_type = params["variance_type"]

    day_indices = np.arange(days)

    if variance_type == "low":
        noise = rng.normal(0, base_std, days).astype(int)
        sales = np.full(days, int(base_mean)) + noise
        sales = np.clip(sales, 0, None)

    elif variance_type == "moderate":
        seasonal = (base_mean * MODERATE_SEASONAL_AMPLITUDE
                    * np.sin(2 * np.pi * day_indices / MODERATE_SEASONAL_PERIOD)).astype(int)
        noise = rng.normal(0, base_std, days).astype(int)
        sales = int(base_mean) + seasonal + noise
        sales = np.clip(sales, 0, None)

    elif variance_type == "high":
        seasonal = (base_mean * HIGH_SEASONAL_AMPLITUDE
                    * np.sin(2 * np.pi * day_indices / HIGH_SEASONAL_PERIOD)).astype(int)
        noise = rng.normal(0, base_std, days).astype(int)
        sales = int(base_mean) + seasonal + noise
        spike_lo, spike_hi = SPIKE_COUNT_RANGE
        num_spikes = rng.integers(spike_lo, spike_hi)
        spike_indices = rng.choice(days, size=num_spikes, replace=False)
        spike_magnitudes = rng.integers(
            int(base_mean * SPIKE_MULTIPLIER_LOW),
            int(base_mean * SPIKE_MULTIPLIER_HIGH),
            size=num_spikes,
        )
        for idx, mag in zip(spike_indices, spike_magnitudes):
            sales[idx] += mag
        sales = np.clip(sales, 0, None)

    return sales.astype(int).tolist()


def _assign_categories(
    num_skus: int,
    distribution: dict[str, float],
    rng: np.random.Generator,
) -> np.ndarray:
    """Assign categories to SKUs based on the given probability distribution."""
    cat_names = list(distribution.keys())
    probs = np.array([distribution[c] for c in cat_names], dtype=float)
    probs /= probs.sum()
    return rng.choice(cat_names, size=num_skus, p=probs)


def _compute_current_stock(
    daily_sales: list[int],
    rng: np.random.Generator,
) -> int:
    """
    Derive current_stock from the SKU's own average daily sales via a
    randomized days-of-supply multiplier.

    Distribution (per Section 5.2a):
      ~10% →  0–10 days  (critically understocked)
      ~20% → 11–29 days  (lean inventory)
      ~55% → 30–60 days  (healthy stock)
      ~15% → 61–90 days  (overstocked / bulk-bought)
    """
    sales_arr = np.array(daily_sales, dtype=np.float64)
    avg_daily = float(np.mean(sales_arr))
    if avg_daily <= 0:
        return 0

    weights = [t[0] for t in DAYS_OF_SUPPLY_TIERS]
    norm_weights = np.array(weights) / sum(weights)
    tier_idx = rng.choice(len(DAYS_OF_SUPPLY_TIERS), p=norm_weights)
    _, lo, hi = DAYS_OF_SUPPLY_TIERS[tier_idx]
    days_of_supply = rng.integers(lo, hi + 1)

    return max(0, int(round(avg_daily * days_of_supply)))


def generate_dataset(
    num_skus: int,
    category_distribution: Optional[dict[str, float]] = None,
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Generate a mock SKU dataset and save it as a timestamped CSV.

    Args:
        num_skus: Total number of SKU records to generate.
        category_distribution: Dict of category -> probability (0-1).
            Defaults to DEFAULT_CATEGORY_DISTRIBUTION.
        seed: Optional RNG seed for deterministic reproduction.
        output_dir: Directory to save the CSV. Defaults to scaleforecast/data/.
        progress_callback: Optional callable(current, total) for progress reporting.

    Returns:
        Absolute path to the generated CSV file.
    """
    if output_dir is None:
        output_dir = str(config.DATA_DIR)
    config.ensure_dir(output_dir)

    if category_distribution is None:
        category_distribution = DEFAULT_CATEGORY_DISTRIBUTION

    rng = np.random.default_rng(seed)

    categories_arr = _assign_categories(num_skus, category_distribution, rng)

    timestamp = datetime.now().strftime(DATASET_TIMESTAMP_FORMAT)
    filename = f"{DATASET_FILENAME_PREFIX}{num_skus}_{timestamp}{DATASET_FILENAME_SUFFIX}"
    filepath = os.path.join(output_dir, filename)

    header_written = False
    for start in range(0, num_skus, WRITE_CHUNK_SIZE):
        end = min(start + WRITE_CHUNK_SIZE, num_skus)
        chunk_size = end - start

        chunk_categories = categories_arr[start:end]

        rows = []
        for i in range(chunk_size):
            idx = start + i
            category = chunk_categories[i]

            sku_id = f"SKU-{idx + 1:06d}"

            daily_sales = _generate_daily_sales(rng, category)
            current_stock = _compute_current_stock(daily_sales, rng)

            lt_low, lt_high = CATEGORY_LEAD_TIME[category]
            lead_time_days = int(rng.integers(lt_low, lt_high + 1))

            cost_low, cost_high = CATEGORY_COST_RANGE[category]
            unit_cost = round(float(rng.uniform(cost_low, cost_high)), 2)

            rows.append({
                "sku_id": sku_id,
                "category": category,
                "current_stock": current_stock,
                "lead_time_days": lead_time_days,
                "unit_cost": unit_cost,
                "daily_sales": json.dumps(daily_sales),
            })

        chunk_df = pd.DataFrame(rows)
        chunk_df.to_csv(
            filepath,
            mode="a",
            header=not header_written,
            index=False,
        )
        header_written = True

        if progress_callback:
            progress_callback(end, num_skus)

    return filepath


def get_dataset_preview(filepath: str, rows: int = 5) -> pd.DataFrame:
    """Read the first *rows* records of a dataset CSV for preview display."""
    df = pd.read_csv(filepath, nrows=rows)
    # Parse daily_sales back to list for display
    if "daily_sales" in df.columns:
        df["daily_sales"] = df["daily_sales"].apply(
            lambda x: json.loads(x) if isinstance(x, str) else x
        )
    return df


def get_dataset_info(filepath: str) -> dict:
    """Return metadata about a generated dataset file."""
    file_size = os.path.getsize(filepath)
    # Efficient row count: stream the file and count newlines (header excluded).
    # ~1000x faster than pandas for multi-million-row datasets.
    with open(filepath, "rb") as f:
        row_count = max(0, sum(1 for _ in f) - 1)
    return {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "sku_count": row_count,
        "file_size_bytes": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
    }


def extract_timestamp_from_filename(filename: str) -> str:
    """Extract a human-readable timestamp from a dataset filename."""
    stem = filename
    if stem.endswith(DATASET_FILENAME_SUFFIX):
        stem = stem[: -len(DATASET_FILENAME_SUFFIX)]
    parts = stem.split("_")
    if len(parts) >= 4:
        date_str = parts[-2]
        time_str = parts[-1]
        try:
            dt = datetime.strptime(f"{date_str}_{time_str}", DATASET_TIMESTAMP_PARSE_FORMAT)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return "Unknown"


if __name__ == "__main__":
    # Quick smoke test: generate a tiny 500-SKU dataset
    path = generate_dataset(500, seed=42)
    info = get_dataset_info(path)
    print(f"Generated: {info['filename']} ({info['sku_count']} SKUs, {info['file_size_mb']} MB)")
    preview = get_dataset_preview(path)
    print(preview.to_string())
