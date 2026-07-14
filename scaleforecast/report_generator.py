"""
Forecast report generator for ScaleForecast.

Generates timestamped CSV reports from forecast output and provides
list / delete / category-summary / at-risk / restock filtering utilities.
CSV columns use fixed decimal precision (2dp for monetary values, 4dp for
volatility) to keep the on-disk format stable.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional, Union

import pandas as pd

from scaleforecast import config
from scaleforecast.constants import (
    REPORT_FILENAME_PREFIX,
    REPORT_FILENAME_SUFFIX,
    REPORT_TIMESTAMP_FORMAT,
    RISK_SEVERITY_ORDER,
    AT_RISK_LEVELS,
    REPORT_COLUMN_ROUND_2DP,
    REPORT_COLUMN_ROUND_4DP,
)
from scaleforecast.models import ReportInfo, RiskLevel


def generate_report(
    forecast_results: list[dict[str, Any]],
    dataset_name: str,
    technique_label: str,
    output_dir: Optional[Union[str, os.PathLike]] = None,
) -> str:
    """
    Generate a forecast report CSV from forecast results.

    Args:
        forecast_results: List of forecast result dicts (output of forecast_skus).
        dataset_name: Name of the source dataset (e.g. filename).
        technique_label: Label of the execution technique used.
        output_dir: Directory for report files. Defaults to
            :data:`config.REPORTS_DIR`.

    Returns:
        Absolute path to the generated report CSV file.
    """
    if output_dir is None:
        output_dir = str(config.REPORTS_DIR)
    config.ensure_dir(output_dir)

    now = datetime.now()
    timestamp = now.strftime(REPORT_TIMESTAMP_FORMAT)
    filename = f"{REPORT_FILENAME_PREFIX}{timestamp}{REPORT_FILENAME_SUFFIX}"
    filepath = os.path.join(output_dir, filename)

    df = pd.DataFrame(forecast_results)

    df.insert(0, "source_dataset", dataset_name)
    df.insert(1, "technique", technique_label)
    df.insert(2, "report_generated", now.isoformat())

    column_order = [
        "source_dataset", "technique", "report_generated",
        "sku_id", "category", "current_stock", "lead_time_days",
        "unit_cost", "avg_daily_demand", "ma_7day", "ma_30day",
        "volatility", "demand_std", "safety_stock", "reorder_point",
        "stockout_risk", "recommended_order_qty",
    ]
    df = df[[c for c in column_order if c in df.columns]]

    # The forecast engine returns full-precision floats; rounding is applied
    # ONLY here, at the CSV boundary, to keep the on-disk format identical to
    # the legacy 2dp / 4dp precision. Volatility keeps its 4dp convention.
    for col in REPORT_COLUMN_ROUND_2DP:
        if col in df.columns:
            df[col] = df[col].astype(float).round(2)
    for col in REPORT_COLUMN_ROUND_4DP:
        if col in df.columns:
            df[col] = df[col].astype(float).round(4)

    df.to_csv(filepath, index=False)
    return filepath


def category_summary(forecast_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Compute category-level demand trend summary from forecast results.

    Returns a list of dicts with per-category aggregated metrics, or ``[]``
    if the input is empty or lacks the minimum required columns
    (``category`` plus the metric columns the aggregator depends on).
    """
    df = pd.DataFrame(forecast_results)
    if df.empty or "category" not in df.columns:
        return []

    # Defensive column check: groupby + named aggregations raise KeyError
    # if any referenced column is entirely missing. Fail soft -> []
    # rather than crash the CLI on a malformed / partial result set.
    required = (
        "category", "sku_id", "current_stock", "avg_daily_demand",
        "volatility", "reorder_point", "stockout_risk", "recommended_order_qty",
    )
    if not all(c in df.columns for c in required):
        missing = [c for c in required if c not in df.columns]
        import sys
        print(
            f"[report_generator] WARNING: category_summary skipped because "
            f"required columns are missing: {missing}",
            file=sys.stderr,
        )
        return []

    summary = df.groupby("category").agg(
        sku_count=("sku_id", "count"),
        total_current_stock=("current_stock", "sum"),
        avg_daily_demand=("avg_daily_demand", "mean"),
        avg_volatility=("volatility", "mean"),
        avg_reorder_point=("reorder_point", "mean"),
        at_risk_count=(
            "stockout_risk",
            lambda x: x.isin([RiskLevel.HIGH, RiskLevel.CRITICAL]).sum(),
        ),
        total_recommended_order=("recommended_order_qty", "sum"),
    ).reset_index()

    for col in ["avg_daily_demand", "avg_volatility", "avg_reorder_point"]:
        summary[col] = summary[col].round(2)

    return summary.to_dict("records")


