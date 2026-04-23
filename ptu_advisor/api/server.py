from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ptu_advisor.analysis.engine import DecisionEngine
from ptu_advisor.auth import get_azure_credential
from ptu_advisor.config import (
    AnalysisConfig,
    get_ineligibility_reason,
    get_model_config,
    get_model_family,
)
from ptu_advisor.cost.calculator import (
    calculate_break_even,
    calculate_break_even_for_fixed_ptu,
    calculate_spillover_cost,
    generate_cost_curves,
    generate_cost_curves_fixed_ptu,
)
from ptu_advisor.cost.pricing import (
    DEPLOYMENT_TYPE_CONFIGS,
    REGION_CONFIGS,
    get_deployment_config,
    get_deployment_type,
    get_region_config,
    normalize_region,
)
from ptu_advisor.cost.price_resolver import PricingResolver, get_pricing_resolver
from ptu_advisor.demo import (
    DemoScenario,
    FOCUS_TOPICS,
    generate_demo_metrics,
    generate_consolidation_demo_metrics,
)
from ptu_advisor.metrics.merge import (
    compute_individual_payg_cost,
    merge_deployment_metrics,
    serialize_per_deployment_charts,
)
from ptu_advisor.discovery import (
    authenticate,
    invalidate_discovery_cache,
    list_ai_accounts,
    list_deployments,
    list_subscriptions,
)
from ptu_advisor.metrics.collector import MetricsCollector
from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries


class AnalyzeRequest(BaseModel):
    mode: Literal["demo", "live"] = "live"
    focus_topic: str = "Cost Reduction"
    lookback_days: int = Field(default=14, ge=1, le=30)
    granularity_minutes: Literal[1, 5, 15, 30] = 1
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    workspace: Optional[str] = None
    deployment: Optional[str] = None
    reservation_type: Literal[
        "Hourly — No Commitment",
        "Monthly Commitment (Estimated 64% off)",
    ] = "Monthly Commitment (Estimated 64% off)"
    baseline_percentile: Optional[float] = None
    baseline_ptu: Optional[int] = None
    region: str = "eastus"
    deployment_type: Literal["global", "data_zone", "regional"] = "global"
    include_throttle: bool = False

    payg_input_rate_override: Optional[float] = Field(default=None, ge=0)
    payg_output_rate_override: Optional[float] = Field(default=None, ge=0)
    ptu_hourly_rate_override: Optional[float] = Field(default=None, ge=0)


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


class ConsolidationRequest(BaseModel):
    mode: Literal["demo", "live"] = "live"
    deployments: List[str] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="2-10 deployment names of the same model to consolidate",
    )
    focus_topic: str = "Cost Reduction"
    lookback_days: int = Field(default=14, ge=1, le=30)
    granularity_minutes: Literal[1, 5, 15, 30] = 1
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    workspace: Optional[str] = None
    reservation_type: Literal[
        "Hourly — No Commitment",
        "Monthly Commitment (Estimated 64% off)",
        "1-Year Commitment (Estimated 69% off)",
    ] = "Monthly Commitment (Estimated 64% off)"
    baseline_percentile: int = Field(default=75, ge=0, le=95)
    baseline_ptu: Optional[int] = Field(
        default=None,
        ge=0,
        description="PTU units for slider. When set, overrides baseline_percentile.",
    )
    region: str = "eastus"
    deployment_type: Literal["global", "data_zone", "regional"] = "global"
    include_throttle: bool = False

    payg_input_rate_override: Optional[float] = Field(default=None, ge=0)
    payg_output_rate_override: Optional[float] = Field(default=None, ge=0)
    ptu_hourly_rate_override: Optional[float] = Field(default=None, ge=0)


class IndividualDeploymentSummary(BaseModel):
    name: str
    avg_tpm: float
    peak_tpm: float
    throttling_rate_pct: float
    total_requests: int
    latency_p50: float
    latency_p95: float
    payg_monthly_cost: float


class ConsolidationSummary(BaseModel):
    deployment_count: int
    model_name: str
    deployment_type: str
    individual_deployments: List[IndividualDeploymentSummary]
    combined_avg_tpm: float
    combined_peak_tpm: float
    combined_throttling_rate_pct: float
    individual_payg_total: float
    consolidated_hybrid_cost: float
    savings: float
    savings_pct: float
    warnings: List[str] = Field(default_factory=list)
    all_on_ptu: bool = False


class ConsolidationResponse(AnalyzeResponse):
    consolidation_summary: ConsolidationSummary


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


