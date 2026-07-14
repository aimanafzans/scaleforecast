"""
Dataset management utilities for ScaleForecast.

Handles listing generated datasets in the ``data/`` directory and provides
safe single / bulk deletion with optional report-reference safeguards.

All paths are sourced from :mod:`scaleforecast.config` (no more per-function
``os.path.join(os.path.dirname(os.path.abspath(__file__)), ...)`` duplication).
All deletion entry points validate the supplied filename via
:func:`scaleforecast.config.validate_filename` to reject path-traversal
attacks such as ``"../sensitive_file.csv"``.

Public API (kept stable for callers):

    list_datasets(data_dir=None) -> list[DatasetInfo]
    delete_dataset(dataset_selection, data_dir=None, reports_dir=None) -> tuple[bool, str]

Each :class:`DatasetInfo` is a small dataclass that also exposes
:meth:`as_dict` for legacy dict-style access during the transition.
"""

from __future__ import annotations

import csv
import os
from typing import Optional, Union

from scaleforecast import config
from scaleforecast.constants import (
    DATASET_FILENAME_PREFIX,
    DATASET_FILENAME_SUFFIX,
    REPORT_FILENAME_SUFFIX,
)
from scaleforecast.data_generator import get_dataset_info, extract_timestamp_from_filename
from scaleforecast.models import DatasetInfo


def list_datasets(data_dir: Optional[Union[str, os.PathLike]] = None) -> list[DatasetInfo]:
    """
    List all generated SKU dataset files in the data directory.

    Args:
        data_dir: Path to the data directory. Defaults to :data:`config.DATA_DIR`.

    Returns:
        List of :class:`DatasetInfo` (newest-first, sorted by timestamp
        extracted from filename).
    """
    if data_dir is None:
        data_dir = str(config.DATA_DIR)

    if not os.path.isdir(data_dir):
        return []

    datasets: list[DatasetInfo] = []
    for entry in sorted(os.listdir(data_dir), key=extract_timestamp_from_filename, reverse=True):
        if not entry.startswith(DATASET_FILENAME_PREFIX) or not entry.endswith(DATASET_FILENAME_SUFFIX):
            continue
        filepath = os.path.join(data_dir, entry)
        if not os.path.isfile(filepath):
            continue
        info = get_dataset_info(filepath)
        timestamp = extract_timestamp_from_filename(entry)
        datasets.append(
            DatasetInfo(
                filename=info["filename"],
                sku_count=info["sku_count"],
                timestamp=timestamp,
                file_size_mb=info["file_size_mb"],
                filepath=info["filepath"],
            )
        )
    return datasets


def _find_referencing_reports(dataset_filename: str, reports_dir: str) -> list[str]:
    """
    Find report files that reference a given dataset filename.

    Checks the first data row of each CSV report for a ``source_dataset``
    column matching *dataset_filename*.  Returns a list of referencing
    report filenames.
    """
    referencing: list[str] = []
    if not os.path.isdir(reports_dir):
        return referencing
    for entry in os.listdir(reports_dir):
        if not entry.endswith(REPORT_FILENAME_SUFFIX):
            continue
        filepath = os.path.join(reports_dir, entry)
        try:
            with open(filepath, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                if "source_dataset" in header:
                    idx = header.index("source_dataset")
                    row = next(reader, None)
                    if row and len(row) > idx and row[idx] == dataset_filename:
                        referencing.append(entry)
        except (StopIteration, csv.Error, OSError):
            continue
    return referencing


def delete_dataset(
    dataset_selection: str,
    data_dir: Optional[Union[str, os.PathLike]] = None,
    reports_dir: Optional[Union[str, os.PathLike]] = None,
) -> tuple[bool, str]:
    """
    Delete one or all datasets, with optional safeguard against deleting
    datasets referenced by existing reports.

    Args:
        dataset_selection: Either ``"ALL"`` to delete every dataset, or a
            bare filename (e.g. ``"sku_dataset_1000000_20260708_1421.csv"``)
            to delete a single file. Bare filenames are validated via
            :func:`config.validate_filename` to reject path-traversal.
        data_dir: Path to the data directory. Defaults to :data:`config.DATA_DIR`.
        reports_dir: Path to the reports directory for reference checking.
            Defaults to :data:`config.REPORTS_DIR`.

    Returns:
        ``(success: bool, message: str)``
    """
    if data_dir is None:
        data_dir = str(config.DATA_DIR)
    if reports_dir is None:
        reports_dir = str(config.REPORTS_DIR)

    if not os.path.isdir(data_dir):
        return False, "Data directory does not exist."

    if dataset_selection.upper() == "ALL":
        datasets = os.listdir(data_dir)
        deleted = 0
        blocked = 0
        for filename in datasets:
            if not filename.startswith(DATASET_FILENAME_PREFIX) or not filename.endswith(DATASET_FILENAME_SUFFIX):
                continue
            filepath = os.path.join(data_dir, filename)
            refs = _find_referencing_reports(filename, reports_dir)
            if refs:
                blocked += 1
                continue
            try:
                os.remove(filepath)
                deleted += 1
            except OSError as e:
                return False, f"Failed to delete {filename}: {e}"
        msg = f"Deleted {deleted} dataset(s)."
        if blocked:
            msg += f" {blocked} dataset(s) skipped (referenced by existing reports)."
        return True, msg

    # Single-file deletion: validate the supplied filename BEFORE joining
    # it onto the managed directory to prevent path traversal.
    try:
        config.validate_filename(dataset_selection)
    except config.InvalidFilenameError as e:
        return False, str(e)

    filepath = os.path.join(data_dir, dataset_selection)
    if not os.path.isfile(filepath):
        return False, f"Dataset '{dataset_selection}' not found."

    refs = _find_referencing_reports(dataset_selection, reports_dir)
    if refs:
        return False, (
            f"Cannot delete '{dataset_selection}': it is referenced by "
            f"report(s): {', '.join(refs)}. Delete those reports first."
        )

    try:
        os.remove(filepath)
        return True, f"Deleted '{dataset_selection}'."
    except OSError as e:
        return False, f"Failed to delete '{dataset_selection}': {e}"


if __name__ == "__main__":
    # Smoke test: list datasets in data/
    datasets = list_datasets()
    if not datasets:
        print("No datasets found in data/ directory.")
    else:
        for ds in datasets:
            print(f"{ds.filename} | {ds.sku_count} SKUs | {ds.timestamp} | {ds.file_size_mb} MB")