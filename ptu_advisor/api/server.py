from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from starlette.responses import JSONResponse

from ptu_advisor import __version__
from ptu_advisor.analysis.engine import DecisionEngine
from ptu_advisor.auth import get_azure_credential
from ptu_advisor.config import (
    AnalysisConfig,
    get_ineligibility_reason,
    get_model_config,
    get_model_family,
)
from ptu_advisor.cost.cache import (
    build_cache_impact,
    calculate_cache_aware_spillover,
    generate_cache_aware_cost_curves,
)
from ptu_advisor.cost.calculator import (
    calculate_break_even_for_fixed_ptu,
    calculate_spillover_cost,
)
from ptu_advisor.cost.price_resolver import get_pricing_resolver
from ptu_advisor.cost.pricing import (
    DEPLOYMENT_TYPE_CONFIGS,
    REGION_CONFIGS,
    get_deployment_config,
    get_deployment_type,
    get_region_config,
    normalize_region,
)
from ptu_advisor.demo import (
    FOCUS_TOPICS,
    DemoScenario,
    generate_consolidation_demo_metrics,
    generate_demo_metrics,
)
from ptu_advisor.discovery import (
    authenticate,
    invalidate_discovery_cache,
    list_ai_accounts,
    list_deployments,
    list_subscriptions,
)
from ptu_advisor.metrics.collector import MetricsCollector
from ptu_advisor.metrics.merge import (
    compute_individual_payg_cost,
    merge_deployment_metrics,
    serialize_per_deployment_charts,
)
from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries


logger = logging.getLogger(__name__)


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
        "1-Year Commitment (Estimated 69% off)",
    ] = "Monthly Commitment (Estimated 64% off)"
    baseline_percentile: Optional[float] = Field(default=None, ge=0, le=95)
    baseline_ptu: Optional[int] = Field(default=None, ge=0)
    region: str = "eastus"
    deployment_type: Literal["global", "data_zone", "regional"] = "global"
    include_throttle: bool = False

    payg_input_rate_override: Optional[float] = Field(default=None, ge=0)
    payg_output_rate_override: Optional[float] = Field(default=None, ge=0)
    ptu_hourly_rate_override: Optional[float] = Field(default=None, ge=0)
    cache_mode: Literal["auto", "disabled", "override"] = "auto"
    cache_match_rate_override_pct: Optional[float] = Field(default=None, ge=0, le=100)
    cached_input_rate_override: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_cache_override(self) -> "AnalyzeRequest":
        if self.cache_mode == "override" and self.cache_match_rate_override_pct is None:
            raise ValueError(
                "cache_match_rate_override_pct is required when cache_mode is override"
            )
        return self


class TokenSnapshotRequest(BaseModel):
    """Request body for the GBB-style token-usage snapshot export.

    Mirrors the PowerShell ``az monitor metrics list`` call that GBB
    distributes to customers (InputTokens, OutputTokens, and the
    AzureOpenAIContextTokensCacheMatchRate metric over a 7-day window
    at 1-minute granularity).
    """

    mode: Literal["demo", "live"] = "live"
    focus_topic: str = "Cost Reduction"
    days: int = Field(default=7, ge=1, le=30)
    interval: Literal["PT1M", "PT5M", "PT15M", "PT1H"] = "PT1M"

    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    workspace: Optional[str] = None
    deployment: Optional[str] = None
    cache_mode: Literal["auto", "disabled", "override"] = "auto"
    cache_match_rate_override_pct: Optional[float] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_cache_override(self) -> "TokenSnapshotRequest":
        if self.cache_mode == "override" and self.cache_match_rate_override_pct is None:
            raise ValueError(
                "cache_match_rate_override_pct is required when cache_mode is override"
            )
        return self


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
    cache_mode: Literal["auto", "disabled", "override"] = "auto"
    cache_match_rate_override_pct: Optional[float] = Field(default=None, ge=0, le=100)
    cached_input_rate_override: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_cache_override(self) -> "ConsolidationRequest":
        if self.cache_mode == "override" and self.cache_match_rate_override_pct is None:
            raise ValueError(
                "cache_match_rate_override_pct is required when cache_mode is override"
            )
        return self


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


@asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _startup_warm_pricing_cache()
    try:
        yield
    finally:
        _shutdown_pricing_cache()


app = FastAPI(title="PTU Advisor API", version=__version__, lifespan=_app_lifespan)


@app.middleware("http")
async def require_api_authentication(request: Request, call_next):
    auth_mode = os.getenv("PTU_ADVISOR_AUTH_MODE", "local").strip().lower()
    is_protected_api = request.url.path.startswith("/api/") and request.url.path != "/api/health"

    if auth_mode not in {"local", "easy_auth"}:
        return JSONResponse(
            status_code=500,
            content={"detail": "Server authentication mode is invalid."},
        )
    if auth_mode == "easy_auth" and is_protected_api:
        if not os.getenv("WEBSITE_INSTANCE_ID"):
            return JSONResponse(
                status_code=500,
                content={"detail": "Easy Auth mode requires Azure App Service hosting."},
            )
        if not request.headers.get("X-MS-CLIENT-PRINCIPAL-ID"):
            return JSONResponse(status_code=401, content={"detail": "Authentication required."})

    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _startup_warm_pricing_cache() -> None:
    """Start pricing refresh off the application readiness path."""
    resolver = get_pricing_resolver()
    resolver.start_background_warmup()


