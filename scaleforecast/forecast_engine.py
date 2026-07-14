"""
Core forecasting computation engine for ScaleForecast.

Contains the single shared compute function `forecast_skus()` that all four
executor techniques (sequential, concurrent-GIL, concurrent-NoGIL,
multiprocessing) call identically. No logic is duplicated across executors —
this module is the single source of truth for the forecasting algorithm.

Per-SKU metrics computed:
  - 7-day and 30-day moving average demand
  - Demand volatility score (rolling standard deviation)
  - Safety stock (z-score × σ_demand × √lead_time)
  - Reorder point = (avg daily demand × lead_time) + safety_stock
  - Stockout risk flag (Low / Medium / High / Critical)
"""

import json
import math
from typing import Any

import numpy as np

from scaleforecast.constants import (
    Z_SCORE as DEFAULT_Z_SCORE,
    MA_WINDOWS,
    DEFAULT_LEAD_TIME_DAYS,
    DEFAULT_MIN_LEAD_TIME,
    DEMAND_STD_DDOF,
    RISK_CRITICAL_RATIO,
    RISK_VOLATILITY_THRESHOLD,
)
from scaleforecast.models import RiskLevel


def _moving_average(series: np.ndarray, window: int) -> float:
    """Compute the simple moving average of the last *window* elements."""
    if len(series) == 0:
        return 0.0
    actual_window = min(window, len(series))
    return float(np.mean(series[-actual_window:]))


def _volatility_score(series: np.ndarray) -> float:
    """
    Compute demand volatility as the coefficient of variation (CV)
    over the full 90-day window: std / mean.
    Returns 0.0 if mean is zero.
    """
    mean_val = float(np.mean(series))
    if mean_val == 0:
        return 0.0
    return float(np.std(series, ddof=1) / mean_val)


def _safety_stock(
    demand_std: float,
    lead_time_days: int,
    z_score: float = DEFAULT_Z_SCORE,
) -> float:
    """
    Standard safety stock formula:
        SS = z × σ_d × √L
    where σ_d is the standard deviation of daily demand (90-day window) and
    L is the replenishment lead time in days.
    """
    return z_score * demand_std * math.sqrt(max(lead_time_days, DEFAULT_MIN_LEAD_TIME))


def _reorder_point(
    avg_daily_demand: float,
    lead_time_days: int,
    safety_stock_val: float,
) -> float:
    """
    Reorder point = (average daily demand × lead time) + safety stock.
    """
    return (avg_daily_demand * lead_time_days) + safety_stock_val


def _stockout_risk(
    current_stock: int,
    reorder_point_val: float,
    volatility: float,
) -> RiskLevel:
    """
    Classify stockout risk based on current stock vs reorder point
    and demand volatility.

    Thresholds (PRD Section 6.4):
      - Critical: current_stock < RISK_CRITICAL_RATIO × reorder_point
      - High:     current_stock < reorder_point AND volatility > RISK_VOLATILITY_THRESHOLD
      - Medium:   current_stock < reorder_point
      - Low:      current_stock >= reorder_point

    Returns a :class:`RiskLevel` (a ``StrEnum`` whose members ARE plain
    ``str`` instances — the value "Critical" round-trips through CSV/JSON
    identically to the previously-hardcoded string literal).
    """
    if current_stock < reorder_point_val * RISK_CRITICAL_RATIO:
        return RiskLevel.CRITICAL
    elif current_stock < reorder_point_val:
        if volatility > RISK_VOLATILITY_THRESHOLD:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def forecast_single(
    daily_sales: list[int],
    lead_time_days: int,
    current_stock: int,
    z_score: float = DEFAULT_Z_SCORE,
) -> dict[str, Any]:
    """
    Compute all forecast metrics for a single SKU.

    This is the **pure computation layer**: returns raw, full-precision
    floats.  Rounding/precision is applied ONLY at display boundaries
    (e.g. :mod:`scaleforecast.report_generator` rounds columns before
    writing CSVs) so that downstream code (sorting, filtering, further
    math, JSON subprocess payloads) never loses precision.

    Args:
        daily_sales: List of 90 daily sales integers.
        lead_time_days: Supplier replenishment lead time in days.
        current_stock: Current inventory count.
        z_score: Service-level z-score (default 1.65 for ~95%).

    Returns:
        Dict with keys: avg_daily_demand, ma_7day, ma_30day, volatility,
        demand_std, safety_stock, reorder_point, stockout_risk,
        recommended_order_qty.
    """
    sales_arr = np.array(daily_sales, dtype=np.float64)

    avg_daily_demand = float(np.mean(sales_arr))
    demand_std = float(np.std(sales_arr, ddof=DEMAND_STD_DDOF))
    ma_7day_val = _moving_average(sales_arr, MA_WINDOWS[0])
    ma_30day_val = _moving_average(sales_arr, MA_WINDOWS[1])
    vol = _volatility_score(sales_arr)

    ss = _safety_stock(demand_std, lead_time_days, z_score)
    rp = _reorder_point(avg_daily_demand, lead_time_days, ss)
    risk = _stockout_risk(current_stock, rp, vol)

    recommended_qty = 0
    if current_stock < rp:
        recommended_qty = max(0, int(math.ceil(rp - current_stock)))

    return {
        "avg_daily_demand": avg_daily_demand,
        "ma_7day": ma_7day_val,
        "ma_30day": ma_30day_val,
        "volatility": vol,
        "demand_std": demand_std,
        "safety_stock": ss,
        "reorder_point": rp,
        "stockout_risk": risk,
        "recommended_order_qty": recommended_qty,
    }


def forecast_skus(
    sku_records: list[dict[str, Any]],
    z_score: float = DEFAULT_Z_SCORE,
) -> list[dict[str, Any]]:
    """
    Core forecasting function — the single shared entry point called by all
    four executor techniques.

    For each SKU record, computes moving averages, volatility, safety stock,
    reorder point, and stockout risk. Returns a list of result dicts enriched
    with the original record fields plus computed forecast metrics.

    Args:
        sku_records: List of SKU dicts. Each dict must contain:
            - daily_sales (list[int] or JSON string of list)
            - lead_time_days (int)
            - current_stock (int)
            - sku_id, category, unit_cost (optional, passed through)
        z_score: Service-level z-score.

    Returns:
        List of result dicts containing original fields plus forecast metrics.
    """
    results = []
    for record in sku_records:
        daily_sales = record.get("daily_sales", [])
        if isinstance(daily_sales, str):
            daily_sales = json.loads(daily_sales)

        lead_time = int(record.get("lead_time_days", DEFAULT_LEAD_TIME_DAYS))
        current_stock = int(record.get("current_stock", 0))

        metrics = forecast_single(daily_sales, lead_time, current_stock, z_score)

        result = {
            "sku_id": record.get("sku_id", ""),
            "category": record.get("category", ""),
            "current_stock": current_stock,
            "lead_time_days": lead_time,
            "unit_cost": record.get("unit_cost", 0.0),
        }
        result.update(metrics)
        results.append(result)

    return results