@app.on_event("startup")
def _startup_warm_pricing_cache() -> None:
    """Pre-warm popular model/region pricing combos and start the periodic refresh."""
    resolver = get_pricing_resolver()
    resolver.warm_cache()
    resolver.start_background_warmup()


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
        setattr(
            filtered, attr_name, _filter_series_by_window(series, normalized_start, normalized_end)
        )

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
    pricing_source: str = "",
) -> Dict[str, str]:
    """Build human-readable formula strings for PAYG and hybrid cost breakdowns."""
    avg_daily_overflow = avg_spillover_tpm * 1440  # tokens/day

    monthly_tokens = avg_daily_tokens * 30
    effective_capacity = input_tpm_per_ptu / effective_mult

    # Annotation suffix when user has overridden rates
    rate_tag = " (custom rate)" if pricing_source == "manual" else ""

    # ── PAYG block ──
    payg_lines = [
        f"avg_daily_tokens = {avg_tpm:,.0f} TPM × 1,440 min/day = {avg_daily_tokens:,.0f} tokens/day",
        f"monthly_tokens = {avg_daily_tokens:,.0f} × 30 days = {monthly_tokens:,.0f} tokens/month",
        f"blended_rate = ${payg_input_rate:.2f} × {(1 - output_ratio) * 100:.0f}% input + ${payg_output_rate:.2f} × {output_ratio * 100:.0f}% output = ${payg_blended_rate:.2f}/1M tokens{rate_tag}",
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
        f"effective_mult = {(1 - output_ratio) * 100:.0f}% input + {output_ratio * 100:.0f}% output × {model_output_multiplier} = {effective_mult:.2f}×",
        f"capacity_per_ptu = {input_tpm_per_ptu:,} ÷ {effective_mult:.2f} = {effective_capacity:,.0f} raw TPM/PTU",
        f"ptu_cost = {baseline_ptu} PTU × ${ptu_monthly_rate:,.2f}/PTU/month = ${ptu_baseline_cost:,.0f}/month{rate_tag}",
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
    payg_input_rate_override: Optional[float] = None,
    payg_output_rate_override: Optional[float] = None,
    ptu_hourly_rate_override: Optional[float] = None,
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

    # ── Resolve pricing via layered strategy ─────────────────────────────
    resolver = get_pricing_resolver()
    pricing = resolver.resolve(
        model_name=metrics.model_name,
        region=region,
        deployment_type=deployment_type,
        payg_input_override=payg_input_rate_override,
        payg_output_override=payg_output_rate_override,
        ptu_hourly_override=ptu_hourly_rate_override,
    )
    payg_input_rate = pricing.payg_input_rate
    payg_output_rate = pricing.payg_output_rate
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
    # Use the resolved PTU hourly rate (live/cached/fallback/manual)
    # instead of the old base_hourly_rate * multiplier formula
    ptu_hourly = pricing.ptu_hourly_rate
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

    ptu_needed_full = (
        max(min_ptu, int((peak_tpm * 1.2 / ptu_capacity) + 0.5)) if peak_tpm > 0 else min_ptu
    )
    ptu_needed_full = ((ptu_needed_full + (ptu_increment - 1)) // ptu_increment) * ptu_increment
    ptu_monthly_full = ptu_needed_full * ptu_hourly * 24 * 30
    ptu_committed_cost = ptu_monthly_full * reservation_discount

    savings = payg_total - hybrid_total
    savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0.0

    # v2: Fixed-PTU break-even — analytical solution
    break_even_tpm = calculate_break_even_for_fixed_ptu(
        selected_ptu=baseline_ptu,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        reservation_discount=reservation_discount,
    )

    # Determine break-even reason for distinct messaging (PRD §5):
    # - "exists": break-even TPM is within PTU capacity (normal case)
    # - "ptu_always_more_expensive": flat_break_even > ptu_capacity (PTU never pays off)
    # - "ptu_always_cheaper": degenerate case (ptu_fixed ≈ 0 or rate ≈ 0)
    if break_even_tpm is not None:
        break_even_reason = "exists"
    elif payg_blended_rate > 0 and ptu_hourly > 0:
        break_even_reason = "ptu_always_more_expensive"
    else:
        break_even_reason = "ptu_always_cheaper"

    # v2: Cost curves with fixed PTU, varying traffic on X-axis
    curve_max_tpm = (
        max(peak_tpm * 2, avg_tpm * 3, ptu_capacity_tpm * 2, 100_000) if peak_tpm > 0 else 200_000
    )
    cost_curves_df = generate_cost_curves_fixed_ptu(
        selected_ptu=baseline_ptu,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        reservation_discount=reservation_discount,
        max_tpm=curve_max_tpm,
    )

    payg_at_avg = avg_tpm * 43_200 / 1_000_000 * payg_blended_rate

    token_timestamps = (
        [ts.isoformat() for ts in prompt.timestamps]
        if prompt and prompt.timestamps
        else (
            [ts.isoformat() for ts in completion.timestamps]
            if completion and completion.timestamps
            else []
        )
    )

    token_total_values: List[float] = []
    if prompt and completion and len(prompt.values) == len(completion.values):
        token_total_values = [float(p + c) for p, c in zip(prompt.values, completion.values)]
    elif tpm:
        token_total_values = [float(v) for v in tpm.values]

    requests_timestamps = (
        [ts.isoformat() for ts in successful.timestamps]
        if successful and successful.timestamps
        else (
            [ts.isoformat() for ts in throttled.timestamps]
            if throttled and throttled.timestamps
            else []
        )
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

    # ── Default PTU for slider (recommendation-aware) ──────────────────
    # Strategy:
    #   PTU recommended / borderline → max PTU that still saves > 5%
    #   PTU NOT recommended          → min PTU (so break-even chart
    #                                   shows what traffic level is needed)
    default_baseline_ptu = min_ptu  # fallback

    if payg_total > 0 and tpm_values:
        # Upper bound for the sweep: enough PTU to cover P99 × 1.3
        p99_tpm_sweep = float(np.percentile(tpm_values, 99))
        sweep_ceiling_raw = p99_tpm_sweep * 1.3 / ptu_capacity
        sweep_ceiling = max(
            min_ptu, int(np.ceil(sweep_ceiling_raw / ptu_increment) * ptu_increment)
        )

        # Walk from min_ptu up to sweep_ceiling and track the lowest-cost
        # PTU value that still delivers > 5% savings.
        best_positive_ptu: Optional[int] = None
        best_positive_hybrid: Optional[float] = None
        max_positive_ptu: Optional[int] = None

        for candidate_ptu in range(min_ptu, sweep_ceiling + ptu_increment, ptu_increment):
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

            if candidate_savings_pct > 5 and (
                best_positive_hybrid is None or candidate_hybrid < best_positive_hybrid
            ):
                best_positive_ptu = candidate_ptu
                best_positive_hybrid = candidate_hybrid
            if candidate_savings_pct > 5:
                max_positive_ptu = candidate_ptu

        if best_positive_ptu is not None:
            # PTU is cost-effective → default to the clearest economical
            # starting point rather than the largest viable commitment.
            default_baseline_ptu = best_positive_ptu
        # else: no PTU level saves > 5% → keep min_ptu so user sees the
        # break-even threshold for the smallest possible commitment

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

    max_viable_baseline_ptu = max_positive_ptu if payg_total > 0 else None

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

    # ── Commitment Safety metrics (Layer E) ─────────────────────────────
    savings_margin_pct = float(savings_pct)  # already (payg - hybrid) / payg * 100
    capacity_coverage_pct = 100.0 - spillover_pct  # % of intervals fitting in PTU
    # Determine safety verdict (thresholds per PRD §3.1.1)
    if savings_margin_pct <= 0:
        safety_verdict = "not_justified"
    elif savings_margin_pct < 5 or spillover_pct > 25 or capacity_coverage_pct < 75:
        safety_verdict = "efficient_but_risky"
    else:
        safety_verdict = "safe"

    if break_even_tpm and break_even_tpm > 0 and avg_tpm > 0:
        distance_pct = ((avg_tpm - break_even_tpm) / break_even_tpm) * 100
        if distance_pct > 10:
            break_even_message = (
                f"Economic break-even for {baseline_ptu} PTU is {break_even_tpm:,.0f} TPM. "
                f"Your average TPM ({avg_tpm:,.0f}) is {distance_pct:.0f}% above that threshold, "
                f"so the economic signal favors PTU. Final recommendation: {cost_recommendation.replace('_', ' ')} "
                f"with safety verdict '{safety_verdict}'."
            )
        elif distance_pct >= -10:
            break_even_message = (
                f"Economic break-even for {baseline_ptu} PTU is {break_even_tpm:,.0f} TPM. "
                f"Your average TPM ({avg_tpm:,.0f}) is near that threshold, so the economic signal is marginal. "
                f"Final recommendation: {cost_recommendation.replace('_', ' ')} with safety verdict '{safety_verdict}'."
            )
        else:
            break_even_message = (
                f"Economic break-even for {baseline_ptu} PTU is {break_even_tpm:,.0f} TPM. "
                f"Your average TPM ({avg_tpm:,.0f}) is {abs(distance_pct):.0f}% below that threshold, "
                f"so the economic signal favors PAYG. Final recommendation: {cost_recommendation.replace('_', ' ')} "
                f"with safety verdict '{safety_verdict}'."
            )
    elif break_even_reason == "ptu_always_cheaper":
        break_even_message = (
            f"PTU is cheaper than PAYG at all usage levels for {baseline_ptu} PTU. "
            f"Final recommendation: {cost_recommendation.replace('_', ' ')} with safety verdict '{safety_verdict}'."
        )
    else:
        # ptu_always_more_expensive (PRD §5 row 1)
        break_even_message = (
            f"No economic break-even exists for {baseline_ptu} PTU within the no-spillover range. "
            f"At your usage level, PAYG is more cost-effective for this commitment size. "
            f"Final recommendation: {cost_recommendation.replace('_', ' ')} with safety verdict '{safety_verdict}'."
        )

    # ── Financial-decision-aware narratives and dimensions ───────────────
    break_even_distance_pct = 0.0
    if break_even_tpm and break_even_tpm > 0 and avg_tpm > 0:
        break_even_distance_pct = ((avg_tpm - break_even_tpm) / break_even_tpm) * 100

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

    financial_score = (
        "positive" if savings_pct > 5 else ("negative" if savings_pct < -5 else "neutral")
    )
    spillover_score = (
        "positive" if spillover_pct <= 20 else ("negative" if spillover_pct >= 40 else "neutral")
    )

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
                "timestamps": [
                    ts.isoformat() for ts in (throttled.timestamps if throttled else [])
                ],
                "values": [float(v) for v in (throttled.values if throttled else [])],
            },
            "cost_curves": {
                "sustained_tpm": [float(v) for v in cost_curves_df["sustained_tpm"].tolist()]
                if not cost_curves_df.empty
                else [],
                "payg_monthly": [float(v) for v in cost_curves_df["payg_monthly"].tolist()]
                if not cost_curves_df.empty
                else [],
                "ptu_spill_monthly": [
                    float(v) for v in cost_curves_df["ptu_spill_monthly"].tolist()
                ]
                if not cost_curves_df.empty
                else [],
                "break_even_tpm": float(break_even_tpm) if break_even_tpm else None,
                "break_even_reason": break_even_reason,
                "ptu_capacity_tpm": float(ptu_capacity_tpm),
                "avg_tpm": float(avg_tpm),
                "selected_ptu": baseline_ptu,
                "payg_at_avg": float(payg_at_avg),
                "hybrid_at_avg": float(hybrid_total),
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
                "pricing_source": pricing.source,
                "pricing_as_of": pricing.as_of.isoformat(),
                "pricing_currency": pricing.currency,
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
                "max_viable_baseline_ptu": int(max_viable_baseline_ptu)
                if max_viable_baseline_ptu is not None
                else None,
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
            "commitment_safety": {
                "savings_margin_pct": round(savings_margin_pct, 1),
                "spillover_pct": round(spillover_pct, 1),
                "capacity_coverage_pct": round(capacity_coverage_pct, 1),
                "safety_verdict": safety_verdict,
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
                pricing_source=pricing.source,
            ),
        },
        insights={
            "break_even_message": break_even_message,
            "focus_topic": focus_topic,
            "analysis_notes": [
                "PTU + spillover sizes baseline capacity and overflows peak traffic to PAYG.",
                "Throttling above 1% usually indicates capacity pressure affecting reliability.",
                "Stable utilization patterns improve PTU ROI.",
            ]
            + (
                [
                    "High usage variance (CV > 1.5) means spillover costs remain significant "
                    "even at high baselines. Consider whether your workload shape is predictable "
                    "enough for a PTU commitment."
                ]
                if tpm_values and avg_tpm > 0 and float(np.std(tpm_values)) / avg_tpm > 1.5
                else []
            ),
        },
    )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/focus-topics")
def focus_topics() -> List[Dict[str, str]]:
    return [
        {"name": name, "tagline": data.get("tagline", "")} for name, data in FOCUS_TOPICS.items()
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


@app.get("/api/pricing/rates")
def pricing_rates(
    model: str = Query(..., description="Model name (e.g. gpt-4o, gpt-5)"),
    region: str = Query("eastus", description="Azure region slug"),
    deployment_type: str = Query(
        "global", description="Deployment type: global, data_zone, regional"
    ),
) -> Dict[str, Any]:
    """Expose resolved pricing rates for a model/region/deployment-type without running a full analysis.

    This is useful for dashboards, CI scripts, and ad-hoc rate checks.
    """
    resolver = get_pricing_resolver()
    result = resolver.resolve(
        model_name=model,
        region=region,
        deployment_type=deployment_type,
    )
    return {
        "model": result.model_name,
        "region": result.region,
        "deployment_type": result.deployment_type,
        "payg_input_rate_per_million": round(result.payg_input_rate, 4),
        "payg_output_rate_per_million": round(result.payg_output_rate, 4),
        "ptu_hourly_rate": round(result.ptu_hourly_rate, 4),
        "pricing_source": result.source,
        "pricing_as_of": result.as_of.isoformat(),
        "pricing_currency": result.currency,
    }


@app.get("/api/discovery/auth-status")
def auth_status() -> Dict[str, Any]:
    """Return the authenticated user's identity (PRD §4.1 Auth Status Banner)."""
    try:
        _credential, user_info = authenticate()
        return {
            "authenticated": True,
            "display_name": user_info.display_name,
            "email": user_info.email,
            "tenant_id": user_info.tenant_id,
        }
    except Exception as e:
        return {
            "authenticated": False,
            "display_name": "",
            "email": "",
            "tenant_id": "",
            "error": str(e),
        }


@app.get("/api/discovery/subscriptions")
def subscriptions() -> List[Dict[str, Any]]:
    try:
        credential = get_azure_credential()
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please run `az login` in your terminal, then refresh this page. "
            f"Error: {e}",
        )
    try:
        subs = list_subscriptions(credential)
    except Exception as e:
        raise HTTPException(
            status_code=403,
            detail="Failed to list subscriptions. Ensure your account has Reader access to at least "
            "one Azure subscription. You can check access in the Azure Portal under "
            f"'Subscriptions'. Error: {e}",
        )
    if not subs:
        raise HTTPException(
            status_code=404,
            detail="No Azure subscriptions found for your account. "
            "Ensure you have at least one enabled subscription in this tenant.",
        )
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
    try:
        credential = get_azure_credential()
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    try:
        items = list_ai_accounts(credential, subscription_id)
    except Exception as e:
        raise HTTPException(
            status_code=403,
            detail="Failed to list AI Services accounts. Ensure you have Reader access to "
            f"the subscription. Error: {e}",
        )
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
    try:
        credential = get_azure_credential()
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    try:
        items = list_deployments(credential, subscription_id, resource_group, account_name)
    except Exception as e:
        raise HTTPException(
            status_code=403,
            detail="Failed to list deployments. Ensure you have Cognitive Services User or "
            "Reader role on this account, plus Monitoring Reader for metrics. "
            f"Error: {e}",
        )
    result: List[Dict[str, Any]] = []
    for dep in items:
        ptu_eligible = get_model_config(dep.model) is not None
        family = get_model_family(dep.model)
        entry: Dict[str, Any] = {
            "name": dep.name,
            "model": dep.model,
            "model_family": family,
            "sku_type": dep.sku_type,
            "sku_capacity": dep.sku_capacity,
            "ptu_eligible": ptu_eligible,
        }
        if not ptu_eligible:
            entry["ineligibility_reason"] = get_ineligibility_reason(family)
        result.append(entry)
    return result


@app.post("/api/discovery/refresh")
def refresh_discovery_cache() -> Dict[str, str]:
    """Invalidate the server-side discovery cache so the next fetch hits Azure ARM."""
    invalidate_discovery_cache()
    return {"status": "ok"}


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
            payg_input_rate_override=payload.payg_input_rate_override,
            payg_output_rate_override=payload.payg_output_rate_override,
            ptu_hourly_rate_override=payload.ptu_hourly_rate_override,
        )

    if not payload.subscription_id or not payload.resource_group or not payload.workspace:
        raise HTTPException(
            status_code=400,
            detail="subscription_id, resource_group, and workspace are required in live mode",
        )

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

    # PTU eligibility gate — reject non-PTU-eligible models
    if get_model_config(metrics.model_name) is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Model '{metrics.model_name}' does not support PTU. "
                "Analysis requires a PTU-eligible model (GPT-4o, GPT-4.1, GPT-5, "
                "o1, o3-mini, o4-mini, and their variants)."
            ),
        )

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
        payg_input_rate_override=payload.payg_input_rate_override,
        payg_output_rate_override=payload.payg_output_rate_override,
        ptu_hourly_rate_override=payload.ptu_hourly_rate_override,
    )