def _shutdown_pricing_cache() -> None:
    """Stop pricing refresh during application shutdown."""
    get_pricing_resolver().stop_background_warmup()


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
        cache_coverage_pct=metrics.cache_coverage_pct,
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
        "cache_match_rate",
        "active_tokens",
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
    cached_prompt_values: Optional[List[float]] = None,
    payg_cached_input_rate: Optional[float] = None,
    interval_minutes: int = 1,
) -> Dict[str, Any]:
    """Aggregate interval-level token data into daily cost bars."""
    from collections import defaultdict

    daily_input: Dict[str, float] = defaultdict(float)
    daily_cached_input: Dict[str, float] = defaultdict(float)
    daily_output: Dict[str, float] = defaultdict(float)

    interval_minutes = max(1, interval_minutes)
    cached_values = cached_prompt_values or [0.0] * len(timestamps)
    cached_rate = (
        payg_cached_input_rate if payg_cached_input_rate is not None else payg_input_rate
    )
    for ts, p_tok, c_tok, cached_tok in zip(
        timestamps, prompt_values, completion_values, cached_values
    ):
        day = ts[:10]  # "2026-03-01T14:00:00Z" -> "2026-03-01"
        bounded_cached = min(float(p_tok), max(0.0, float(cached_tok)))
        daily_input[day] += (float(p_tok) - bounded_cached) * interval_minutes
        daily_cached_input[day] += bounded_cached * interval_minutes
        daily_output[day] += c_tok * interval_minutes

    dates = sorted(daily_input.keys())
    input_costs = [
        (daily_input[d] / 1_000_000) * payg_input_rate
        + (daily_cached_input[d] / 1_000_000) * cached_rate
        for d in dates
    ]
    cached_input_costs = [
        (daily_cached_input[d] / 1_000_000) * cached_rate for d in dates
    ]
    output_costs = [(daily_output[d] / 1_000_000) * payg_output_rate for d in dates]
    total_costs = [ic + oc for ic, oc in zip(input_costs, output_costs)]
    avg_daily = sum(total_costs) / len(total_costs) if total_costs else 0.0

    return {
        "dates": dates,
        "input_cost": [round(v, 2) for v in input_costs],
        "cached_input_cost": [round(v, 2) for v in cached_input_costs],
        "output_cost": [round(v, 2) for v in output_costs],
        "total_cost": [round(v, 2) for v in total_costs],
        "avg_daily_cost": round(avg_daily, 2),
    }


