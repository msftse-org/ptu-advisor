from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ptu_advisor.analysis.engine import DecisionEngine
from ptu_advisor.auth import get_azure_credential
from ptu_advisor.config import AnalysisConfig, get_model_config
from ptu_advisor.cost.calculator import (
    calculate_break_even,
    calculate_spillover_cost,
    generate_cost_curves,
)
from ptu_advisor.cost.pricing import (
    DEPLOYMENT_TYPE_CONFIGS,
    REGION_CONFIGS,
    get_deployment_config,
    get_deployment_type,
    get_region_config,
    normalize_region,
)
from ptu_advisor.demo import DemoScenario, FOCUS_TOPICS, generate_demo_metrics
from ptu_advisor.discovery import list_ai_accounts, list_deployments, list_subscriptions
from ptu_advisor.metrics.collector import MetricsCollector
from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries


class AnalyzeRequest(BaseModel):
    mode: Literal["demo", "live"] = "live"
    focus_topic: str = "Cost Reduction"
    lookback_days: int = Field(default=14, ge=1, le=30)
    granularity_minutes: Literal[1, 5, 15, 30] = 5
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    workspace: Optional[str] = None
    deployment: Optional[str] = None
    reservation_type: Literal[
        "Hourly — No Commitment",
        "Monthly Commitment (Estimated 64% off)",
        "1-Year Commitment (Estimated 69% off)",
    ] = "Monthly Commitment (Estimated 64% off)"
    baseline_percentile: int = Field(default=75, ge=0, le=95)
    baseline_ptu: Optional[int] = Field(default=None, ge=0, description="PTU units for slider. When set, overrides baseline_percentile.")
    region: str = "eastus"
    deployment_type: Literal["global", "data_zone", "regional"] = "global"
    include_throttle: bool = False


class AnalyzeResponse(BaseModel):
    recommendation: str
    confidence: float
    summary: str
    explanation: str
    what_would_change: str
    data_quality: str
    analysis_period: str
    dimensions: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    charts: Dict[str, Any]
    cost_analysis: Dict[str, Any]
    insights: Dict[str, Any]


def _series_payload(series: Optional[TimeSeries]) -> Dict[str, Any]:
    if not series:
        return {
            "timestamps": [],
            "values": [],
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std": 0.0,
            "total": 0.0,
        }
    return {
        "timestamps": [ts.isoformat() for ts in series.timestamps],
        "values": [float(v) for v in series.values],
        "mean": float(series.mean),
        "p50": float(series.p50),
        "p95": float(series.p95),
        "p99": float(series.p99),
        "min": float(series.min),
        "max": float(series.max),
        "std": float(series.std),
        "total": float(series.total),
    }


def _pricing_terms(reservation_type: str) -> Dict[str, Any]:
    if reservation_type == "1-Year Commitment (Estimated 69% off)":
        return {"discount_factor": 0.307, "discount_pct": 69}
    if reservation_type == "Monthly Commitment (Estimated 64% off)":
        return {"discount_factor": 0.361, "discount_pct": 64}
    return {"discount_factor": 1.0, "discount_pct": 0}