@app.post("/api/analyze-consolidation", response_model=ConsolidationResponse)
def analyze_consolidation(payload: ConsolidationRequest) -> ConsolidationResponse:
    """Analyze whether consolidating multiple same-model deployments onto shared PTU is cost-effective."""

    # ------------------------------------------------------------------
    # 1. Collect metrics for each deployment
    # ------------------------------------------------------------------
    all_metrics: List[DeploymentMetrics] = []

    if payload.mode == "demo":
        # In demo mode, the deployment names in the payload are ignored;
        # we generate 3 sibling deployments from the consolidation scenario.
        # Pick scenario based on focus topic heuristic: "Cost Reduction"
        # maps to CONSOLIDATE_WORTH_IT, everything else to NOT_WORTH_IT.
        scenario = (
            DemoScenario.CONSOLIDATE_WORTH_IT
            if payload.focus_topic == "Cost Reduction"
            else DemoScenario.CONSOLIDATE_NOT_WORTH_IT
        )
        all_metrics = generate_consolidation_demo_metrics(
            scenario,
            lookback_days=payload.lookback_days,
            granularity_minutes=payload.granularity_minutes,
        )
        # Apply time-window filter
        all_metrics = [
            _filter_metrics_by_window(m, payload.window_start, payload.window_end)
            for m in all_metrics
        ]
    else:
        # Live mode
        if not payload.subscription_id or not payload.resource_group or not payload.workspace:
            raise HTTPException(
                status_code=400,
                detail="subscription_id, resource_group, and workspace are required in live mode",
            )

        credential = get_azure_credential()
        for dep_name in payload.deployments:
            config = AnalysisConfig(
                resource_group=payload.resource_group,
                workspace=payload.workspace,
                deployment=dep_name,
                subscription_id=payload.subscription_id,
                lookback_days=payload.lookback_days,
                aggregation_interval_minutes=payload.granularity_minutes,
            )
            collector = MetricsCollector(credential, config)
            metrics = collector.collect()
            metrics = _filter_metrics_by_window(metrics, payload.window_start, payload.window_end)

            if metrics.tokens_per_minute is None and metrics.requests_per_minute is None:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": f"No metrics returned for deployment '{dep_name}'",
                        "hint": (
                            f"Deployment '{dep_name}' may have had no traffic "
                            f"in the last {payload.lookback_days} days."
                        ),
                    },
                )
            all_metrics.append(metrics)

    # ------------------------------------------------------------------
    # 2. Validate all deployments share the same model
    # ------------------------------------------------------------------
    model_names = {m.model_name for m in all_metrics}
    if len(model_names) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot consolidate deployments with different models: {sorted(model_names)}. "
                "PTU capacity is model-specific — only same-model deployments can share a PTU allocation."
            ),
        )

    sku_types = {m.deployment_info.sku_type for m in all_metrics if m.deployment_info is not None}
    if len(sku_types) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot consolidate deployments with different SKU types: {sorted(sku_types)}. "
                "PTU capacity is SKU-specific — only same-SKU deployments can share a PTU allocation."
            ),
        )

    if len(all_metrics) < 2:
        raise HTTPException(
            status_code=422,
            detail="Need at least 2 deployments to consolidate.",
        )

    # ------------------------------------------------------------------
    # 2b. Detect time-window mismatches and "already on PTU" status
    # ------------------------------------------------------------------
    consolidation_warnings: List[str] = []

    # Time-window mismatch: check if any deployment has a significantly
    # shorter time range than the overall span.
    all_starts = [m.start_time for m in all_metrics]
    all_ends = [m.end_time for m in all_metrics]
    global_start = min(all_starts)
    global_end = max(all_ends)
    global_span = (global_end - global_start).total_seconds()

    if global_span > 0:
        for m in all_metrics:
            dep_span = (m.end_time - m.start_time).total_seconds()
            # Flag if a deployment covers less than 80% of the global span
            if dep_span < global_span * 0.8:
                missing_start = m.start_time > global_start
                missing_end = m.end_time < global_end
                gaps: List[str] = []
                if missing_start:
                    gaps.append(
                        f"{global_start.strftime('%m/%d')}–{m.start_time.strftime('%m/%d')}"
                    )
                if missing_end:
                    gaps.append(f"{m.end_time.strftime('%m/%d')}–{global_end.strftime('%m/%d')}")
                gap_desc = " and ".join(gaps) if gaps else "some periods"
                consolidation_warnings.append(
                    f"Deployment '{m.deployment_name}' has no data for {gap_desc}. "
                    "Consolidation will treat missing periods as 0 TPM."
                )

    # "Already on PTU" detection
    all_on_ptu = all(
        m.deployment_info is not None and m.deployment_info.sku_type == "ProvisionedManaged"
        for m in all_metrics
    )
    if all_on_ptu:
        consolidation_warnings.append(
            "All selected deployments already use PTU (ProvisionedManaged). "
            "This analysis shows what their combined PAYG cost would be vs the current PTU spend."
        )

    # ------------------------------------------------------------------
    # 3. Merge into combined virtual deployment
    # ------------------------------------------------------------------
    combined_metrics = merge_deployment_metrics(all_metrics)

    # ------------------------------------------------------------------
    # 4. Run analysis engine on combined metrics
    # ------------------------------------------------------------------
    effective_lookback_days = max(
        1,
        int(
            max(
                1.0,
                (combined_metrics.end_time - combined_metrics.start_time).total_seconds()
                / 86_400.0,
            )
        ),
    )

    analysis_config = AnalysisConfig(
        resource_group=payload.resource_group or "demo-rg",
        workspace=payload.workspace or "demo-workspace",
        deployment=combined_metrics.deployment_name,
        subscription_id=payload.subscription_id,
        lookback_days=effective_lookback_days,
        aggregation_interval_minutes=payload.granularity_minutes,
    )
    engine = DecisionEngine(analysis_config)
    analysis = engine.analyze(combined_metrics)

    # ------------------------------------------------------------------
    # 5. Build base response using _serialize_analysis on combined metrics
    # ------------------------------------------------------------------
    region = normalize_region(payload.region)
    base_response = _serialize_analysis(
        metrics=combined_metrics,
        analysis=analysis,
        focus_topic=payload.focus_topic,
        lookback_days=effective_lookback_days,
        reservation_type=payload.reservation_type,
        baseline_percentile=payload.baseline_percentile,
        region=region,
        deployment_type=payload.deployment_type,
        baseline_ptu=payload.baseline_ptu,
        include_throttle=payload.include_throttle,
        payg_input_rate_override=payload.payg_input_rate_override,
        payg_output_rate_override=payload.payg_output_rate_override,
        ptu_hourly_rate_override=payload.ptu_hourly_rate_override,
    )

    # ------------------------------------------------------------------
    # 6. Compute per-deployment summaries and build consolidation summary
    # ------------------------------------------------------------------
    payg_blended_rate = base_response.cost_analysis["pricing"]["payg_blended_rate_per_million"]

    individual_summaries: List[IndividualDeploymentSummary] = []
    for m in all_metrics:
        tpm = m.tokens_per_minute
        p50 = m.time_to_first_byte_p50
        p95 = m.time_to_first_byte_p95
        individual_summaries.append(
            IndividualDeploymentSummary(
                name=m.deployment_name,
                avg_tpm=float(tpm.mean) if tpm else 0.0,
                peak_tpm=float(tpm.p95) if tpm else 0.0,
                throttling_rate_pct=float(m.throttling_rate * 100),
                total_requests=int(m.total_requests),
                latency_p50=float(p50.mean) if p50 else 0.0,
                latency_p95=float(p95.mean) if p95 else 0.0,
                payg_monthly_cost=compute_individual_payg_cost(m, payg_blended_rate),
            )
        )

    individual_payg_total = sum(s.payg_monthly_cost for s in individual_summaries)
    consolidated_hybrid_cost = base_response.cost_analysis["hybrid"]["hybrid_total"]
    savings = individual_payg_total - consolidated_hybrid_cost
    savings_pct = (savings / individual_payg_total * 100) if individual_payg_total > 0 else 0.0

    combined_tpm = combined_metrics.tokens_per_minute
    consolidation_summary = ConsolidationSummary(
        deployment_count=len(all_metrics),
        model_name=combined_metrics.model_name,
        deployment_type=payload.deployment_type,
        individual_deployments=individual_summaries,
        combined_avg_tpm=float(combined_tpm.mean) if combined_tpm else 0.0,
        combined_peak_tpm=float(combined_tpm.p95) if combined_tpm else 0.0,
        combined_throttling_rate_pct=float(combined_metrics.throttling_rate * 100),
        individual_payg_total=individual_payg_total,
        consolidated_hybrid_cost=consolidated_hybrid_cost,
        savings=savings,
        savings_pct=savings_pct,
        warnings=consolidation_warnings,
        all_on_ptu=all_on_ptu,
    )

    # ------------------------------------------------------------------
    # 7. Build per-deployment chart series for chart attribution
    # ------------------------------------------------------------------
    # Use the combined timestamps from the token chart (canonical axis)
    combined_ts_iso = base_response.charts.get("tokens", {}).get("timestamps", [])
    per_dep_charts = serialize_per_deployment_charts(all_metrics, combined_ts_iso)

    # Merge per_deployment data into existing chart sections
    enriched_charts = dict(base_response.charts)
    for chart_key in ("tokens", "requests", "tpm", "throttling"):
        if chart_key in enriched_charts and chart_key in per_dep_charts:
            enriched_charts[chart_key] = {
                **enriched_charts[chart_key],
                **per_dep_charts[chart_key],
            }

    # Latency chart section does not exist in single-deployment mode.
    # For consolidation, build it from the combined + per-deployment data.
    p50_combined = combined_metrics.time_to_first_byte_p50
    p95_combined = combined_metrics.time_to_first_byte_p95
    p99_combined = combined_metrics.time_to_first_byte_p99
    enriched_charts["latency"] = {
        "timestamps": combined_ts_iso,
        "combined": {
            "p50": [float(v) for v in p50_combined.values] if p50_combined else [],
            "p95": [float(v) for v in p95_combined.values] if p95_combined else [],
            "p99": [float(v) for v in p99_combined.values] if p99_combined else [],
        },
        **per_dep_charts.get("latency", {}),
    }

    # ------------------------------------------------------------------
    # 8. Return ConsolidationResponse (extends AnalyzeResponse)
    # ------------------------------------------------------------------
    response_data = base_response.model_dump()
    response_data["charts"] = enriched_charts
    return ConsolidationResponse(
        **response_data,
        consolidation_summary=consolidation_summary,
    )


