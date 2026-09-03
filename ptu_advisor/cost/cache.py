"""Prompt-cache impact calculations shared by API, reports, and consolidation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from math import ceil, isfinite
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from ptu_advisor.metrics.models import TimeSeries, infer_cache_match_rate

CacheMode = Literal["auto", "disabled", "override"]
CacheSource = Literal[
    "observed", "inferred", "mixed", "override", "disabled", "unavailable"
]
CacheQuality = Literal["good", "partial", "limited", "unavailable"]


@dataclass(frozen=True)
class CacheImpact:
    """Cache-aware workload shape and sizing outputs."""

    timestamps: List[datetime]
    source: CacheSource
    quality: CacheQuality
    applied: bool
    coverage_pct: float
    match_rate_pct: List[Optional[float]]
    prompt_tokens: List[float]
    completion_tokens: List[float]
    cached_prompt_tokens: List[float]
    active_prompt_tokens: List[float]
    raw_normalized_tpm: List[float]
    adjusted_normalized_tpm: List[float]
    avg_match_rate_pct: float
    p95_match_rate_pct: float
    total_cached_prompt_tokens: float
    total_active_prompt_tokens: float
    no_cache_normalized_avg_tpm: float
    cache_adjusted_normalized_avg_tpm: float
    normalized_tpm_reduction_pct: float
    no_cache_recommended_ptu: int
    cache_aware_recommended_ptu: int
    ptu_avoided: int
    active_tokens_observed: float
    validation_warnings: List[str]


def _round_ptu(value: float, minimum: int, increment: int) -> int:
    increment = max(1, increment)
    return max(minimum, int(ceil(value / increment) * increment))


def _quality(coverage_pct: float) -> CacheQuality:
    if coverage_pct >= 80:
        return "good"
    if coverage_pct >= 50:
        return "partial"
    if coverage_pct > 0:
        return "limited"
    return "unavailable"


def build_cache_impact(
    *,
    prompt_tokens: Optional[TimeSeries],
    completion_tokens: Optional[TimeSeries],
    cache_match_rate: Optional[TimeSeries],
    active_tokens: Optional[TimeSeries],
    output_multiplier: int,
    input_tpm_per_ptu: float,
    min_ptu: int,
    ptu_increment: int,
    cache_mode: CacheMode = "auto",
    override_pct: Optional[float] = None,
    interval_minutes: int = 1,
    coverage_pct_override: Optional[float] = None,
    source_override: Optional[CacheSource] = None,
    missing_evidence_as_zero: bool = False,
) -> CacheImpact:
    """Build cache-aware normalized throughput and rounded PTU estimates.

    Missing cache intervals are displayed as gaps and receive zero benefit in
    calculations. Cache data below 50% coverage is contextual only and does not
    modify the primary workload calculation.
    """
    if cache_mode not in ("auto", "disabled", "override"):
        raise ValueError("cache_mode must be auto, disabled, or override")
    if cache_mode == "override":
        if override_pct is None:
            raise ValueError("override_pct is required when cache_mode is override")
        if not 0 <= override_pct <= 100:
            raise ValueError("override_pct must be between 0 and 100")

    interval_minutes = max(1, interval_minutes)
    timestamps = list(prompt_tokens.timestamps) if prompt_tokens else []
    prompts = [float(value) for value in prompt_tokens.values] if prompt_tokens else []
    has_complete_shape = bool(
        prompt_tokens
        and completion_tokens
        and prompt_tokens.timestamps == completion_tokens.timestamps
        and len(prompt_tokens.values) == len(completion_tokens.values)
    )
    completions = (
        [float(value) for value in completion_tokens.values]
        if has_complete_shape and completion_tokens
        else []
    )

    direct_lookup = (
        dict(zip(cache_match_rate.timestamps, cache_match_rate.values)) if cache_match_rate else {}
    )
    active_lookup = dict(zip(active_tokens.timestamps, active_tokens.values)) if active_tokens else {}

    source: CacheSource
    ratios: List[Optional[float]] = []
    valid_count = 0
    validation_warnings: List[str] = []

    if cache_mode == "disabled":
        source = "disabled"
        ratios = [0.0 for _ in timestamps]
    elif cache_mode == "override":
        source = "override"
        ratio = float(override_pct or 0.0) / 100.0
        ratios = [ratio for _ in timestamps]
        valid_count = len(timestamps)
    elif direct_lookup:
        used_inferred = False
        for index, (ts, prompt) in enumerate(zip(timestamps, prompts)):
            direct_value = direct_lookup.get(ts)
            inferred_value = None
            active_value = active_lookup.get(ts)
            if active_value is not None and has_complete_shape:
                inferred_value = infer_cache_match_rate(
                    prompt,
                    completions[index],
                    float(active_value),
                )
            if direct_value is not None and 0 <= float(direct_value) <= 1:
                ratio = float(direct_value)
                ratios.append(ratio)
                valid_count += 1
                if inferred_value is not None and abs(ratio - inferred_value) > 0.05:
                    validation_warnings.append(
                        f"Direct cache rate and ActiveTokens disagreed at {ts.isoformat()} "
                        f"({ratio * 100:.1f}% vs {inferred_value * 100:.1f}%); direct telemetry was used."
                    )
            elif inferred_value is not None:
                ratios.append(inferred_value)
                valid_count += 1
                used_inferred = True
            else:
                ratios.append(None)
        source = "mixed" if used_inferred else "observed"
    elif active_lookup:
        source = "inferred"
        for index, (ts, prompt) in enumerate(zip(timestamps, prompts)):
            value = active_lookup.get(ts)
            if value is None or not has_complete_shape:
                ratios.append(None)
                continue
            completion = completions[index]
            inferred_ratio = infer_cache_match_rate(prompt, completion, float(value))
            if inferred_ratio is None:
                ratios.append(None)
                continue
            ratios.append(inferred_ratio)
            valid_count += 1
        if valid_count == 0:
            source = "unavailable"
    else:
        source = "unavailable"
        ratios = [None for _ in timestamps]

    if source_override is not None and cache_mode == "auto":
        source = source_override

    measured_coverage_pct = (valid_count / len(timestamps) * 100.0) if timestamps else 0.0
    coverage_pct = (
        min(measured_coverage_pct, max(0.0, min(100.0, coverage_pct_override)))
        if coverage_pct_override is not None
        else measured_coverage_pct
    )
    if source in ("override",):
        quality: CacheQuality = "good" if timestamps else "unavailable"
    elif source in ("disabled", "unavailable"):
        quality = "unavailable"
    else:
        quality = _quality(coverage_pct)

    applied = has_complete_shape and (
        source == "override"
        or (
            source in ("observed", "inferred", "mixed")
            and (quality in ("good", "partial") or missing_evidence_as_zero)
        )
    )

    raw_normalized = (
        [
            prompt + completion * output_multiplier
            for prompt, completion in zip(prompts, completions)
        ]
        if has_complete_shape
        else []
    )
    cached_prompt = [
        prompt * ratio if ratio is not None else 0.0
        for prompt, ratio in zip(prompts, ratios)
    ]
    observed_active_prompt = [
        prompt - cached for prompt, cached in zip(prompts, cached_prompt)
    ]
    active_prompt = observed_active_prompt
    adjusted_candidate = (
        [
            active + completion * output_multiplier
            for active, completion in zip(active_prompt, completions)
        ]
        if has_complete_shape
        else []
    )
    adjusted_normalized = adjusted_candidate if applied else list(raw_normalized)

    valid_rates_pct = [ratio * 100.0 for ratio in ratios if ratio is not None]
    total_prompt = float(sum(prompts))
    unscaled_cached = float(sum(cached_prompt))
    total_cached = unscaled_cached * interval_minutes
    avg_rate = unscaled_cached / total_prompt * 100.0 if total_prompt > 0 else 0.0
    p95_rate = float(np.percentile(valid_rates_pct, 95)) if valid_rates_pct else 0.0
    raw_avg = float(np.mean(raw_normalized)) if raw_normalized else 0.0
    adjusted_avg = float(np.mean(adjusted_normalized)) if adjusted_normalized else 0.0
    reduction_pct = ((raw_avg - adjusted_avg) / raw_avg * 100.0) if raw_avg > 0 else 0.0

    raw_p95 = float(np.percentile(raw_normalized, 95)) if raw_normalized else 0.0
    adjusted_p95 = (
        float(np.percentile(adjusted_normalized, 95)) if adjusted_normalized else 0.0
    )
    capacity = max(float(input_tpm_per_ptu), 1.0)
    no_cache_ptu = _round_ptu(raw_p95 / capacity, min_ptu, ptu_increment)
    cache_ptu = _round_ptu(adjusted_p95 / capacity, min_ptu, ptu_increment)

    active_observed = (
        sum(
            float(value)
            for value in active_tokens.values
            if isfinite(float(value)) and float(value) >= 0
        )
        * interval_minutes
        if active_tokens
        else 0.0
    )
    return CacheImpact(
        timestamps=timestamps,
        source=source,
        quality=quality,
        applied=applied,
        coverage_pct=coverage_pct,
        match_rate_pct=[ratio * 100.0 if ratio is not None else None for ratio in ratios],
        prompt_tokens=prompts,
        completion_tokens=completions,
        cached_prompt_tokens=cached_prompt,
        active_prompt_tokens=active_prompt,
        raw_normalized_tpm=raw_normalized,
        adjusted_normalized_tpm=adjusted_normalized,
        avg_match_rate_pct=avg_rate,
        p95_match_rate_pct=p95_rate,
        total_cached_prompt_tokens=total_cached,
        total_active_prompt_tokens=float(sum(active_prompt)) * interval_minutes,
        no_cache_normalized_avg_tpm=raw_avg,
        cache_adjusted_normalized_avg_tpm=adjusted_avg,
        normalized_tpm_reduction_pct=reduction_pct,
        no_cache_recommended_ptu=no_cache_ptu,
        cache_aware_recommended_ptu=cache_ptu,
        ptu_avoided=max(0, no_cache_ptu - cache_ptu),
        active_tokens_observed=active_observed,
        validation_warnings=validation_warnings,
    )


def calculate_cache_aware_spillover(
    *,
    impact: CacheImpact,
    selected_ptu: int,
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    reservation_discount: float,
    payg_input_rate_per_million: float,
    payg_output_rate_per_million: float,
) -> Dict[str, Any]:
    """Calculate fixed PTU plus conservatively priced PAYG spillover.

    Spillover receives no source-deployment cache discount because the target
    Standard deployment can have different cache locality.
    """
    capacity = selected_ptu * ptu_capacity_per_unit
    overflow_input: List[float] = []
    overflow_output: List[float] = []
    overflow_normalized: List[float] = []

    for normalized, completion in zip(
        impact.adjusted_normalized_tpm,
        impact.completion_tokens,
    ):
        index = len(overflow_normalized)
        # Spillover is conservatively priced uncached because a separate
        # Standard target deployment can have different cache locality.
        effective_active_prompt = impact.prompt_tokens[index]
        overflow = max(0.0, normalized - capacity)
        fraction = overflow / normalized if normalized > 0 else 0.0
        overflow_normalized.append(overflow)
        overflow_input.append(effective_active_prompt * fraction)
        overflow_output.append(completion * fraction)

    minutes_per_month = 43_200
    monthly_input = float(np.mean(overflow_input)) * minutes_per_month if overflow_input else 0.0
    monthly_output = (
        float(np.mean(overflow_output)) * minutes_per_month if overflow_output else 0.0
    )
    spillover_cost = (
        monthly_input / 1_000_000 * payg_input_rate_per_million
        + monthly_output / 1_000_000 * payg_output_rate_per_million
    )
    discount = reservation_discount if reservation_discount > 0 else 1.0
    ptu_monthly_cost = selected_ptu * ptu_hourly_rate * 720 * discount
    spillover_intervals = sum(1 for value in overflow_normalized if value > 0)

    return {
        "baseline_ptu": selected_ptu,
        "ptu_capacity_tpm": capacity,
        "ptu_monthly_cost": ptu_monthly_cost,
        "avg_spillover_normalized_tpm": float(np.mean(overflow_normalized))
        if overflow_normalized
        else 0.0,
        "spillover_input_tokens_monthly": monthly_input,
        "spillover_output_tokens_monthly": monthly_output,
        "spillover_tokens_monthly": monthly_input + monthly_output,
        "spillover_cost": spillover_cost,
        "total_hybrid_cost": ptu_monthly_cost + spillover_cost,
        "spillover_pct": (
            spillover_intervals / len(overflow_normalized) * 100.0
            if overflow_normalized
            else 0.0
        ),
    }


def generate_cache_aware_cost_curves(
    *,
    selected_ptu: int,
    ptu_capacity_raw_tpm: float,
    ptu_monthly_cost: float,
    payg_rate_per_raw_million: float,
    spillover_rate_per_raw_million: float,
    max_tpm: float,
    num_points: int = 200,
) -> tuple[pd.DataFrame, Optional[float], Optional[float]]:
    """Generate fixed-PTU curves when PAYG and spillover have distinct slopes."""
    rows: list[dict[str, float]] = []
    minutes_per_month = 43_200
    payg_slope = minutes_per_month / 1_000_000 * payg_rate_per_raw_million
    spillover_slope = minutes_per_month / 1_000_000 * spillover_rate_per_raw_million
    crossings: list[float] = []
    if payg_slope > 0:
        lower = ptu_monthly_cost / payg_slope
        if 0 <= lower <= ptu_capacity_raw_tpm:
            crossings.append(lower)
    slope_delta = payg_slope - spillover_slope
    if not math.isclose(payg_slope, spillover_slope, rel_tol=1e-9, abs_tol=1e-12):
        upper = (
            ptu_monthly_cost - spillover_slope * ptu_capacity_raw_tpm
        ) / slope_delta
        if ptu_capacity_raw_tpm < upper:
            crossings.append(upper)

    curve_max_tpm = max(max_tpm, max(crossings, default=0.0) * 1.05)
    sample_tpms = np.linspace(0, curve_max_tpm, num_points)

    for tpm in sample_tpms:
        payg = tpm * minutes_per_month / 1_000_000 * payg_rate_per_raw_million
        overflow_tpm = max(0.0, tpm - ptu_capacity_raw_tpm)
        hybrid = (
            ptu_monthly_cost
            + overflow_tpm
            * minutes_per_month
            / 1_000_000
            * spillover_rate_per_raw_million
        )
        rows.append(
            {
                "sustained_tpm": float(tpm),
                "payg_monthly": float(payg),
                "ptu_spill_monthly": float(hybrid),
            }
        )

    crossings.sort()
    lower_crossing = crossings[0] if crossings else None
    upper_crossing = crossings[1] if len(crossings) > 1 else None
    return pd.DataFrame(rows), lower_crossing, upper_crossing