app = FastAPI(title="PTU Advisor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pick_demo_scenario(focus_topic: str) -> DemoScenario:
    options = FOCUS_TOPICS.get(focus_topic, {}).get("scenarios", {})
    if options:
        first = next(iter(options.keys()))
        if isinstance(first, DemoScenario):
            return first
    return DemoScenario.PTU_RECOMMENDED


def _filter_series_by_window(
    series: Optional[TimeSeries],
    start: Optional[datetime],
    end: Optional[datetime],
) -> Optional[TimeSeries]:
    if series is None or (start is None and end is None):
        return series

    filtered_timestamps: List[datetime] = []
    filtered_values: List[float] = []
    for ts, value in zip(series.timestamps, series.values):
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        filtered_timestamps.append(ts)
        filtered_values.append(value)

    if not filtered_timestamps:
        return None

    return TimeSeries(
        timestamps=filtered_timestamps,
        values=filtered_values,
        metric_name=series.metric_name,
        unit=series.unit,
    )


def _filter_metrics_by_window(
    metrics: DeploymentMetrics,
    start: Optional[datetime],
    end: Optional[datetime],
) -> DeploymentMetrics:
    if start is None and end is None:
        return metrics

    normalized_start = start
    normalized_end = end
    if normalized_start and normalized_end and normalized_start > normalized_end:
        normalized_start, normalized_end = normalized_end, normalized_start

    filtered = DeploymentMetrics(
        deployment_name=metrics.deployment_name,
        model_name=metrics.model_name,
        start_time=normalized_start or metrics.start_time,
        end_time=normalized_end or metrics.end_time,
        deployment_info=metrics.deployment_info,
    )

    for attr_name in [
        "requests_per_minute",
        "successful_requests",
        "throttled_requests",
        "prompt_tokens",
        "completion_tokens",
        "tokens_per_minute",
        "time_to_first_byte_p50",
        "time_to_first_byte_p95",
        "time_to_first_byte_p99",
        "ptu_utilization",
    ]:
        series = getattr(metrics, attr_name)
        setattr(filtered, attr_name, _filter_series_by_window(series, normalized_start, normalized_end))

    # Prefer token timestamps first, then request timestamps if tokens are unavailable.
    timeline = filtered.tokens_per_minute or filtered.requests_per_minute
    if timeline:
        filtered.timestamps = list(timeline.timestamps)
        if filtered.timestamps:
            filtered.start_time = filtered.timestamps[0]
            filtered.end_time = filtered.timestamps[-1]

    return filtered


def _aggregate_daily_costs(
    timestamps: List[str],
    prompt_values: List[float],
    completion_values: List[float],
    payg_input_rate: float,
    payg_output_rate: float,
) -> Dict[str, Any]:
    """Aggregate interval-level token data into daily cost bars."""
    from collections import defaultdict

    daily_input: Dict[str, float] = defaultdict(float)
    daily_output: Dict[str, float] = defaultdict(float)

    for ts, p_tok, c_tok in zip(timestamps, prompt_values, completion_values):
        day = ts[:10]  # "2026-03-01T14:00:00Z" -> "2026-03-01"
        daily_input[day] += p_tok
        daily_output[day] += c_tok

    dates = sorted(daily_input.keys())
    input_costs = [(daily_input[d] / 1_000_000) * payg_input_rate for d in dates]
    output_costs = [(daily_output[d] / 1_000_000) * payg_output_rate for d in dates]
    total_costs = [ic + oc for ic, oc in zip(input_costs, output_costs)]
    avg_daily = sum(total_costs) / len(total_costs) if total_costs else 0.0

    return {
        "dates": dates,
        "input_cost": [round(v, 2) for v in input_costs],
        "output_cost": [round(v, 2) for v in output_costs],
        "total_cost": [round(v, 2) for v in total_costs],
        "avg_daily_cost": round(avg_daily, 2),
    }


def _build_formula_blocks(
    *,
    avg_tpm: float,
    total_tokens: float,
    lookback_days: int,
    avg_daily_tokens: float,
    payg_input_rate: float,
    payg_output_rate: float,
    output_ratio: float,
    payg_blended_rate: float,
    payg_base: float,
    payg_total: float,
    throttle_rate: float,
    throttle_rate_pct: float,
    throttle_impact: float,
    include_throttle: bool,
    baseline_ptu: int,
    ptu_monthly_rate: float,
    ptu_baseline_cost: float,
    avg_spillover_tpm: float,
    spillover_cost: float,
    hybrid_total: float,
    effective_mult: float = 1.0,
    input_tpm_per_ptu: int = 2500,
    model_output_multiplier: int = 3,
) -> Dict[str, str]:
    """Build human-readable formula strings for PAYG and hybrid cost breakdowns."""
    avg_daily_overflow = avg_spillover_tpm * 1440  # tokens/day

    monthly_tokens = avg_daily_tokens * 30
    effective_capacity = input_tpm_per_ptu / effective_mult

    # ── PAYG block ──
    payg_lines = [
        f"avg_daily_tokens = {avg_tpm:,.0f} TPM × 1,440 min/day = {avg_daily_tokens:,.0f} tokens/day",
        f"monthly_tokens = {avg_daily_tokens:,.0f} × 30 days = {monthly_tokens:,.0f} tokens/month",
        f"blended_rate = ${payg_input_rate:.2f} × {(1-output_ratio)*100:.0f}% input + ${payg_output_rate:.2f} × {output_ratio*100:.0f}% output = ${payg_blended_rate:.2f}/1M tokens",
        f"payg_cost = {monthly_tokens:,.0f} ÷ 1M × ${payg_blended_rate:.2f} = ${payg_base:,.0f}/month",
    ]
    if include_throttle:
        payg_lines.append(f"throttle_rate = {throttle_rate_pct:.1f}%")
        payg_lines.append(f"throttle_impact = ${throttle_impact:,.0f}/month")
        payg_lines.append(
            f"total_payg = ${payg_base:,.0f} + ${throttle_impact:,.0f} = ${payg_total:,.0f}/month"
        )
    else:
        payg_lines.append(f"total_payg = ${payg_total:,.0f}/month")

    # ── Hybrid block ──
    monthly_overflow = avg_daily_overflow * 30
    hybrid_lines = [
        f"effective_mult = {(1-output_ratio)*100:.0f}% input + {output_ratio*100:.0f}% output × {model_output_multiplier} = {effective_mult:.2f}×",
        f"capacity_per_ptu = {input_tpm_per_ptu:,} ÷ {effective_mult:.2f} = {effective_capacity:,.0f} raw TPM/PTU",
        f"ptu_cost = {baseline_ptu} PTU × ${ptu_monthly_rate:,.2f}/PTU/month = ${ptu_baseline_cost:,.0f}/month",
    ]
    if avg_spillover_tpm > 0:
        hybrid_lines += [
            f"avg_daily_overflow = {avg_spillover_tpm:,.0f} TPM × 1,440 min = {avg_daily_overflow:,.0f} tokens/day",
            f"monthly_overflow = {avg_daily_overflow:,.0f} × 30 days = {monthly_overflow:,.0f} tokens/month",
            f"spillover_cost = {monthly_overflow:,.0f} ÷ 1M × ${payg_blended_rate:.2f} = ${spillover_cost:,.0f}/month",
            f"total_hybrid = ${ptu_baseline_cost:,.0f} + ${spillover_cost:,.0f} = ${hybrid_total:,.0f}/month",
        ]
    else:
        hybrid_lines += [
            f"spillover = none — all traffic fits within {baseline_ptu} PTU",
            f"total_hybrid = ${ptu_baseline_cost:,.0f}/month",
        ]

    return {"payg": "\n".join(payg_lines), "hybrid": "\n".join(hybrid_lines)}


def _serialize_analysis(
    metrics: DeploymentMetrics,
    analysis: Any,
    focus_topic: str,
    lookback_days: int,
    reservation_type: str,
    baseline_percentile: int,
    region: str,
    deployment_type: str,
    baseline_ptu: Optional[int] = None,
    include_throttle: bool = False,
) -> AnalyzeResponse:
    tpm = metrics.tokens_per_minute
    throttled = metrics.throttled_requests
    prompt = metrics.prompt_tokens
    completion = metrics.completion_tokens
    successful = metrics.successful_requests
    requests = metrics.requests_per_minute
    p50 = metrics.time_to_first_byte_p50
    p95 = metrics.time_to_first_byte_p95
    p99 = metrics.time_to_first_byte_p99

    lookback_days = max(1, lookback_days)
    avg_tpm = float(tpm.mean) if tpm else 0.0
    peak_tpm = float(tpm.p95) if tpm else 0.0
    throttle_rate_pct = float(metrics.throttling_rate * 100)

    # Derive daily token volume from TPM (the authoritative throughput rate)
    avg_daily_tokens = avg_tpm * 1440  # tokens per minute × minutes per day
    total_tokens = avg_daily_tokens * max(1, lookback_days)
    monthly_tokens = avg_daily_tokens * 30

    payg_input_rate = 2.50
    payg_output_rate = 10.0
    # Derive output ratio from actual prompt vs completion data
    prompt_total = float(prompt.total) if prompt else 0.0
    completion_total = float(completion.total) if completion else 0.0
    token_sum = prompt_total + completion_total
    output_ratio = (completion_total / token_sum) if token_sum > 0 else 0.30
    payg_blended_rate = (payg_input_rate * (1 - output_ratio)) + (payg_output_rate * output_ratio)
    payg_rate_per_1k = payg_blended_rate / 1000

    payg_base = (monthly_tokens / 1_000_000) * payg_blended_rate
    throttle_rate = float(metrics.throttling_rate)
    if throttle_rate > 0.01:
        retry_overhead = payg_base * (throttle_rate / max(0.0001, (1 - throttle_rate)))
        opportunity_multiplier = min(5.0, 1.0 + (throttle_rate * 20))
        throttle_impact = retry_overhead * opportunity_multiplier
    else:
        throttle_impact = 0.0
    payg_total = (payg_base + throttle_impact) if include_throttle else payg_base

    # Look up model-specific PTU capacity and output multiplier
    model_cfg = get_model_config(metrics.model_name)
    input_tpm_per_ptu = model_cfg.input_tpm_per_ptu if model_cfg else 2500
    model_output_multiplier = model_cfg.output_ratio if model_cfg else 3
    # Effective multiplier: output tokens consume more PTU capacity
    effective_mult = (1 - output_ratio) + output_ratio * model_output_multiplier
    # Effective raw-TPM capacity per PTU (accounts for output ratio)
    ptu_capacity = input_tpm_per_ptu / effective_mult
    region_cfg = get_region_config(region)
    deployment_cfg = get_deployment_config(deployment_type)
    deployment_kind = get_deployment_type(deployment_type)
    ptu_hourly = deployment_cfg.base_hourly_rate * region_cfg.multiplier
    ptu_increment = deployment_cfg.increment
    min_ptu = deployment_cfg.default_min_ptu
    term = _pricing_terms(reservation_type)
    reservation_discount = float(term["discount_factor"])
    reservation_discount_pct = int(term["discount_pct"])

    ptu_monthly_rate = ptu_hourly * 730 * reservation_discount

    tpm_values = list(tpm.values) if tpm else []
    spillover = calculate_spillover_cost(
        tpm_values=tpm_values,
        baseline_percentile=baseline_percentile,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_rate_per_1k=payg_rate_per_1k,
        reservation_discount=reservation_discount,
        baseline_ptu_override=baseline_ptu,
        min_ptu=min_ptu,
        ptu_increment=ptu_increment,
    )

    baseline_tpm = float(spillover["baseline_tpm"])
    baseline_ptu = int(spillover["baseline_ptu"])
    ptu_capacity_tpm = float(spillover["ptu_capacity_tpm"])
    spillover_tokens_monthly = float(spillover["spillover_tokens_monthly"])
    spillover_cost = float(spillover["spillover_cost"])
    ptu_baseline_cost = float(spillover["ptu_monthly_cost"])
    hybrid_total = float(spillover["total_hybrid_cost"])
    spillover_pct = float(spillover["spillover_pct"])
    avg_spillover_tpm = float(spillover["avg_spillover_tpm"])

    ptu_needed_full = max(min_ptu, int((peak_tpm * 1.2 / ptu_capacity) + 0.5)) if peak_tpm > 0 else min_ptu
    ptu_needed_full = ((ptu_needed_full + (ptu_increment - 1)) // ptu_increment) * ptu_increment
    ptu_monthly_full = ptu_needed_full * ptu_hourly * 24 * 30
    ptu_committed_cost = ptu_monthly_full * reservation_discount

    savings = payg_total - hybrid_total
    savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0.0

    break_even_tpm = calculate_break_even(
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        reservation_discount=reservation_discount,
        min_ptu=min_ptu,
        ptu_increment=ptu_increment,
        max_search_tpm=max(peak_tpm * 3, 100_000) if peak_tpm > 0 else 200_000,
    )

    cost_curves_df = generate_cost_curves(
        tpm_values=tpm_values,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        payg_rate_per_1k=payg_rate_per_1k,
        reservation_discount=reservation_discount,
        min_ptu=min_ptu,
        ptu_increment=ptu_increment,
        include_tpm=baseline_tpm,
    )

    # Derive chart-consistent break-even from the generated cost curves
    # (PAYG and PTU+spillover lines used in the frontend chart).
    curve_break_even_tpm: Optional[float] = None
    if not cost_curves_df.empty:
        diff = cost_curves_df["payg_monthly"] - cost_curves_df["ptu_spill_monthly"]
        for idx in range(1, len(cost_curves_df)):
            prev_diff = float(diff.iloc[idx - 1])
            curr_diff = float(diff.iloc[idx])
            if prev_diff < 0 <= curr_diff:
                prev_x = float(cost_curves_df["baseline_tpm"].iloc[idx - 1])
                curr_x = float(cost_curves_df["baseline_tpm"].iloc[idx])
                if curr_diff == prev_diff:
                    curve_break_even_tpm = curr_x
                else:
                    ratio = abs(prev_diff) / (abs(prev_diff) + abs(curr_diff))
                    curve_break_even_tpm = prev_x + (curr_x - prev_x) * ratio
                break

    if curve_break_even_tpm and curve_break_even_tpm > 0:
        break_even_tpm = curve_break_even_tpm

    payg_at_slider = baseline_tpm * 43_200 / 1_000_000 * payg_blended_rate

    if break_even_tpm and break_even_tpm > 0 and avg_tpm > 0:
        distance_pct = ((avg_tpm - break_even_tpm) / break_even_tpm) * 100
        if distance_pct > 10:
            break_even_message = (
                f"Your average TPM ({avg_tpm:,.0f}) is {distance_pct:.0f}% above break-even "
                f"({break_even_tpm:,.0f} TPM). PTU is cost-effective at current usage."
            )
        elif distance_pct >= -10:
            break_even_message = (
                f"Your average TPM ({avg_tpm:,.0f}) is near break-even ({break_even_tpm:,.0f} TPM). "
                "Small usage changes can tip the decision."
            )
        else:
            break_even_message = (
                f"Your average TPM ({avg_tpm:,.0f}) is {abs(distance_pct):.0f}% below break-even "
                f"({break_even_tpm:,.0f} TPM). PAYG is currently more cost-effective."
            )
    else:
        break_even_message = "Break-even was not reached in the evaluated range for the selected pricing term."

    token_timestamps = (
        [ts.isoformat() for ts in prompt.timestamps]
        if prompt and prompt.timestamps
        else ([ts.isoformat() for ts in completion.timestamps] if completion and completion.timestamps else [])
    )

    token_total_values: List[float] = []
    if prompt and completion and len(prompt.values) == len(completion.values):
        token_total_values = [float(p + c) for p, c in zip(prompt.values, completion.values)]
    elif tpm:
        token_total_values = [float(v) for v in tpm.values]

    requests_timestamps = (
        [ts.isoformat() for ts in successful.timestamps]
        if successful and successful.timestamps
        else ([ts.isoformat() for ts in throttled.timestamps] if throttled and throttled.timestamps else [])
    )

    request_total_values: List[float] = []
    if successful and throttled and len(successful.values) == len(throttled.values):
        request_total_values = [float(s + t) for s, t in zip(successful.values, throttled.values)]
    elif requests:
        request_total_values = [float(v) for v in requests.values]

    dimensions = []
    for dim in analysis.dimensions.all_dimensions:
        dimensions.append(
            {
                "name": dim.name,
                "score": dim.score.value,
                "confidence": float(dim.confidence),
                "summary": dim.summary,
                "explanation": dim.explanation,
                "key_metrics": dim.key_metrics,
                "is_positive": bool(dim.is_positive),
            }
        )

    utilization = {
        "peak_to_average_ratio": float(tpm.peak_to_average_ratio) if tpm else 0.0,
        "sustained_utilization_rate": float(tpm.sustained_utilization_rate(0.3)) if tpm else 0.0,
        "active_hours_percentage": float(tpm.active_hours_percentage) if tpm else 0.0,
        "business_hours_concentration": float(tpm.business_hours_concentration) if tpm else 0.0,
        "weekend_vs_weekday_ratio": float(tpm.weekend_vs_weekday_ratio) if tpm else 0.0,
    }

    # total_tokens already computed above from actual fetched data

    # ── Default PTU for slider (break-even-guided and recommendation-focused) ──
    if tpm_values:
        p25_tpm = float(np.percentile(tpm_values, 25))
        p25_raw = p25_tpm / ptu_capacity
        default_baseline_ptu = max(min_ptu, int(
            np.ceil(p25_raw / ptu_increment) * ptu_increment
        ))
    else:
        default_baseline_ptu = min_ptu

    if break_even_tpm and break_even_tpm > 0:
        be_ptu_raw = break_even_tpm / ptu_capacity
        break_even_ptu = max(min_ptu, int(
            np.ceil(be_ptu_raw / ptu_increment) * ptu_increment
        ))

        # Start from break-even PTU, then search up to break-even for the
        # best recommendation-friendly baseline (prefer savings > 5%).
        default_baseline_ptu = break_even_ptu

        if payg_total > 0 and tpm_values:
            best_positive: Optional[tuple[int, float]] = None
            best_any: Optional[tuple[int, float]] = None

            for candidate_ptu in range(min_ptu, break_even_ptu + ptu_increment, ptu_increment):
                candidate = calculate_spillover_cost(
                    tpm_values=tpm_values,
                    baseline_percentile=baseline_percentile,
                    ptu_capacity_per_unit=ptu_capacity,
                    ptu_hourly_rate=ptu_hourly,
                    payg_rate_per_1k=payg_rate_per_1k,
                    reservation_discount=reservation_discount,
                    baseline_ptu_override=candidate_ptu,
                    min_ptu=min_ptu,
                    ptu_increment=ptu_increment,
                )
                candidate_hybrid = float(candidate["total_hybrid_cost"])
                candidate_savings_pct = ((payg_total - candidate_hybrid) / payg_total) * 100

                if best_any is None or candidate_savings_pct > best_any[1]:
                    best_any = (candidate_ptu, candidate_savings_pct)
                if candidate_savings_pct > 5 and (
                    best_positive is None or candidate_savings_pct > best_positive[1]
                ):
                    best_positive = (candidate_ptu, candidate_savings_pct)

            if best_positive is not None:
                default_baseline_ptu = best_positive[0]
            elif best_any is not None:
                default_baseline_ptu = best_any[0]

    # Max PTU for slider range (P99 × 1.3 worth of PTU, minimum 2× default)
    if tpm_values:
        p99_tpm = float(np.percentile(tpm_values, 99))
        max_ptu_raw = p99_tpm * 1.3 / ptu_capacity
        max_baseline_ptu = max(
            default_baseline_ptu * 2,
            int(np.ceil(max_ptu_raw / ptu_increment) * ptu_increment),
        )
    else:
        max_baseline_ptu = default_baseline_ptu * 4

    # If caller didn't specify baseline PTU, evaluate Financial Decision using
    # the computed default baseline so first render is recommendation-focused.
    if baseline_ptu is None and default_baseline_ptu != baseline_ptu:
        spillover = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=baseline_percentile,
            ptu_capacity_per_unit=ptu_capacity,
            ptu_hourly_rate=ptu_hourly,
            payg_rate_per_1k=payg_rate_per_1k,
            reservation_discount=reservation_discount,
            baseline_ptu_override=default_baseline_ptu,
            min_ptu=min_ptu,
            ptu_increment=ptu_increment,
        )

        baseline_tpm = float(spillover["baseline_tpm"])
        baseline_ptu = int(spillover["baseline_ptu"])
        ptu_capacity_tpm = float(spillover["ptu_capacity_tpm"])
        spillover_tokens_monthly = float(spillover["spillover_tokens_monthly"])
        spillover_cost = float(spillover["spillover_cost"])
        ptu_baseline_cost = float(spillover["ptu_monthly_cost"])
        hybrid_total = float(spillover["total_hybrid_cost"])
        spillover_pct = float(spillover["spillover_pct"])
        avg_spillover_tpm = float(spillover["avg_spillover_tpm"])

        savings = payg_total - hybrid_total
        savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0.0
        payg_at_slider = baseline_tpm * 43_200 / 1_000_000 * payg_blended_rate

    # ── Cost-driven recommendation (reacts to slider PTU value) ──────────
    if payg_total > 0 and hybrid_total > 0:
        cost_savings_pct = savings_pct  # already (payg - hybrid) / payg * 100
        if cost_savings_pct > 5:
            cost_recommendation = "ptu_recommended"
        elif cost_savings_pct < -5:
            cost_recommendation = "ptu_not_recommended"
        else:
            cost_recommendation = "borderline"
    else:
        # Fall back to engine recommendation when costs can't be compared
        cost_recommendation = str(analysis.recommendation.value)

    # ── Financial-decision-aware narratives and dimensions ───────────────
    break_even_distance_pct = 0.0
    if break_even_tpm and break_even_tpm > 0 and baseline_tpm > 0:
        break_even_distance_pct = ((baseline_tpm - break_even_tpm) / break_even_tpm) * 100

    selected_context = (
        f"Selected baseline: {baseline_ptu} PTU ({baseline_tpm:,.0f} TPM), "
        f"hybrid cost ${hybrid_total:,.0f}/month vs PAYG ${payg_total:,.0f}/month."
    )

    if cost_recommendation == "ptu_recommended":
        dynamic_summary = (
            f"PTU is recommended at {baseline_ptu} PTU; estimated savings are "
            f"{savings_pct:.1f}% (${savings:,.0f}/month)."
        )
        dynamic_explanation = (
            f"{selected_context} This baseline remains financially favorable, with "
            f"spillover at {spillover_pct:.1f}% and break-even distance {break_even_distance_pct:.1f}%."
        )
        dynamic_what_would_change = (
            "Recommendation may move away from PTU if sustained TPM declines, "
            "spillover rises substantially, or PAYG blended rates decrease."
        )
    elif cost_recommendation == "ptu_not_recommended":
        dynamic_summary = (
            f"PAYG is recommended at {baseline_ptu} PTU baseline; PTU would increase cost by "
            f"{abs(savings_pct):.1f}% (${abs(savings):,.0f}/month)."
        )
        dynamic_explanation = (
            f"{selected_context} At this baseline, PTU is not cost-effective. "
            f"Break-even distance is {break_even_distance_pct:.1f}% and spillover is {spillover_pct:.1f}%."
        )
        dynamic_what_would_change = (
            "Recommendation may move toward PTU with higher sustained traffic, "
            "lower spillover, or selecting a lower but still efficient PTU baseline."
        )
    else:
        dynamic_summary = (
            f"Decision is borderline at {baseline_ptu} PTU; estimated delta is "
            f"{savings_pct:.1f}% (${savings:,.0f}/month)."
        )
        dynamic_explanation = (
            f"{selected_context} Costs are close enough that modest workload or pricing changes "
            f"can flip the recommendation."
        )
        dynamic_what_would_change = (
            "A small increase in sustained TPM or a lower-spillover PTU baseline can favor PTU; "
            "a decrease in demand can favor PAYG."
        )

    dynamic_confidence = float(min(0.98, max(0.55, 0.55 + (abs(savings_pct) / 100))))

    financial_score = "positive" if savings_pct > 5 else ("negative" if savings_pct < -5 else "neutral")
    spillover_score = "positive" if spillover_pct <= 20 else ("negative" if spillover_pct >= 40 else "neutral")

    enriched_dimensions: List[Dict[str, Any]] = []
    for dim in dimensions:
        dim_name = str(dim.get("name", ""))
        dim_key_metrics = dict(dim.get("key_metrics") or {})
        dim_key_metrics.update(
            {
                "selected_baseline_ptu": float(baseline_ptu),
                "selected_baseline_tpm": float(baseline_tpm),
                "estimated_savings_pct": float(savings_pct),
                "spillover_pct": float(spillover_pct),
                "break_even_tpm": float(break_even_tpm) if break_even_tpm else 0.0,
            }
        )

        lowered = dim_name.lower()
        if "capacity" in lowered:
            dim["score"] = financial_score
            dim["summary"] = (
                f"At {baseline_ptu} PTU, monthly delta is {savings_pct:.1f}% "
                f"(${savings:,.0f}/month)."
            )
            dim["explanation"] = (
                f"Capacity decision is currently driven by selected PTU baseline. "
                f"PAYG ${payg_total:,.0f} vs hybrid ${hybrid_total:,.0f}."
            )
            dim["is_positive"] = financial_score == "positive"
            dim["confidence"] = dynamic_confidence
        elif "predict" in lowered:
            dim["score"] = spillover_score
            dim["summary"] = (
                f"Spillover is {spillover_pct:.1f}% at {baseline_ptu} PTU "
                f"({avg_spillover_tpm:,.0f} average overflow TPM)."
            )
            dim["explanation"] = (
                "Lower spillover indicates the selected PTU baseline tracks demand more predictably."
            )
            dim["is_positive"] = spillover_score == "positive"

        dim["key_metrics"] = dim_key_metrics
        enriched_dimensions.append(dim)

    return AnalyzeResponse(
        recommendation=cost_recommendation,
        confidence=dynamic_confidence,
        summary=dynamic_summary,
        explanation=dynamic_explanation,
        what_would_change=dynamic_what_would_change,
        data_quality=str(analysis.data_quality),
        analysis_period=str(analysis.analysis_period),
        dimensions=enriched_dimensions,
        metrics={
            "deployment_name": metrics.deployment_name,
            "model_name": metrics.model_name,
            "avg_tpm": avg_tpm,
            "peak_tpm": peak_tpm,
            "throttling_rate_pct": throttle_rate_pct,
            "total_requests": int(metrics.total_requests),
            "throttled_requests": int(throttled.total) if throttled else 0,
            "successful_requests": int(successful.total) if successful else 0,
            "total_tokens": total_tokens,
            "total_tokens_millions": total_tokens / 1_000_000,
            "lookback_days": lookback_days,
            "latency": {
                "p50": float(p50.mean) if p50 else 0.0,
                "p95": float(p95.mean) if p95 else 0.0,
                "p99": float(p99.mean) if p99 else 0.0,
            },
            "utilization": utilization,
            "series_summary": {
                "tpm": _series_payload(tpm),
                "requests": _series_payload(requests),
                "successful_requests": _series_payload(successful),
                "throttled_requests": _series_payload(throttled),
                "prompt_tokens": _series_payload(prompt),
                "completion_tokens": _series_payload(completion),
                "latency_p50": _series_payload(p50),
                "latency_p95": _series_payload(p95),
                "latency_p99": _series_payload(p99),
            },
        },
        charts={
            "tokens": {
                "timestamps": token_timestamps,
                "prompt": [float(v) for v in prompt.values] if prompt else [],
                "completion": [float(v) for v in completion.values] if completion else [],
                "total": token_total_values,
            },
            "requests": {
                "timestamps": requests_timestamps,
                "successful": [float(v) for v in successful.values] if successful else [],
                "throttled": [float(v) for v in throttled.values] if throttled else [],
                "total": request_total_values,
            },
            "daily_cost": {
                **_aggregate_daily_costs(
                    timestamps=token_timestamps,
                    prompt_values=[float(v) for v in prompt.values] if prompt else [],
                    completion_values=[float(v) for v in completion.values] if completion else [],
                    payg_input_rate=payg_input_rate,
                    payg_output_rate=payg_output_rate,
                ),
                "ptu_daily_cost": round(ptu_baseline_cost / 30, 2),
            },
            "tpm": {
                "timestamps": [ts.isoformat() for ts in (tpm.timestamps if tpm else [])],
                "values": [float(v) for v in (tpm.values if tpm else [])],
                "avg": float(tpm.mean) if tpm else 0.0,
                "p25": float(np.percentile(tpm_values, 25)) if tpm_values else 0.0,
                "p95": float(tpm.p95) if tpm else 0.0,
            },
            "throttling": {
                "timestamps": [ts.isoformat() for ts in (throttled.timestamps if throttled else [])],
                "values": [float(v) for v in (throttled.values if throttled else [])],
            },
            "cost_curves": {
                "baseline_tpm": [float(v) for v in cost_curves_df["baseline_tpm"].tolist()] if not cost_curves_df.empty else [],
                "payg_monthly": [float(v) for v in cost_curves_df["payg_monthly"].tolist()] if not cost_curves_df.empty else [],
                "ptu_spill_monthly": [float(v) for v in cost_curves_df["ptu_spill_monthly"].tolist()] if not cost_curves_df.empty else [],
                "ptu_units": [int(v) for v in cost_curves_df["ptu_units"].tolist()] if not cost_curves_df.empty else [],
                "break_even_tpm": float(break_even_tpm) if break_even_tpm else None,
                "slider_baseline_tpm": baseline_tpm,
                "payg_at_slider": float(payg_at_slider),
                "hybrid_at_slider": float(hybrid_total),
            },
        },
        cost_analysis={
            "pricing": {
                "focus_topic": focus_topic,
                "reservation_type": reservation_type,
                "reservation_discount_pct": reservation_discount_pct,
                "region": region_cfg.name,
                "region_display_name": region_cfg.display_name,
                "region_multiplier": region_cfg.multiplier,
                "deployment_type": deployment_kind.value,
                "deployment_type_label": deployment_cfg.label,
                "payg_blended_rate_per_million": payg_blended_rate,
                "payg_input_rate_per_million": payg_input_rate,
                "payg_output_rate_per_million": payg_output_rate,
                "output_ratio": round(output_ratio, 4),
                "ptu_hourly_rate": ptu_hourly,
                "ptu_capacity_per_unit": ptu_capacity,
                "input_tpm_per_ptu": input_tpm_per_ptu,
                "model_output_multiplier": model_output_multiplier,
                "effective_mult": round(effective_mult, 4),
                "ptu_increment": ptu_increment,
                "ptu_minimum": min_ptu,
            },
            "payg": {
                "monthly_tokens": float(monthly_tokens),
                "payg_base": float(payg_base),
                "throttle_impact": float(throttle_impact),
                "payg_total": float(payg_total),
            },
            "hybrid": {
                "baseline_percentile": baseline_percentile,
                "baseline_label": f"{baseline_ptu} PTU",
                "baseline_tpm": baseline_tpm,
                "baseline_ptu": baseline_ptu,
                "default_baseline_ptu": default_baseline_ptu,
                "max_baseline_ptu": max_baseline_ptu,
                "ptu_capacity_tpm": ptu_capacity_tpm,
                "avg_spillover_tpm": avg_spillover_tpm,
                "spillover_tokens_monthly": spillover_tokens_monthly,
                "spillover_cost": spillover_cost,
                "ptu_baseline_cost": ptu_baseline_cost,
                "hybrid_total": hybrid_total,
                "spillover_pct": spillover_pct,
            },
            "full_ptu": {
                "ptu_needed_full": int(ptu_needed_full),
                "ptu_monthly_full": float(ptu_monthly_full),
                "ptu_committed_cost": float(ptu_committed_cost),
            },
            "comparison": {
                "savings": float(savings),
                "savings_pct": float(savings_pct),
                "break_even_tpm": float(break_even_tpm) if break_even_tpm else None,
                "cheaper_strategy": "PTU + Spillover" if savings > 0 else "PAYG",
            },
            "formula_blocks": _build_formula_blocks(
                avg_tpm=avg_tpm,
                total_tokens=total_tokens,
                lookback_days=lookback_days,
                avg_daily_tokens=avg_daily_tokens,
                payg_input_rate=payg_input_rate,
                payg_output_rate=payg_output_rate,
                output_ratio=output_ratio,
                payg_blended_rate=payg_blended_rate,
                payg_base=payg_base,
                payg_total=payg_total,
                throttle_rate=throttle_rate,
                throttle_rate_pct=throttle_rate_pct,
                throttle_impact=throttle_impact,
                include_throttle=include_throttle,
                baseline_ptu=baseline_ptu,
                ptu_monthly_rate=ptu_monthly_rate,
                ptu_baseline_cost=ptu_baseline_cost,
                avg_spillover_tpm=avg_spillover_tpm,
                spillover_cost=spillover_cost,
                hybrid_total=hybrid_total,
                effective_mult=effective_mult,
                input_tpm_per_ptu=input_tpm_per_ptu,
                model_output_multiplier=model_output_multiplier,
            ),
        },
        insights={
            "break_even_message": break_even_message,
            "focus_topic": focus_topic,
            "analysis_notes": [
                "PTU + spillover sizes baseline capacity and overflows peak traffic to PAYG.",
                "Throttling above 1% usually indicates capacity pressure affecting reliability.",
                "Stable utilization patterns improve PTU ROI.",
            ],
        },
    )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/focus-topics")
def focus_topics() -> List[Dict[str, str]]:
    return [
        {"name": name, "tagline": data.get("tagline", "")}
        for name, data in FOCUS_TOPICS.items()
    ]


@app.get("/api/pricing/options")
def pricing_options() -> Dict[str, Any]:
    regions = [
        {
            "name": region.name,
            "display_name": region.display_name,
            "multiplier": region.multiplier,
            "zone": region.zone,
        }
        for region in sorted(REGION_CONFIGS.values(), key=lambda value: value.display_name)
    ]
    deployment_types = [
        {
            "name": dtype.value,
            "label": config.label,
            "increment": config.increment,
            "default_min_ptu": config.default_min_ptu,
            "base_hourly_rate": config.base_hourly_rate,
        }
        for dtype, config in DEPLOYMENT_TYPE_CONFIGS.items()
    ]
    return {"regions": regions, "deployment_types": deployment_types}


@app.get("/api/discovery/subscriptions")
def subscriptions() -> List[Dict[str, Any]]:
    credential = get_azure_credential()
    subs = list_subscriptions(credential)
    return [
        {
            "subscription_id": sub.subscription_id,
            "display_name": sub.display_name,
            "state": sub.state,
            "label": sub.label,
        }
        for sub in subs
    ]


@app.get("/api/discovery/accounts")
def accounts(subscription_id: str = Query(...)) -> List[Dict[str, Any]]:
    credential = get_azure_credential()
    items = list_ai_accounts(credential, subscription_id)
    return [
        {
            "name": account.name,
            "resource_group": account.resource_group,
            "location": account.location,
            "kind": account.kind,
            "sku_name": account.sku_name,
            "label": account.label,
        }
        for account in items
    ]


@app.get("/api/discovery/deployments")
def deployments(
    subscription_id: str = Query(...),
    resource_group: str = Query(...),
    account_name: str = Query(...),
) -> List[Dict[str, Any]]:
    credential = get_azure_credential()
    items = list_deployments(credential, subscription_id, resource_group, account_name)
    return [
        {
            "name": dep.name,
            "model": dep.model,
            "sku_type": dep.sku_type,
            "sku_capacity": dep.sku_capacity,
        }
        for dep in items
    ]


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    if payload.mode == "demo":
        scenario = _pick_demo_scenario(payload.focus_topic)
        metrics, _scenario_cfg = generate_demo_metrics(
            scenario,
            lookback_days=payload.lookback_days,
            granularity_minutes=payload.granularity_minutes,
        )
        metrics = _filter_metrics_by_window(metrics, payload.window_start, payload.window_end)
        effective_lookback_days = max(
            1,
            int(max(1.0, (metrics.end_time - metrics.start_time).total_seconds() / 86_400.0)),
        )
        config = AnalysisConfig(
            resource_group="demo-rg",
            workspace="demo-workspace",
            deployment=metrics.deployment_name,
            lookback_days=effective_lookback_days,
            aggregation_interval_minutes=payload.granularity_minutes,
        )
        engine = DecisionEngine(config)
        analysis = engine.analyze(metrics)
        return _serialize_analysis(
            metrics=metrics,
            analysis=analysis,
            focus_topic=payload.focus_topic,
            lookback_days=effective_lookback_days,
            reservation_type=payload.reservation_type,
            baseline_percentile=payload.baseline_percentile,
            region=normalize_region(payload.region),
            deployment_type=payload.deployment_type,
            baseline_ptu=payload.baseline_ptu,
            include_throttle=payload.include_throttle,
        )

    if not payload.subscription_id or not payload.resource_group or not payload.workspace:
        raise HTTPException(status_code=400, detail="subscription_id, resource_group, and workspace are required in live mode")

    if not payload.deployment:
        raise HTTPException(status_code=400, detail="deployment is required in live mode")

    credential = get_azure_credential()
    config = AnalysisConfig(
        resource_group=payload.resource_group,
        workspace=payload.workspace,
        deployment=payload.deployment,
        subscription_id=payload.subscription_id,
        lookback_days=payload.lookback_days,
        aggregation_interval_minutes=payload.granularity_minutes,
    )

    collector = MetricsCollector(credential, config)
    metrics = collector.collect()
    metrics = _filter_metrics_by_window(metrics, payload.window_start, payload.window_end)

    effective_lookback_days = max(
        1,
        int(max(1.0, (metrics.end_time - metrics.start_time).total_seconds() / 86_400.0)),
    )

    if metrics.tokens_per_minute is None and metrics.requests_per_minute is None:
        diagnostics = collector.get_diagnostics()
        metric_items = diagnostics.get("metrics", [])
        context = diagnostics.get("context", {})

        # Build a human-readable hint from the diagnostics
        account_empty = [d for d in metric_items if d.get("status") == "account_empty"]
        probe_diags = [d for d in metric_items if d.get("status") == "fallback_probe"]

        if account_empty:
            hint = (
                f"{account_empty[0]['message']}\n\n"
                "Troubleshooting steps:\n"
                "1. Verify the resource has had API traffic in the selected "
                f"lookback window ({payload.lookback_days} days).\n"
                "2. Check that 'Diagnostic settings' are enabled on the "
                "Cognitive Services resource in the Azure portal "
                "(Settings → Diagnostic settings → Add diagnostic setting).\n"
                "3. Confirm the signed-in identity has at least 'Monitoring "
                "Reader' role on the resource.\n"
                f"4. Resource ID used: {context.get('resource_id', 'N/A')}"
            )
        elif probe_diags:
            hint = probe_diags[0]["message"]
        else:
            missing = [d["metric_name"] for d in metric_items if d.get("status") == "missing"]
            hint = (
                f"No data returned for metrics: {', '.join(missing)}. "
                f"The deployment '{payload.deployment}' may have had no traffic "
                f"in the last {payload.lookback_days} days, or the resource may "
                f"not expose these metrics. "
                f"Resource ID: {context.get('resource_id', 'N/A')}"
            )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No metrics returned for selected deployment",
                "hint": hint,
                "diagnostics": diagnostics,
            },
        )

    analysis_config = AnalysisConfig(
        resource_group=payload.resource_group,
        workspace=payload.workspace,
        deployment=payload.deployment,
        subscription_id=payload.subscription_id,
        lookback_days=effective_lookback_days,
        aggregation_interval_minutes=payload.granularity_minutes,
    )

    engine = DecisionEngine(analysis_config)
    analysis = engine.analyze(metrics)
    return _serialize_analysis(
        metrics=metrics,
        analysis=analysis,
        focus_topic=payload.focus_topic,
        lookback_days=effective_lookback_days,
        reservation_type=payload.reservation_type,
        baseline_percentile=payload.baseline_percentile,
        region=normalize_region(payload.region),
        deployment_type=payload.deployment_type,
        baseline_ptu=payload.baseline_ptu,
        include_throttle=payload.include_throttle,
    )


# ---------------------------------------------------------------------------
# Static file serving (production)
# ---------------------------------------------------------------------------
# In Docker the Vite build output is copied to /app/static.  When that
# directory exists we mount a catch-all route *after* all /api/* routes so
# the React SPA is served for every non-API path (including index.html
# fallback for client-side routing).
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

_STATIC_CANDIDATES = [
    # Source layout (repo/local editable installs)
    Path(__file__).resolve().parent.parent.parent / "static",
    # Docker runtime layout (frontend copied to /app/static)
    Path("/app/static"),
]

_STATIC_DIR = next((path for path in _STATIC_CANDIDATES if path.is_dir()), None)

if _STATIC_DIR:
    from starlette.responses import FileResponse  # noqa: E402

    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str) -> FileResponse:
        """Serve React SPA; fall back to index.html for client-side routing."""
        file_path = _STATIC_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_STATIC_DIR / "index.html")