# ---------------------------------------------------------------------------
# Static file serving (production)
# ---------------------------------------------------------------------------
# Lightweight deployment preview (Phase 3 — pre-analysis TPM/throttle)
# ---------------------------------------------------------------------------


class DeploymentPreview(BaseModel):
    """Lightweight preview stats for a single deployment."""

    name: str
    avg_tpm: float
    throttling_rate_pct: float


@app.get("/api/deployments/preview", response_model=List[DeploymentPreview])
def deployment_preview(
    mode: str = Query("demo"),
    deployments: str = Query("", description="Comma-separated deployment names"),
    subscription_id: Optional[str] = Query(None),
    resource_group: Optional[str] = Query(None),
    workspace: Optional[str] = Query(None),
    lookback_days: int = Query(7),
    focus_topic: str = Query("Cost Reduction"),
) -> List[DeploymentPreview]:
    """Return lightweight TPM and throttle preview for deployments.

    In demo mode, generates preview data from the consolidation demo scenario.
    In live mode, collects minimal metrics for each deployment.
    """
    if mode == "demo":
        scenario = (
            DemoScenario.CONSOLIDATE_WORTH_IT
            if focus_topic == "Cost Reduction"
            else DemoScenario.CONSOLIDATE_NOT_WORTH_IT
        )
        all_metrics = generate_consolidation_demo_metrics(
            scenario,
            lookback_days=lookback_days,
            granularity_minutes=5,  # coarse granularity for speed
        )
        results: List[DeploymentPreview] = []
        for m in all_metrics:
            avg_tpm = float(m.tokens_per_minute.mean) if m.tokens_per_minute else 0.0
            throttle_rate = m.throttling_rate * 100 if m.throttled_requests else 0.0
            results.append(
                DeploymentPreview(
                    name=m.deployment_name,
                    avg_tpm=round(avg_tpm, 1),
                    throttling_rate_pct=round(throttle_rate, 1),
                )
            )
        return results

    # Live mode
    if not subscription_id or not resource_group or not workspace:
        raise HTTPException(
            status_code=400,
            detail="subscription_id, resource_group, and workspace are required in live mode",
        )

    dep_names = [d.strip() for d in deployments.split(",") if d.strip()]
    if not dep_names:
        raise HTTPException(status_code=400, detail="At least one deployment name is required")

    credential = get_azure_credential()
    results = []
    for dep_name in dep_names:
        try:
            config = AnalysisConfig(
                resource_group=resource_group,
                workspace=workspace,
                deployment=dep_name,
                subscription_id=subscription_id,
                lookback_days=lookback_days,
                aggregation_interval_minutes=5,  # coarse for speed
            )
            collector = MetricsCollector(credential, config)
            metrics = collector.collect()
            avg_tpm = float(metrics.tokens_per_minute.mean) if metrics.tokens_per_minute else 0.0
            throttle_rate = metrics.throttling_rate * 100 if metrics.throttled_requests else 0.0
            results.append(
                DeploymentPreview(
                    name=dep_name,
                    avg_tpm=round(avg_tpm, 1),
                    throttling_rate_pct=round(throttle_rate, 1),
                )
            )
        except Exception:
            # If a deployment fails to fetch metrics, return zero values
            results.append(
                DeploymentPreview(
                    name=dep_name,
                    avg_tpm=0.0,
                    throttling_rate_pct=0.0,
                )
            )
    return results


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
