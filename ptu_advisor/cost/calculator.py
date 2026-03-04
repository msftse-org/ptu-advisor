"""Cost calculation and break-even analysis for PTU vs PAYG pricing.

Extracted from ptu_advisor/dashboard/app.py to separate business logic
from UI presentation. Contains all cost-related computations:
- Spillover cost calculation (PTU baseline + PAYG overflow)
- Break-even analysis (where PTU becomes cheaper than PAYG)
- Cost curve generation for charting
- PTU sizing calculations
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd


def calculate_spillover_cost(
    tpm_values: List[float],
    baseline_percentile: float,
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_rate_per_1k: float,
    reservation_discount: float = 0.0,
    baseline_ptu_override: Optional[int] = None,
    min_ptu: int = 15,
    ptu_increment: int = 5,
) -> Dict[str, Any]:
    """
    Calculate optimal PTU + spillover (PAYG overflow) cost.

    Based on Azure Foundry spillover strategy:
    - Size PTU to cover baseline (not peak)
    - Overflow traffic spills to standard (PAYG) deployment
    - Total cost = PTU baseline + PAYG spillover

    Reference:
        https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management

    Args:
        tpm_values: Raw TPM values from metrics.
        baseline_percentile: Percentile to use as baseline (e.g., 50 for P50).
        ptu_capacity_per_unit: TPM capacity per PTU unit.
        ptu_hourly_rate: Hourly cost per PTU.
        payg_rate_per_1k: PAYG rate per 1K tokens.
        reservation_discount: Discount factor (0.307 for 1-yr, 0.361 for monthly, 1.0 for hourly).
        baseline_ptu_override: If set, use this exact PTU count instead of computing
            from baseline_percentile. The slider sends PTU units directly.
        min_ptu: Minimum PTU units for the deployment type.
        ptu_increment: PTU step size for the deployment type.

    Returns:
        Dict with baseline PTU, spillover tokens, costs breakdown.
    """
    empty = {
        "baseline_tpm": 0,
        "peak_tpm": 0,
        "baseline_ptu": min_ptu,
        "ptu_capacity_tpm": min_ptu * ptu_capacity_per_unit,
        "spillover_tokens_monthly": 0,
        "avg_spillover_tpm": 0,
        "ptu_monthly_full": 0,
        "ptu_monthly_cost": 0,
        "spillover_cost": 0,
        "total_hybrid_cost": 0,
        "spillover_pct": 0,
    }

    if not tpm_values or len(tpm_values) == 0:
        return empty

    peak_tpm = float(np.percentile(tpm_values, 95))

    if baseline_ptu_override is not None:
        # Slider sends PTU units directly — skip percentile lookup
        baseline_ptu = max(min_ptu, int(
            np.ceil(baseline_ptu_override / ptu_increment) * ptu_increment
        ))
        baseline_tpm = baseline_ptu * ptu_capacity_per_unit
    elif baseline_percentile == 0:
        baseline_ptu = min_ptu
        baseline_tpm = baseline_ptu * ptu_capacity_per_unit
    else:
        baseline_tpm = float(np.percentile(tpm_values, baseline_percentile))
        ptu_raw = baseline_tpm / ptu_capacity_per_unit
        baseline_ptu = max(min_ptu, int(
            np.ceil(ptu_raw / ptu_increment) * ptu_increment
        ))

    ptu_capacity_tpm = baseline_ptu * ptu_capacity_per_unit

    spillover_tokens_per_minute = [
        max(0.0, tpm - ptu_capacity_tpm) for tpm in tpm_values
    ]

    avg_spillover_tpm = float(np.mean(spillover_tokens_per_minute))
    spillover_tokens_monthly = avg_spillover_tpm * 60 * 24 * 30

    spillover_minutes = sum(1 for t in spillover_tokens_per_minute if t > 0)
    spillover_pct = (spillover_minutes / len(tpm_values)) * 100 if tpm_values else 0

    hours_per_month = 24 * 30  # 720
    ptu_monthly_full = baseline_ptu * ptu_hourly_rate * hours_per_month

    ptu_monthly_cost = (
        ptu_monthly_full * reservation_discount
        if reservation_discount > 0
        else ptu_monthly_full
    )

    spillover_cost = (spillover_tokens_monthly / 1000) * payg_rate_per_1k

    return {
        "baseline_tpm": baseline_tpm,
        "peak_tpm": peak_tpm,
        "baseline_ptu": baseline_ptu,
        "ptu_capacity_tpm": ptu_capacity_tpm,
        "spillover_tokens_monthly": spillover_tokens_monthly,
        "avg_spillover_tpm": avg_spillover_tpm,
        "ptu_monthly_full": ptu_monthly_full,
        "ptu_monthly_cost": ptu_monthly_cost,
        "spillover_cost": spillover_cost,
        "total_hybrid_cost": ptu_monthly_cost + spillover_cost,
        "spillover_pct": spillover_pct,
    }


def calculate_break_even(
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,
    reservation_discount: float = 1.0,
    min_ptu: int = 15,
    ptu_increment: int = 5,
    max_search_tpm: float = 200_000,
) -> Optional[float]:
    """
    Find the sustained TPM where PTU monthly cost equals PAYG monthly cost.

    PAYG cost  = tpm x 43,200 / 1M x blended_rate
    PTU cost   = ceil_to_increment(tpm / capacity_per_ptu) x hourly x 720 x discount

    Returns the break-even TPM, or ``None`` if the lines don't cross.
    """
    minutes_per_month = 60 * 24 * 30  # 43,200
    hours_per_month = 24 * 30  # 720
    step = max(50, max_search_tpm / 2000)

    prev_diff: Optional[float] = None
    prev_tpm = 0.0

    for tpm_i in np.arange(step, max_search_tpm, step):
        payg_cost = tpm_i * minutes_per_month / 1_000_000 * payg_blended_rate

        ptu_units_raw = tpm_i / ptu_capacity_per_unit
        ptu_units = max(min_ptu, int(np.ceil(ptu_units_raw / ptu_increment) * ptu_increment))

        discount = reservation_discount if reservation_discount < 1.0 else 1.0
        ptu_cost = ptu_units * ptu_hourly_rate * hours_per_month * discount

        diff = payg_cost - ptu_cost  # positive = PAYG more expensive

        if prev_diff is not None and prev_diff < 0 and diff >= 0:
            ratio = abs(prev_diff) / (abs(prev_diff) + abs(diff))
            return prev_tpm + ratio * step

        prev_diff = diff
        prev_tpm = float(tpm_i)

    return None


def generate_cost_curves(
    tpm_values: List[float],
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,
    payg_rate_per_1k: float,
    reservation_discount: float = 1.0,
    min_ptu: int = 15,
    ptu_increment: int = 5,
    include_tpm: float = 0.0,
) -> pd.DataFrame:
    """
    Generate PAYG and PTU+Spillover cost curves for break-even charting.

    For each sample baseline TPM, computes:
    - PAYG: cost if ALL traffic at that sustained TPM went through PAYG.
    - PTU+Spillover: PTU sized to that baseline, spillover from actual traffic.

    Returns:
        DataFrame with columns: baseline_tpm, payg_monthly, ptu_spill_monthly, ptu_units.
    """
    minutes_per_month = 60 * 24 * 30
    hours_per_month = 24 * 30

    if not tpm_values:
        return pd.DataFrame(
            columns=["baseline_tpm", "payg_monthly", "ptu_spill_monthly", "ptu_units"]
        )

    max_tpm = float(np.percentile(tpm_values, 99)) * 1.3
    if include_tpm > 0:
        max_tpm = max(max_tpm, include_tpm * 1.2)
    sample_points = np.linspace(0, max_tpm, 150)
    discount = reservation_discount if reservation_discount < 1.0 else 1.0

    rows: list[dict] = []
    for baseline in sample_points:
        payg = baseline * minutes_per_month / 1_000_000 * payg_blended_rate

        if baseline <= 0:
            ptu_units = min_ptu
        else:
            ptu_units = max(
                min_ptu,
                int(np.ceil(baseline / ptu_capacity_per_unit / ptu_increment) * ptu_increment),
            )

        ptu_fixed = ptu_units * ptu_hourly_rate * hours_per_month * discount

        ptu_cap = ptu_units * ptu_capacity_per_unit
        overflows = [max(0.0, v - ptu_cap) for v in tpm_values]
        avg_overflow_tpm = float(np.mean(overflows))
        spill_cost = avg_overflow_tpm * minutes_per_month / 1_000_000 * payg_blended_rate

        rows.append(
            {
                "baseline_tpm": baseline,
                "payg_monthly": payg,
                "ptu_spill_monthly": ptu_fixed + spill_cost,
                "ptu_units": ptu_units,
            }
        )

    return pd.DataFrame(rows)


def calculate_ptu_costs(
    peak_tpm: float,
    model: str,
    completion_ratio: float = 0.4,
) -> Dict[str, Any]:
    """Calculate PTU sizing and costs for a given model."""
    ptu_configs = {
        "gpt-5": {"tpm_per_ptu": 3400, "output_ratio": 8, "global_min": 15, "regional_min": 50},
        "gpt-4.1": {"tpm_per_ptu": 4750, "output_ratio": 4, "global_min": 15, "regional_min": 50},
        "gpt-4o": {"tpm_per_ptu": 2500, "output_ratio": 3, "global_min": 15, "regional_min": 50},
        "gpt-4o-mini": {"tpm_per_ptu": 37000, "output_ratio": 3, "global_min": 15, "regional_min": 25},
        "gpt-3.5-turbo": {"tpm_per_ptu": 37000, "output_ratio": 3, "global_min": 15, "regional_min": 25},
    }

    config = ptu_configs.get(model.lower(), ptu_configs["gpt-4o"])

    prompt_ratio = 1 - completion_ratio
    effective_multiplier = prompt_ratio + (completion_ratio * config["output_ratio"])

    safety_margin = 1.2
    raw_ptu = (peak_tpm * effective_multiplier * safety_margin) / config["tpm_per_ptu"]

    global_ptu = max(config["global_min"], int((raw_ptu // 5 + 1) * 5))
    regional_ptu = max(config["regional_min"], int((raw_ptu // 50 + 1) * 50))

    global_hourly = 2.00
    regional_hourly = 1.50
    reservation_discount = 0.35

    return {
        "raw_ptu": raw_ptu,
        "global_ptu": global_ptu,
        "regional_ptu": regional_ptu,
        "global_monthly": global_ptu * global_hourly * 730,
        "global_reserved": global_ptu * global_hourly * 730 * reservation_discount,
        "regional_monthly": regional_ptu * regional_hourly * 730,
        "regional_reserved": regional_ptu * regional_hourly * 730 * reservation_discount,
        "tpm_per_ptu": config["tpm_per_ptu"],
    }