def at_risk_skus(
    forecast_results: list[dict[str, Any]],
    sort_by_severity: bool = True,
) -> list[dict[str, Any]]:
    """
    Return only SKUs flagged as Medium, High, or Critical stockout risk,
    optionally sorted by severity (Critical > High > Medium).
    """
    at_risk = [
        r for r in forecast_results
        if r.get("stockout_risk") in AT_RISK_LEVELS
    ]
    if sort_by_severity:
        at_risk.sort(key=lambda r: RISK_SEVERITY_ORDER.get(r.get("stockout_risk", ""), 99))
    return at_risk


def restock_recommendations(
    forecast_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return SKUs that have a non-zero recommended_order_qty (i.e., need restock).
    """
    return [r for r in forecast_results if r.get("recommended_order_qty", 0) > 0]


def list_reports_with_skipped(
    reports_dir: Optional[Union[str, os.PathLike]] = None,
) -> tuple[list[ReportInfo], list[tuple[str, str]]]:
    """
    List generated forecast reports with full error visibility.

    Returns a ``(reports, skipped_files)`` tuple where:

      - ``reports`` is a list of :class:`ReportInfo`, newest-first.
      - ``skipped_files`` is a list of ``(filename, reason)`` tuples for
        every file that could not be read (corrupt CSV, missing columns,
        IO error).  Callers SHOULD surface these to the user rather than
        silently dropping them.

    Use this from any code path that wants to report unreadable files
    (e.g. the Phase 3 CLI).  :func:`list_reports` remains available for
    callers that only need the list and tolerate dropped files.
    """
    if reports_dir is None:
        reports_dir = str(config.REPORTS_DIR)
    if not os.path.isdir(reports_dir):
        return [], []

    reports: list[ReportInfo] = []
    skipped: list[tuple[str, str]] = []
    for entry in sorted(os.listdir(reports_dir), reverse=True):
        if not entry.startswith(REPORT_FILENAME_PREFIX) or not entry.endswith(REPORT_FILENAME_SUFFIX):
            continue
        filepath = os.path.join(reports_dir, entry)
        try:
            df = pd.read_csv(filepath)
            at_risk = 0
            if "stockout_risk" in df.columns:
                at_risk = int((df["stockout_risk"].isin([RiskLevel.HIGH, RiskLevel.CRITICAL])).sum())
            reports.append(
                ReportInfo(
                    filename=entry,
                    filepath=filepath,
                    source_dataset=(
                        df["source_dataset"].iloc[0]
                        if "source_dataset" in df.columns else "Unknown"
                    ),
                    technique=(
                        df["technique"].iloc[0]
                        if "technique" in df.columns else "Unknown"
                    ),
                    date=(
                        df["report_generated"].iloc[0]
                        if "report_generated" in df.columns else "Unknown"
                    ),
                    sku_count=len(df),
                    at_risk_count=at_risk,
                )
            )
        except Exception as exc:
            # No longer silent: record the failure so callers can surface it.
            skipped.append((entry, f"{type(exc).__name__}: {exc}"))
    return reports, skipped


def list_reports(reports_dir: Optional[Union[str, os.PathLike]] = None) -> list[ReportInfo]:
    """
    List all generated forecast reports with metadata.

    Returns a list of :class:`ReportInfo` dataclasses (newest-first). Use
    :meth:`ReportInfo.as_dict` for backward-compatible dict access.

    Unreadable / corrupt report files are skipped and a one-line warning
    per skipped file is written to stderr (so a missing report is visible
    rather than silently dropped).  Callers that want programmatic access
    to the skipped list should use :func:`list_reports_with_skipped`.
    """
    import sys

    reports, skipped = list_reports_with_skipped(reports_dir)
    for name, reason in skipped:
        print(
            f"[report_generator] WARNING: could not read report {name!r}: {reason}",
            file=sys.stderr,
        )
    return reports


def delete_report(filename: str, reports_dir: Optional[Union[str, os.PathLike]] = None) -> tuple[bool, str]:
    """Delete a single report file by filename."""
    if reports_dir is None:
        reports_dir = str(config.REPORTS_DIR)

    # Validate the filename BEFORE joining it to the managed directory to
    # prevent path traversal (e.g. "../sensitive_file").
    try:
        config.validate_filename(filename)
    except config.InvalidFilenameError as e:
        return False, str(e)

    filepath = os.path.join(reports_dir, filename)
    if not os.path.isfile(filepath):
        return False, f"Report '{filename}' not found."
    try:
        os.remove(filepath)
        return True, f"Deleted report '{filename}'."
    except OSError as e:
        return False, f"Failed to delete '{filename}': {e}"