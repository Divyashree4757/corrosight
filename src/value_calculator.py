"""Illustrative business-value calculator.

All inputs and outputs are HYPOTHETICAL. The review-time reduction is an assumption that would have
to be measured in a real pilot. No customers, revenue or validated savings are implied.

    Estimated annual savings = items x hours per item x hourly cost x assumed reduction fraction
    Illustrative net value   = estimated annual savings - annual software fee
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueInputs:
    annual_items: float
    hours_per_item: float
    hourly_cost: float
    reduction_fraction: float  # 0..1
    annual_fee: float


@dataclass(frozen=True)
class ValueResult:
    baseline_hours: float
    hours_saved: float
    estimated_savings: float
    net_value: float
    breakeven_reduction_fraction: float | None


def calculate(inp: ValueInputs) -> ValueResult:
    for name in ("annual_items", "hours_per_item", "hourly_cost", "annual_fee"):
        if getattr(inp, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    if not 0 <= inp.reduction_fraction <= 1:
        raise ValueError("reduction_fraction must be between 0 and 1")
    baseline_hours = inp.annual_items * inp.hours_per_item
    hours_saved = baseline_hours * inp.reduction_fraction
    savings = hours_saved * inp.hourly_cost
    labour_cost = baseline_hours * inp.hourly_cost
    breakeven = inp.annual_fee / labour_cost if labour_cost > 0 else None
    return ValueResult(baseline_hours, hours_saved, savings, savings - inp.annual_fee,
                       breakeven if breakeven is None or breakeven <= 1 else None)