def _infer_interval_minutes(series: Optional[TimeSeries]) -> int:
    if series is None or len(series.timestamps) < 2:
        return 1
    deltas = [
        (current - previous).total_seconds() / 60.0
        for previous, current in zip(series.timestamps, series.timestamps[1:])
        if current > previous
    ]
    return max(1, int(round(float(np.median(deltas))))) if deltas else 1


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
    avg_active_prompt_tpm: float = 0.0,
    avg_cached_prompt_tpm: float = 0.0,
    avg_completion_tpm: float = 0.0,
    payg_cached_input_rate: float = 0.0,
    cache_source: str = "unavailable",
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
    if cache_source not in ("unavailable", "disabled"):
        payg_lines[2:2] = [
            f"active_input_cost = {avg_active_prompt_tpm:,.0f} TPM × 43,200 min ÷ 1M × ${payg_input_rate:.2f}",
            f"cached_input_cost = {avg_cached_prompt_tpm:,.0f} TPM × 43,200 min ÷ 1M × ${payg_cached_input_rate:.2f}",
            f"output_cost = {avg_completion_tpm:,.0f} TPM × 43,200 min ÷ 1M × ${payg_output_rate:.2f}",
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
        "cache_note = cached prompt tokens reduce utilization; fixed PTU cost changes only when selected PTU count changes",
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
    cache_mode: Literal["auto", "disabled", "override"] = "auto",
    cache_match_rate_override_pct: Optional[float] = None,
    cached_input_rate_override: Optional[float] = None,
) -> AnalyzeResponse:
    requested_baseline_ptu = baseline_ptu
    tpm = metrics.tokens_per_minute
    throttled = metrics.throttled_requests
    prompt = metrics.prompt_tokens
    completion = metrics.completion_tokens
    successful = metrics.successful_requests
    requests = metrics.requests_per_minute
    p50 = metrics.time_to_first_byte_p50
    p95 = metrics.time_to_first_byte_p95
    p99 = metrics.time_to_first_byte_p99
    cache_match = metrics.cache_match_rate
    active_tokens = metrics.active_tokens
    metrics_interval_minutes = _infer_interval_minutes(prompt or tpm)

    lookback_days = max(1, lookback_days)
    avg_tpm = float(tpm.mean) if tpm else 0.0
    peak_tpm = float(tpm.p95) if tpm else 0.0
    throttle_rate_pct = float(metrics.throttling_rate * 100)

    # Derive daily token volume from TPM (the authoritative throughput rate)
    avg_daily_tokens = avg_tpm * 1440  # tokens per minute × minutes per day
    total_tokens = avg_daily_tokens * max(1, lookback_days)
    monthly_tokens = avg_daily_tokens * 30
    has_cost_data = monthly_tokens > 0

    # ── Resolve pricing via layered strategy ─────────────────────────────
    resolver = get_pricing_resolver()
    pricing_model_name = metrics.model_name
    if metrics.deployment_info and metrics.deployment_info.model_version:
        pricing_model_name = f"{metrics.model_name}-{metrics.deployment_info.model_version}"
    pricing = resolver.resolve(
        model_name=pricing_model_name,
        region=region,
        deployment_type=deployment_type,
        payg_input_override=payg_input_rate_override,
        payg_output_override=payg_output_rate_override,
        payg_cached_input_override=cached_input_rate_override,
        ptu_hourly_override=ptu_hourly_rate_override,
    )
    payg_input_rate = pricing.payg_input_rate
    payg_cached_input_rate = pricing.payg_cached_input_rate
    payg_output_rate = pricing.payg_output_rate
    # Derive output ratio from actual prompt vs completion data
    prompt_total = float(prompt.total) if prompt else 0.0
    completion_total = float(completion.total) if completion else 0.0
    token_sum = prompt_total + completion_total
    complete_token_shape = bool(
        prompt
        and completion
        and prompt.timestamps == completion.timestamps
        and len(prompt.values) == len(completion.values)
    )
    output_ratio = (
        completion_total / token_sum if complete_token_shape and token_sum > 0 else 0.30
    )
    payg_blended_rate = (payg_input_rate * (1 - output_ratio)) + (
        payg_output_rate * output_ratio
    )

    # Look up model-specific PTU capacity and output multiplier
    model_cfg = get_model_config(metrics.model_name)
    input_tpm_per_ptu = model_cfg.input_tpm_per_ptu if model_cfg else 2500
    model_output_multiplier = model_cfg.output_ratio if model_cfg else 3
    region_cfg = get_region_config(region)
    deployment_cfg = get_deployment_config(deployment_type)
    deployment_kind = get_deployment_type(deployment_type)
    # Use the resolved PTU hourly rate (live/cached/fallback/manual)
    # instead of the old base_hourly_rate * multiplier formula
    ptu_hourly = pricing.ptu_hourly_rate
    ptu_increment = deployment_cfg.increment
    min_ptu = deployment_cfg.default_min_ptu
    if model_cfg:
        if deployment_kind.value == "regional":
            min_ptu = model_cfg.regional_min_ptu
            ptu_increment = model_cfg.regional_increment
        else:
            min_ptu = model_cfg.global_min_ptu
            ptu_increment = model_cfg.global_increment
    cache_impact = build_cache_impact(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_match_rate=cache_match,
        active_tokens=active_tokens,
        output_multiplier=model_output_multiplier,
        input_tpm_per_ptu=input_tpm_per_ptu,
        min_ptu=min_ptu,
        ptu_increment=ptu_increment,
        cache_mode=cache_mode,
        override_pct=cache_match_rate_override_pct,
        interval_minutes=metrics_interval_minutes,
        coverage_pct_override=metrics.cache_coverage_pct,
        source_override=metrics.cache_source,  # type: ignore[arg-type]
        missing_evidence_as_zero=metrics.cache_missing_as_zero,
    )
    # CacheImpact values are input-token-equivalent TPM. Convert capacity back
    # to raw TPM for chart labels while using normalized capacity for sizing.
    effective_mult = (1 - output_ratio) + output_ratio * model_output_multiplier
    adjusted_effective_mult = (
        cache_impact.cache_adjusted_normalized_avg_tpm / avg_tpm
        if avg_tpm > 0
        else effective_mult
    )
    ptu_capacity = input_tpm_per_ptu / max(adjusted_effective_mult, 0.0001)
    term = _pricing_terms(reservation_type)
    reservation_discount = float(term["discount_factor"])
    reservation_discount_pct = int(term["discount_pct"])

    ptu_monthly_rate = ptu_hourly * 720 * reservation_discount

    minutes_per_month = 43_200
    avg_prompt_tpm = float(np.mean(cache_impact.prompt_tokens)) if cache_impact.prompt_tokens else 0.0
    avg_completion_tpm = (
        float(np.mean(cache_impact.completion_tokens)) if cache_impact.completion_tokens else 0.0
    )
    observed_avg_cached_prompt_tpm = (
        float(np.mean(cache_impact.cached_prompt_tokens))
        if cache_impact.cached_prompt_tokens
        else 0.0
    )
    avg_cached_prompt_tpm = observed_avg_cached_prompt_tpm if cache_impact.applied else 0.0
    avg_active_prompt_tpm = max(0.0, avg_prompt_tpm - avg_cached_prompt_tpm)
    no_cache_payg = (
        avg_prompt_tpm * minutes_per_month / 1_000_000 * payg_input_rate
        + avg_completion_tpm * minutes_per_month / 1_000_000 * payg_output_rate
    )
    payg_base = (
        avg_active_prompt_tpm * minutes_per_month / 1_000_000 * payg_input_rate
        + avg_cached_prompt_tpm
        * minutes_per_month
        / 1_000_000
        * payg_cached_input_rate
        + avg_completion_tpm * minutes_per_month / 1_000_000 * payg_output_rate
    )
    if not complete_token_shape:
        no_cache_payg = (monthly_tokens / 1_000_000) * payg_blended_rate
        payg_base = no_cache_payg
    # Effective blended rate keeps the existing raw-TPM cost-curve contract.
    payg_blended_rate = payg_base * 1_000_000 / monthly_tokens if monthly_tokens > 0 else 0.0
    payg_rate_per_1k = payg_blended_rate / 1000
    throttle_rate = float(metrics.throttling_rate)
    if throttle_rate > 0.01:
        retry_overhead = payg_base * (throttle_rate / max(0.0001, (1 - throttle_rate)))
        opportunity_multiplier = min(5.0, 1.0 + (throttle_rate * 20))
        throttle_impact = retry_overhead * opportunity_multiplier
    else:
        throttle_impact = 0.0
    payg_total = (payg_base + throttle_impact) if include_throttle else payg_base

    has_token_shape = bool(cache_impact.adjusted_normalized_tpm)
    tpm_values = (
        list(cache_impact.adjusted_normalized_tpm)
        if has_token_shape
        else (list(tpm.values) if tpm else [])
    )
    normalized_requested_ptu = (
        max(
            min_ptu,
            int(np.ceil(baseline_ptu / ptu_increment) * ptu_increment),
        )
        if baseline_ptu is not None
        else None
    )
    selected_ptu = normalized_requested_ptu or (
        cache_impact.cache_aware_recommended_ptu if has_token_shape else min_ptu
    )
    if has_token_shape:
        spillover = calculate_cache_aware_spillover(
            impact=cache_impact,
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=input_tpm_per_ptu,
            ptu_hourly_rate=ptu_hourly,
            reservation_discount=reservation_discount,
            payg_input_rate_per_million=payg_input_rate,
            payg_output_rate_per_million=payg_output_rate,
        )
    else:
        spillover = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=baseline_percentile,
            ptu_capacity_per_unit=ptu_capacity,
            ptu_hourly_rate=ptu_hourly,
            payg_rate_per_1k=payg_rate_per_1k,
            reservation_discount=reservation_discount,
            baseline_ptu_override=selected_ptu,
            min_ptu=min_ptu,
            ptu_increment=ptu_increment,
        )
        spillover["avg_spillover_normalized_tpm"] = spillover["avg_spillover_tpm"]

    baseline_tpm = float(selected_ptu * ptu_capacity)
    baseline_ptu = int(spillover["baseline_ptu"])
    ptu_capacity_tpm = float(baseline_tpm)
    spillover_tokens_monthly = float(spillover["spillover_tokens_monthly"])
    spillover_cost = float(spillover["spillover_cost"])
    ptu_baseline_cost = float(spillover["ptu_monthly_cost"])
    hybrid_total = float(spillover["total_hybrid_cost"])
    spillover_pct = float(spillover["spillover_pct"])
    avg_spillover_tpm = float(spillover["avg_spillover_normalized_tpm"])

    if has_token_shape:
        ptu_needed_full = cache_impact.cache_aware_recommended_ptu
    else:
        ptu_needed_full = (
            max(min_ptu, int((peak_tpm * 1.2 / ptu_capacity) + 0.5))
            if peak_tpm > 0
            else min_ptu
        )
        ptu_needed_full = (
            (ptu_needed_full + (ptu_increment - 1)) // ptu_increment
        ) * ptu_increment
    ptu_monthly_full = ptu_needed_full * ptu_hourly * 24 * 30
    ptu_committed_cost = ptu_monthly_full * reservation_discount

    savings = payg_total - hybrid_total
    savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0.0

    spillover_blended_rate = (
        payg_input_rate * (1 - output_ratio) + payg_output_rate * output_ratio
    )

    payg_at_avg = avg_tpm * 43_200 / 1_000_000 * payg_blended_rate

    token_timestamps = (
        [ts.isoformat() for ts in prompt.timestamps]
        if complete_token_shape and prompt
        else []
    )

    token_total_values: List[float] = []
    if complete_token_shape and prompt and completion:
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
    max_positive_ptu: Optional[int] = None

    if payg_total > 0 and tpm_values:
        # Upper bound for the sweep: enough PTU to cover P99 × 1.3
        p99_tpm_sweep = float(np.percentile(tpm_values, 99))
        sweep_ceiling_raw = p99_tpm_sweep * 1.3 / input_tpm_per_ptu
        sweep_ceiling = max(
            min_ptu, int(np.ceil(sweep_ceiling_raw / ptu_increment) * ptu_increment)
        )

        # Walk from min_ptu up to sweep_ceiling and track the lowest-cost
        # PTU value that still delivers > 5% savings.
        best_positive_ptu: Optional[int] = None
        best_positive_hybrid: Optional[float] = None

        for candidate_ptu in range(min_ptu, sweep_ceiling + ptu_increment, ptu_increment):
            if has_token_shape:
                candidate = calculate_cache_aware_spillover(
                    impact=cache_impact,
                    selected_ptu=candidate_ptu,
                    ptu_capacity_per_unit=input_tpm_per_ptu,
                    ptu_hourly_rate=ptu_hourly,
                    reservation_discount=reservation_discount,
                    payg_input_rate_per_million=payg_input_rate,
                    payg_output_rate_per_million=payg_output_rate,
                )
            else:
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
        max_ptu_raw = p99_tpm * 1.3 / input_tpm_per_ptu
        max_baseline_ptu = max(
            default_baseline_ptu * 2,
            int(np.ceil(max_ptu_raw / ptu_increment) * ptu_increment),
        )
    else:
        max_baseline_ptu = default_baseline_ptu * 4

    max_viable_baseline_ptu = max_positive_ptu if payg_total > 0 else None

    # If caller didn't specify baseline PTU, evaluate Financial Decision using
    # the computed default baseline so first render is recommendation-focused.
    if requested_baseline_ptu is None and default_baseline_ptu != baseline_ptu:
        if has_token_shape:
            spillover = calculate_cache_aware_spillover(
                impact=cache_impact,
                selected_ptu=default_baseline_ptu,
                ptu_capacity_per_unit=input_tpm_per_ptu,
                ptu_hourly_rate=ptu_hourly,
                reservation_discount=reservation_discount,
                payg_input_rate_per_million=payg_input_rate,
                payg_output_rate_per_million=payg_output_rate,
            )
        else:
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
            spillover["avg_spillover_normalized_tpm"] = spillover["avg_spillover_tpm"]

        baseline_tpm = float(default_baseline_ptu * ptu_capacity)
        baseline_ptu = int(spillover["baseline_ptu"])
        ptu_capacity_tpm = float(baseline_tpm)
        spillover_tokens_monthly = float(spillover["spillover_tokens_monthly"])
        spillover_cost = float(spillover["spillover_cost"])
        ptu_baseline_cost = float(spillover["ptu_monthly_cost"])
        hybrid_total = float(spillover["total_hybrid_cost"])
        spillover_pct = float(spillover["spillover_pct"])
        avg_spillover_tpm = float(spillover["avg_spillover_normalized_tpm"])

        savings = payg_total - hybrid_total
        savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0.0

    # Curves must use the final commitment, which can change during the
    # recommendation-aware default PTU sweep above.
    curve_max_tpm = (
        max(peak_tpm * 2, avg_tpm * 3, ptu_capacity_tpm * 2, 100_000) if peak_tpm > 0 else 200_000
    )
    cost_curves_df, break_even_tpm, upper_break_even_tpm = generate_cache_aware_cost_curves(
        selected_ptu=baseline_ptu,
        ptu_capacity_raw_tpm=ptu_capacity_tpm,
        ptu_monthly_cost=ptu_baseline_cost,
        payg_rate_per_raw_million=payg_blended_rate,
        spillover_rate_per_raw_million=spillover_blended_rate,
        max_tpm=curve_max_tpm,
    )
    if break_even_tpm is not None:
        break_even_reason = "exists"
    else:
        final_diff = (
            float(cost_curves_df.iloc[-1]["payg_monthly"])
            - float(cost_curves_df.iloc[-1]["ptu_spill_monthly"])
            if not cost_curves_df.empty
            else 0.0
        )
        break_even_reason = (
            "ptu_always_cheaper" if final_diff > 0 else "ptu_always_more_expensive"
        )

    # ── Cost-driven recommendation (reacts to slider PTU value) ──────────
    if not has_cost_data:
        cost_recommendation = "insufficient_data"
    elif payg_total > 0 and hybrid_total > 0:
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
    if not has_cost_data:
        safety_verdict = "insufficient_data"
    elif savings_margin_pct <= 0:
        safety_verdict = "not_justified"
    elif savings_margin_pct < 5 or spillover_pct > 25 or capacity_coverage_pct < 75:
        safety_verdict = "efficient_but_risky"
    else:
        safety_verdict = "safe"

    no_cache_impact = build_cache_impact(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_match_rate=cache_match,
        active_tokens=active_tokens,
        output_multiplier=model_output_multiplier,
        input_tpm_per_ptu=input_tpm_per_ptu,
        min_ptu=min_ptu,
        ptu_increment=ptu_increment,
        cache_mode="disabled",
        interval_minutes=metrics_interval_minutes,
    )
    if no_cache_impact.adjusted_normalized_tpm:
        no_cache_spillover = calculate_cache_aware_spillover(
            impact=no_cache_impact,
            selected_ptu=baseline_ptu,
            ptu_capacity_per_unit=input_tpm_per_ptu,
            ptu_hourly_rate=ptu_hourly,
            reservation_discount=reservation_discount,
            payg_input_rate_per_million=payg_input_rate,
            payg_output_rate_per_million=payg_output_rate,
        )
        no_cache_capacity_tpm = baseline_ptu * input_tpm_per_ptu / max(effective_mult, 0.0001)
    else:
        no_cache_spillover = dict(spillover)
        no_cache_capacity_tpm = ptu_capacity_tpm
    no_cache_throttle = (
        throttle_impact * no_cache_payg / payg_base
        if include_throttle and payg_base > 0
        else 0.0
    )
    no_cache_payg_total = no_cache_payg + no_cache_throttle
    no_cache_hybrid_total = float(no_cache_spillover["total_hybrid_cost"])
    no_cache_savings = no_cache_payg_total - no_cache_hybrid_total
    no_cache_savings_pct = (
        no_cache_savings / no_cache_payg_total * 100 if no_cache_payg_total > 0 else 0.0
    )
    no_cache_recommendation = (
        "insufficient_data"
        if not has_cost_data
        else "ptu_recommended"
        if no_cache_savings_pct > 5
        else "ptu_not_recommended"
        if no_cache_savings_pct < -5
        else "borderline"
    )
    no_cache_spillover_pct = float(no_cache_spillover["spillover_pct"])
    no_cache_coverage_pct = 100.0 - no_cache_spillover_pct
    no_cache_safety_verdict = (
        "insufficient_data"
        if not has_cost_data
        else "not_justified"
        if no_cache_savings_pct <= 0
        else "efficient_but_risky"
        if no_cache_savings_pct < 5
        or no_cache_spillover_pct > 25
        or no_cache_coverage_pct < 75
        else "safe"
    )
    no_cache_break_even_tpm = calculate_break_even_for_fixed_ptu(
        selected_ptu=baseline_ptu,
        ptu_capacity_per_unit=no_cache_capacity_tpm / baseline_ptu,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=spillover_blended_rate,
        reservation_discount=reservation_discount,
    )
    no_cache_upper_break_even_tpm = None

    if not has_cost_data:
        break_even_tpm = None
        upper_break_even_tpm = None
        no_cache_break_even_tpm = None
        no_cache_upper_break_even_tpm = None
        break_even_reason = "insufficient_data"
        break_even_message = (
            "Insufficient traffic data to calculate an economic break-even. "
            "Collect token usage before comparing PAYG and PTU commitments."
        )
    elif break_even_tpm and upper_break_even_tpm and avg_tpm > 0:
        if break_even_tpm <= avg_tpm <= upper_break_even_tpm:
            range_position = "inside"
            range_signal = "favors PTU"
        else:
            range_position = "outside"
            range_signal = "favors PAYG"
        break_even_message = (
            f"Economic break-even range for {baseline_ptu} PTU is "
            f"{break_even_tpm:,.0f}-{upper_break_even_tpm:,.0f} TPM. "
            f"Your average TPM ({avg_tpm:,.0f}) is {range_position} that range, "
            f"so the economic signal {range_signal}. Final recommendation: "
            f"{cost_recommendation.replace('_', ' ')} with safety verdict "
            f"'{safety_verdict}'."
        )
    elif break_even_tpm and break_even_tpm > 0 and avg_tpm > 0:
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

    if not has_cost_data:
        dynamic_summary = "Insufficient traffic data for a PTU or PAYG recommendation."
        dynamic_explanation = (
            "No token usage was observed in the selected analysis window, so monthly cost, "
            "savings, and break-even comparisons are not decision-ready."
        )
        dynamic_what_would_change = (
            "Collect representative token traffic, then rerun the analysis."
        )
    elif cost_recommendation == "ptu_recommended":
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

    dynamic_confidence = (
        0.0
        if not has_cost_data
        else float(min(0.98, max(0.55, 0.55 + (abs(savings_pct) / 100))))
    )

    financial_score = (
        "insufficient"
        if not has_cost_data
        else "positive"
        if savings_pct > 5
        else "negative"
        if savings_pct < -5
        else "neutral"
    )
    spillover_score = (
        "insufficient"
        if not has_cost_data
        else "positive"
        if spillover_pct <= 20
        else "negative"
        if spillover_pct >= 40
        else "neutral"
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
        if not has_cost_data and ("capacity" in lowered or "predict" in lowered):
            dim["score"] = "insufficient"
            dim["summary"] = "Insufficient traffic data for a financial capacity decision."
            dim["explanation"] = (
                "No token usage was observed in the selected analysis window."
            )
            dim["is_positive"] = False
            dim["confidence"] = 0.0
        elif "capacity" in lowered:
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
            "cache_match_rate": {
                "avg_pct": cache_impact.avg_match_rate_pct,
                "p95_pct": cache_impact.p95_match_rate_pct,
                "available": cache_impact.source != "unavailable",
                "source": cache_impact.source,
                "quality": cache_impact.quality,
                "coverage_pct": cache_impact.coverage_pct,
                "cached_prompt_tokens": cache_impact.total_cached_prompt_tokens,
                "active_prompt_tokens": cache_impact.total_active_prompt_tokens,
                "active_tokens_observed": cache_impact.active_tokens_observed,
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
                "cache_match_rate": _series_payload(cache_match),
                "active_tokens": _series_payload(active_tokens),
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
                    cached_prompt_values=(
                        cache_impact.cached_prompt_tokens if cache_impact.applied else None
                    ),
                    payg_cached_input_rate=payg_cached_input_rate,
                    interval_minutes=metrics_interval_minutes,
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
            "prompt_cache": {
                "timestamps": [ts.isoformat() for ts in cache_impact.timestamps],
                "match_rate_pct": cache_impact.match_rate_pct,
                "prompt_tokens": cache_impact.prompt_tokens,
                "cached_prompt_tokens": cache_impact.cached_prompt_tokens,
                "active_prompt_tokens": cache_impact.active_prompt_tokens,
                "source": cache_impact.source,
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
                "upper_break_even_tpm": (
                    float(upper_break_even_tpm) if upper_break_even_tpm else None
                ),
                "break_even_reason": break_even_reason,
                "ptu_capacity_tpm": float(ptu_capacity_tpm),
                "avg_tpm": float(avg_tpm),
                "selected_ptu": baseline_ptu,
                "payg_at_avg": float(payg_at_avg),
                "hybrid_at_avg": float(hybrid_total),
            },
        },
        cost_analysis={
            "status": "ready" if has_cost_data else "insufficient_data",
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
                "payg_cached_input_rate_per_million": payg_cached_input_rate,
                "cached_input_pricing_source": pricing.cached_input_source,
                "payg_output_rate_per_million": payg_output_rate,
                "output_ratio": round(output_ratio, 4),
                "ptu_hourly_rate": ptu_hourly,
                "ptu_pricing_source": pricing.ptu_pricing_source,
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
                "no_cache_payg_monthly": float(no_cache_payg),
                "payg_cache_savings": float(no_cache_payg - payg_base),
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
                "upper_break_even_tpm": (
                    float(upper_break_even_tpm) if upper_break_even_tpm else None
                ),
                "cheaper_strategy": (
                    "PTU + Spillover"
                    if has_cost_data and savings > 0
                    else "PAYG"
                    if has_cost_data
                    else None
                ),
            },
            "no_cache_comparison": {
                "payg_total": float(no_cache_payg_total),
                "ptu_baseline_cost": float(no_cache_spillover["ptu_monthly_cost"]),
                "spillover_cost": float(no_cache_spillover["spillover_cost"]),
                "hybrid_total": no_cache_hybrid_total,
                "savings": float(no_cache_savings),
                "savings_pct": float(no_cache_savings_pct),
                "recommendation": no_cache_recommendation,
                "break_even_tpm": no_cache_break_even_tpm,
                "upper_break_even_tpm": no_cache_upper_break_even_tpm,
                "commitment_safety": {
                    "savings_margin_pct": round(no_cache_savings_pct, 1),
                    "spillover_pct": round(no_cache_spillover_pct, 1),
                    "capacity_coverage_pct": round(no_cache_coverage_pct, 1),
                    "safety_verdict": no_cache_safety_verdict,
                },
            },
            "commitment_safety": {
                "savings_margin_pct": round(savings_margin_pct, 1),
                "spillover_pct": round(spillover_pct, 1),
                "capacity_coverage_pct": round(capacity_coverage_pct, 1),
                "safety_verdict": safety_verdict,
            },
            "cache_impact": {
                "applied": cache_impact.applied,
                "source": cache_impact.source,
                "quality": cache_impact.quality,
                "coverage_pct": cache_impact.coverage_pct,
                "no_cache_normalized_avg_tpm": cache_impact.no_cache_normalized_avg_tpm,
                "cache_adjusted_normalized_avg_tpm": (
                    cache_impact.cache_adjusted_normalized_avg_tpm
                ),
                "normalized_tpm_reduction_pct": cache_impact.normalized_tpm_reduction_pct,
                "no_cache_recommended_ptu": cache_impact.no_cache_recommended_ptu,
                "cache_aware_recommended_ptu": cache_impact.cache_aware_recommended_ptu,
                "ptu_avoided": cache_impact.ptu_avoided,
                "no_cache_payg_monthly": float(no_cache_payg),
                "cache_aware_payg_monthly": float(payg_base),
                "payg_cache_savings": float(no_cache_payg - payg_base),
                "fixed_ptu_cost_changed": False,
                "validation_warnings": cache_impact.validation_warnings,
                "calculation_note": (
                    "Cached prompt tokens reduce modeled utilization; fixed PTU cost "
                    "changes only when the selected PTU count changes."
                    if cache_impact.applied
                    else "Cache telemetry was unavailable, disabled, or insufficient; "
                    "the primary estimate conservatively assumes no cache benefit."
                ),
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
                avg_active_prompt_tpm=avg_active_prompt_tpm,
                avg_cached_prompt_tpm=avg_cached_prompt_tpm,
                avg_completion_tpm=avg_completion_tpm,
                payg_cached_input_rate=payg_cached_input_rate,
                cache_source=cache_impact.source,
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
            + cache_impact.validation_warnings
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
    deployment_type: Literal["global", "data_zone", "regional"] = Query(
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
        "payg_cached_input_rate_per_million": round(result.payg_cached_input_rate, 4),
        "payg_output_rate_per_million": round(result.payg_output_rate, 4),
        "ptu_hourly_rate": round(result.ptu_hourly_rate, 4),
        "ptu_pricing_source": result.ptu_pricing_source,
        "pricing_source": result.source,
        "cached_input_pricing_source": result.cached_input_source,
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
    except Exception:
        logger.exception("Azure authentication status check failed")
        return {
            "authenticated": False,
            "display_name": "",
            "email": "",
            "tenant_id": "",
            "error": "Azure authentication unavailable.",
        }


@app.get("/api/discovery/subscriptions")
def subscriptions() -> List[Dict[str, Any]]:
    try:
        credential = get_azure_credential()
    except Exception:
        logger.exception("Azure credential acquisition failed")
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please run `az login` in your terminal, then refresh this page.",
        )
    try:
        subs = list_subscriptions(credential)
    except Exception:
        logger.exception("Azure subscription discovery failed")
        raise HTTPException(
            status_code=403,
            detail="Failed to list subscriptions. Ensure your account has Reader access to at least "
            "one Azure subscription. You can check access in the Azure Portal under "
            "'Subscriptions'.",
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
    except Exception:
        logger.exception("Azure credential acquisition failed")
        raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        items = list_ai_accounts(credential, subscription_id)
    except Exception:
        logger.exception("Azure AI Services account discovery failed")
        raise HTTPException(
            status_code=403,
            detail="Failed to list AI Services accounts. Ensure you have Reader access to "
            "the subscription.",
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
    except Exception:
        logger.exception("Azure credential acquisition failed")
        raise HTTPException(status_code=401, detail="Authentication failed.")
    try:
        items = list_deployments(credential, subscription_id, resource_group, account_name)
    except Exception:
        logger.exception("Azure deployment discovery failed")
        raise HTTPException(
            status_code=403,
            detail="Failed to list deployments. Ensure you have Cognitive Services User or "
            "Reader role on this account, plus Monitoring Reader for metrics.",
        )
    result: List[Dict[str, Any]] = []
    for dep in items:
        ptu_eligible = get_model_config(dep.model) is not None
        family = get_model_family(dep.model)
        entry: Dict[str, Any] = {
            "name": dep.name,
            "model": dep.model,
            "model_version": dep.model_version,
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
            cache_mode=payload.cache_mode,
            cache_match_rate_override_pct=payload.cache_match_rate_override_pct,
            cached_input_rate_override=payload.cached_input_rate_override,
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
        cache_mode=payload.cache_mode,
        cache_match_rate_override_pct=payload.cache_match_rate_override_pct,
        cached_input_rate_override=payload.cached_input_rate_override,
    )


def _interval_to_minutes(interval: str) -> int:
    return {"PT1M": 1, "PT5M": 5, "PT15M": 15, "PT1H": 60}.get(interval, 1)


def _series_to_az_data_points(
    series: Optional[TimeSeries],
    *,
    include_total: bool,
    include_average: bool,
    multiplier: float = 1.0,
) -> List[Dict[str, Any]]:
    """Serialize a TimeSeries into the az-CLI ``data`` array shape."""
    if series is None:
        return []
    points: List[Dict[str, Any]] = []
    for ts, val in zip(series.timestamps, series.values):
        point: Dict[str, Any] = {
            "timeStamp": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        }
        if include_total:
            point["total"] = float(val) * multiplier
        if include_average:
            point["average"] = float(val) * multiplier
        points.append(point)
    return points


def _build_token_snapshot_payload(
    metrics: DeploymentMetrics,
    *,
    resource_id: str,
    interval: str,
    namespace: str = "microsoft.cognitiveservices/accounts",
    cache_mode: Literal["auto", "disabled", "override"] = "auto",
    cache_match_rate_override_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a JSON payload matching ``az monitor metrics list`` output for the
    three GBB metrics: InputTokens, OutputTokens, AzureOpenAIContextTokensCacheMatchRate.
    """
    timespan = (
        f"{metrics.start_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')}/"
        f"{metrics.end_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')}"
    )
    cache_impact = build_cache_impact(
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        cache_match_rate=metrics.cache_match_rate,
        active_tokens=metrics.active_tokens,
        output_multiplier=(get_model_config(metrics.model_name).output_ratio if get_model_config(metrics.model_name) else 3),
        input_tpm_per_ptu=(get_model_config(metrics.model_name).input_tpm_per_ptu if get_model_config(metrics.model_name) else 2500),
        min_ptu=15,
        ptu_increment=5,
        interval_minutes=_infer_interval_minutes(metrics.prompt_tokens),
        coverage_pct_override=metrics.cache_coverage_pct,
        cache_mode=cache_mode,
        override_pct=cache_match_rate_override_pct,
    )
    interval_multiplier = _interval_to_minutes(interval)

    def metric_entry(
        name: str,
        localized: str,
        unit: str,
        series: Optional[TimeSeries],
        description: str,
        multiplier: float = 1.0,
    ) -> Dict[str, Any]:
        return {
            "displayDescription": description,
            "errorCode": "Success",
            "id": f"{resource_id}/providers/Microsoft.Insights/metrics/{name}",
            "name": {"localizedValue": localized, "value": name},
            "timeseries": [
                {
                    "data": _series_to_az_data_points(
                        series,
                        include_total=True,
                        include_average=True,
                        multiplier=multiplier,
                    ),
                    "metadatavalues": [],
                }
            ],
            "type": "Microsoft.Insights/metrics",
            "unit": unit,
        }

    return {
        "cost": 0,
        "interval": interval,
        "namespace": namespace,
        "resourceregion": "",
        "timespan": timespan,
        "value": [
            metric_entry(
                "InputTokens",
                "Input Tokens",
                "Count",
                metrics.prompt_tokens,
                "Number of prompt tokens processed (input) on a model deployment.",
                multiplier=interval_multiplier,
            ),
            metric_entry(
                "OutputTokens",
                "Output Tokens",
                "Count",
                metrics.completion_tokens,
                "Number of tokens generated (output) from a model deployment.",
                multiplier=interval_multiplier,
            ),
            metric_entry(
                "AzureOpenAIContextTokensCacheMatchRate",
                "Azure OpenAI Context Tokens Cache Match Rate",
                "Percent",
                metrics.cache_match_rate,
                "The percentage of context tokens that hit the prompt cache.",
                multiplier=100.0,
            ),
        ],
        "_meta": {
            "deployment_name": metrics.deployment_name,
            "model_name": metrics.model_name,
            "source": "ptu-advisor",
            "cache_analysis": {
                "source": cache_impact.source,
                "quality": cache_impact.quality,
                "coverage_pct": cache_impact.coverage_pct,
                "effective_rate_pct": cache_impact.avg_match_rate_pct,
                "active_prompt_tokens": cache_impact.total_active_prompt_tokens,
                "cached_prompt_tokens": cache_impact.total_cached_prompt_tokens,
                "override_used": cache_impact.source == "override",
            },
        },
    }


@app.post("/api/export/token-snapshot")
def export_token_snapshot(payload: TokenSnapshotRequest) -> Dict[str, Any]:
    """Produce a GBB-style JSON snapshot of token + cache-hit metrics.

    Mirrors the literal output of the PowerShell script GBB ships:
    ``az monitor metrics list --metric "InputTokens,OutputTokens,
    AzureOpenAIContextTokensCacheMatchRate" --interval PT1M``.
    """
    interval_minutes = _interval_to_minutes(payload.interval)

    if payload.mode == "demo":
        scenario = _pick_demo_scenario(payload.focus_topic)
        metrics, _scenario_cfg = generate_demo_metrics(
            scenario,
            lookback_days=payload.days,
            granularity_minutes=interval_minutes,
        )
        resource_id = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/demo-rg/providers/Microsoft.CognitiveServices/"
            "accounts/demo-workspace"
        )
        return _build_token_snapshot_payload(
            metrics,
            resource_id=resource_id,
            interval=payload.interval,
            cache_mode=payload.cache_mode,
            cache_match_rate_override_pct=payload.cache_match_rate_override_pct,
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
        lookback_days=payload.days,
        aggregation_interval_minutes=interval_minutes,
    )
    collector = MetricsCollector(credential, config)
    metrics = collector.collect()
    diagnostics = collector.get_diagnostics()
    resource_id = str(diagnostics.get("context", {}).get("resource_id", ""))
    return _build_token_snapshot_payload(
        metrics,
        resource_id=resource_id,
        interval=payload.interval,
        cache_mode=payload.cache_mode,
        cache_match_rate_override_pct=payload.cache_match_rate_override_pct,
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

    model_versions = {
        m.deployment_info.model_version
        for m in all_metrics
        if m.deployment_info is not None and m.deployment_info.model_version is not None
    }
    if len(model_versions) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cannot consolidate deployments with different model versions: "
                f"{sorted(model_versions)}. PTU capacity and PAYG pricing may be version-specific."
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
    if combined_metrics.cache_coverage_pct is not None and combined_metrics.cache_coverage_pct < 100:
        consolidation_warnings.append(
            "Cache telemetry is incomplete across the selected deployments "
            f"({combined_metrics.cache_coverage_pct:.1f}% prompt-token coverage). "
            "Missing deployment intervals receive no modeled cache benefit."
        )

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
        cache_mode=payload.cache_mode,
        cache_match_rate_override_pct=payload.cache_match_rate_override_pct,
        cached_input_rate_override=payload.cached_input_rate_override,
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
                payg_monthly_cost=compute_individual_payg_cost(
                    m,
                    payg_blended_rate,
                    payg_input_rate=base_response.cost_analysis["pricing"][
                        "payg_input_rate_per_million"
                    ],
                    payg_cached_input_rate=base_response.cost_analysis["pricing"][
                        "payg_cached_input_rate_per_million"
                    ],
                    payg_output_rate=base_response.cost_analysis["pricing"][
                        "payg_output_rate_per_million"
                    ],
                    cache_mode=payload.cache_mode,
                    cache_override_pct=payload.cache_match_rate_override_pct,
                ),
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
    if not combined_ts_iso and combined_tpm:
        combined_ts_iso = [timestamp.isoformat() for timestamp in combined_tpm.timestamps]
    per_dep_charts = serialize_per_deployment_charts(all_metrics, combined_ts_iso)

    # Merge per_deployment data into existing chart sections
    enriched_charts = dict(base_response.charts)
    for chart_key in ("tokens", "requests", "tpm", "throttling"):
        if chart_key in enriched_charts and chart_key in per_dep_charts:
            enriched_charts[chart_key] = {
                **enriched_charts[chart_key],
                **per_dep_charts[chart_key],
            }

    if "prompt_cache" in enriched_charts:
        enriched_charts["prompt_cache"] = {
            **enriched_charts["prompt_cache"],
            **per_dep_charts.get("prompt_cache", {}),
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


def _resolve_static_file(static_dir: Path, full_path: str) -> Optional[Path]:
    static_root = static_dir.resolve()
    candidate = (static_root / full_path).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None

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
        file_path = _resolve_static_file(_STATIC_DIR, full_path)
        if file_path is not None:
            return FileResponse(file_path)
        return FileResponse(_STATIC_DIR / "index.html")
