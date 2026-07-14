"""
Typed schemas for ScaleForecast.

Dataclasses and enums used by the CLI, data manager, report generator,
and benchmark charting.  All use plain attribute access
(e.g. ``ds.filename`` instead of ``ds["filename"]``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """Stockout-risk classification."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class DatasetInfo:
    """Metadata about a generated dataset CSV file."""

    filename: str
    sku_count: int
    timestamp: str
    file_size_mb: float
    filepath: str


@dataclass
class ReportInfo:
    """Metadata about a generated forecast report CSV."""

    filename: str
    filepath: str
    source_dataset: str
    technique: str
    date: str
    sku_count: int
    at_risk_count: int


@dataclass
class TechniqueInfo:
    """Availability and display label for an execution technique."""

    key: str
    label: str
    available: bool
    unavailable_reason: str = ""


__all__ = [
    "RiskLevel",
    "DatasetInfo",
    "ReportInfo",
    "TechniqueInfo",
]
