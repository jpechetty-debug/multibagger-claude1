"""
Scoring — Normalization primitives and type definitions.

Sigmoid-based normalization replaces binary step cliffs with a smooth
continuous gradient for all factor scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union

import numpy as np

from modules.data_utils import optional_float

# Type aliases
_Number = Union[int, float]
_StockData = dict[str, Any]
_SectorMedians = dict[str, dict[str, float]]


@dataclass(frozen=True)
class FactorState:
    score_sales: float
    score_roe: float
    score_cfo: float
    score_val: float
    score_eps: float
    score_fscore: float
    score_de: float
    score_mom_combined: float
    score_sentiment: float
    sg_val: float
    roe_val: float
    best_roe: float
    pe: _Number | None
    peg: _Number | None
    price: float
    atr: float
    stock_sector: str
    prom_hold: float
    inst_hold: float


def normalize_metric(
    value: _Number | None,
    min_val: _Number,
    max_val: _Number,
    invert: bool = False,
) -> float:
    """
    Normalizes a metric to a 0-100 scale using a Sigmoid function.
    Replaces binary step cliffs with a smooth continuous gradient.
    """
    value = optional_float(value)
    if value is None:
        return 0.0

    mid = (min_val + max_val) / 2.0
    span = float(max_val - min_val)
    if span == 0:
        span = 1e-5

    # Scale so min_val is approx at x=-3 (4.7%) and max_val at x=+3 (95%)
    x_scaled = (value - mid) / (span / 6.0)

    # Cap exponent to avoid overflow warnings
    x_scaled = max(-100, min(100, x_scaled))

    sigmoid_val = 1.0 / (1.0 + np.exp(-x_scaled))

    if invert:
        return float((1.0 - sigmoid_val) * 100.0)
    else:
        return float(sigmoid_val * 100.0)


def calculate_sector_medians(results: list[_StockData]) -> _SectorMedians:
    """Compute median ROE, Sales Growth, PE per sector for relative scoring."""
    sector_data: dict[str, dict[str, list[float]]] = {}
    for stock in results:
        sector = stock.get("Sector", "Unknown")
        if sector == "Unknown":
            continue
        if sector not in sector_data:
            sector_data[sector] = {"roe": [], "growth": [], "pe": []}

        # Explicit None checks: 0 is a valid value that must be preserved.
        roe_5y = stock.get("Avg_ROE_5Y%")
        roe_current = stock.get("ROE%")
        roe = roe_5y if roe_5y is not None else (roe_current if roe_current is not None else None)

        growth_5y = stock.get("Sales_Growth_5Y%")
        growth_ttm = stock.get("Sales_Growth_TTM%")
        growth = growth_5y if growth_5y is not None else (growth_ttm if growth_ttm is not None else None)

        pe = stock.get("PE_Ratio")

        if roe is not None:
            sector_data[sector]["roe"].append(roe)
        if growth is not None:
            sector_data[sector]["growth"].append(growth)
        if pe is not None and pe > 0:
            sector_data[sector]["pe"].append(pe)

    medians = {}
    for sector, vals in sector_data.items():
        medians[sector] = {
            "median_roe": round(float(np.median(vals["roe"])), 1) if vals["roe"] else 15,
            "median_growth": round(float(np.median(vals["growth"])), 1) if vals["growth"] else 10,
            "median_pe": round(float(np.median(vals["pe"])), 1) if vals["pe"] else 20,
        }
    return medians
