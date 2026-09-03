"""Merge multiple same-model DeploymentMetrics into a combined virtual deployment.

Used by the consolidation analysis endpoint to evaluate whether grouping
several PAYG deployments onto a shared PTU reservation is cost-effective.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ptu_advisor.metrics.models import (
    DeploymentInfo,
    DeploymentMetrics,
    TimeSeries,
    infer_cache_match_rate,
)


def _align_timestamps(
    all_series: List[TimeSeries],
) -> List[datetime]:
    """Return the sorted union of timestamps across all series."""
    ts_set: set[datetime] = set()
    for series in all_series:
        ts_set.update(series.timestamps)
    return sorted(ts_set)


def _reindex_series(
    series: TimeSeries,
    target_timestamps: List[datetime],
) -> List[float]:
    """Reindex a TimeSeries onto *target_timestamps*, zero-filling gaps."""
    lookup: Dict[datetime, float] = dict(zip(series.timestamps, series.values))
    return [float(lookup.get(ts, 0.0)) for ts in target_timestamps]


def _sum_series(
    all_series: List[Optional[TimeSeries]],
    target_timestamps: List[datetime],
    metric_name: str,
    unit: str = "Count",
) -> Optional[TimeSeries]:
    """Element-wise sum of multiple TimeSeries, aligned to *target_timestamps*."""
    valid = [s for s in all_series if s is not None]
    if not valid:
        return None

    aligned = [_reindex_series(s, target_timestamps) for s in valid]
    summed = [float(sum(vals)) for vals in zip(*aligned)]
    return TimeSeries(
        timestamps=list(target_timestamps),
        values=summed,
        metric_name=metric_name,
        unit=unit,
    )


def _weighted_avg_series(
    latency_series: List[Optional[TimeSeries]],
    weight_series: List[Optional[TimeSeries]],
    target_timestamps: List[datetime],
    metric_name: str,
    unit: str = "Milliseconds",
) -> Optional[TimeSeries]:
    """Weighted average of latency series using request counts as weights.

    For each timestamp: weighted_avg = sum(latency_i * weight_i) / sum(weight_i).
    Falls back to simple average if all weights are zero.
    """
    valid_pairs: List[Tuple[TimeSeries, TimeSeries]] = []
    for lat, wt in zip(latency_series, weight_series):
        if lat is not None and wt is not None:
            valid_pairs.append((lat, wt))
    if not valid_pairs:
        return None

    aligned_lats = [_reindex_series(lat, target_timestamps) for lat, _ in valid_pairs]
    aligned_wts = [_reindex_series(wt, target_timestamps) for _, wt in valid_pairs]

    result: List[float] = []
    for i in range(len(target_timestamps)):
        total_weight = sum(w[i] for w in aligned_wts)
        if total_weight > 0:
            weighted = sum(l[i] * w[i] for l, w in zip(aligned_lats, aligned_wts))
            result.append(weighted / total_weight)
        else:
            # Fall back to simple average
            vals = [l[i] for l in aligned_lats]
            result.append(float(np.mean(vals)) if vals else 0.0)

    return TimeSeries(
        timestamps=list(target_timestamps),
        values=result,
        metric_name=metric_name,
        unit=unit,
    )


def _max_series(
    all_series: List[Optional[TimeSeries]],
    target_timestamps: List[datetime],
    metric_name: str,
    unit: str = "Milliseconds",
) -> Optional[TimeSeries]:
    """Element-wise max across multiple TimeSeries (for P99 latency)."""
    valid = [s for s in all_series if s is not None]
    if not valid:
        return None

    aligned = [_reindex_series(s, target_timestamps) for s in valid]
    maxed = [float(max(vals)) for vals in zip(*aligned)]
    return TimeSeries(
        timestamps=list(target_timestamps),
        values=maxed,
        metric_name=metric_name,
        unit=unit,
    )


def _weighted_cache_rate_series(
    deployments: List[DeploymentMetrics],
    target_timestamps: List[datetime],
) -> Tuple[Optional[TimeSeries], float, Optional[str]]:
    """Combine cache rates using prompt-token volume as the weight.

    Cache values use exact timestamp matches. Missing cache telemetry receives
    zero modeled benefit instead of being forward-filled.
    """
    rate_lookups: List[Dict[datetime, float]] = []
    has_direct = False
    has_inferred = False
    for deployment in deployments:
        observed = (
            {
                timestamp: float(value)
                for timestamp, value in zip(
                    deployment.cache_match_rate.timestamps,
                    deployment.cache_match_rate.values,
                )
                if np.isfinite(value) and 0.0 <= float(value) <= 1.0
            }
            if deployment.cache_match_rate
            else {}
        )
        inferred: Dict[datetime, float] = {}
        if deployment.active_tokens and deployment.prompt_tokens and deployment.completion_tokens:
            prompt_lookup = dict(
                zip(deployment.prompt_tokens.timestamps, deployment.prompt_tokens.values)
            )
            completion_lookup = dict(
                zip(deployment.completion_tokens.timestamps, deployment.completion_tokens.values)
            )
            active_lookup = dict(
                zip(deployment.active_tokens.timestamps, deployment.active_tokens.values)
            )
            for timestamp, prompt in prompt_lookup.items():
                if timestamp in observed:
                    continue
                if timestamp not in completion_lookup or timestamp not in active_lookup:
                    continue
                ratio = infer_cache_match_rate(
                    prompt,
                    completion_lookup[timestamp],
                    active_lookup[timestamp],
                )
                if ratio is not None:
                    inferred[timestamp] = ratio
        rate_lookups.append({**inferred, **observed})
        has_direct = has_direct or bool(observed)
        has_inferred = has_inferred or bool(inferred)
    if not has_direct and not has_inferred:
        return None, 0.0, None
    prompt_lookups = [
        dict(zip(d.prompt_tokens.timestamps, d.prompt_tokens.values)) if d.prompt_tokens else {}
        for d in deployments
    ]

    combined: List[float] = []
    covered_prompt_total = 0.0
    prompt_total_all = 0.0
    for timestamp in target_timestamps:
        total_prompt = 0.0
        total_cached = 0.0
        for rate_lookup, prompt_lookup in zip(rate_lookups, prompt_lookups):
            prompt = float(prompt_lookup.get(timestamp, 0.0))
            has_rate = timestamp in rate_lookup
            rate = float(rate_lookup.get(timestamp, 0.0))
            total_prompt += prompt
            prompt_total_all += prompt
            if has_rate:
                covered_prompt_total += prompt
            total_cached += prompt * min(1.0, max(0.0, rate))
        combined.append(total_cached / total_prompt if total_prompt > 0 else 0.0)

    return (
        TimeSeries(
            timestamps=list(target_timestamps),
            values=combined,
            metric_name="AzureOpenAIContextTokensCacheMatchRate",
            unit="Ratio",
        ),
        covered_prompt_total / prompt_total_all * 100.0 if prompt_total_all > 0 else 0.0,
        "mixed" if has_direct and has_inferred else ("observed" if has_direct else "inferred"),
    )


def merge_deployment_metrics(
    deployments: List[DeploymentMetrics],
) -> DeploymentMetrics:
    """Merge multiple same-model DeploymentMetrics into a combined view.

    Additive metrics (TPM, requests, tokens): element-wise sum.
    Latency P50/P95: request-weighted average.
    Latency P99: element-wise max (worst-case across deployments).

    Args:
        deployments: 2+ DeploymentMetrics objects for the same model.

    Returns:
        A single DeploymentMetrics representing the combined virtual deployment.

    Raises:
        ValueError: If fewer than 2 deployments or models don't match.
    """
    if len(deployments) < 2:
        raise ValueError("Need at least 2 deployments to consolidate")

    model_names = {d.model_name for d in deployments}
    if len(model_names) > 1:
        raise ValueError(f"Cannot consolidate deployments with different models: {model_names}")

    # Validate same SKU type when deployment_info is available
    sku_types = {d.deployment_info.sku_type for d in deployments if d.deployment_info is not None}
    if len(sku_types) > 1:
        raise ValueError(
            f"Cannot consolidate deployments with different SKU types: {sku_types}. "
            "PTU capacity is SKU-specific — only same-SKU deployments can share a PTU allocation."
        )

    reported_model_versions = {
        d.deployment_info.model_version
        for d in deployments
        if d.deployment_info is not None and d.deployment_info.model_version is not None
    }
    if len(reported_model_versions) > 1:
        raise ValueError(
            "Cannot consolidate deployments with different model versions: "
            f"{reported_model_versions}"
        )
    shared_model_version = (
        next(iter(reported_model_versions))
        if len(reported_model_versions) == 1
        and all(
            d.deployment_info is not None and d.deployment_info.model_version is not None
            for d in deployments
        )
        else None
    )

    # Build the unified timestamp axis
    all_ts_series: List[TimeSeries] = []
    for d in deployments:
        if d.tokens_per_minute:
            all_ts_series.append(d.tokens_per_minute)
        elif d.requests_per_minute:
            all_ts_series.append(d.requests_per_minute)
    if not all_ts_series:
        raise ValueError("No time-series data available in any deployment")

    target_timestamps = _align_timestamps(all_ts_series)

    # Determine combined time window
    start_time = min(d.start_time for d in deployments)
    end_time = max(d.end_time for d in deployments)

    # Build combined deployment name
    dep_names = [d.deployment_name for d in deployments]
    combined_name = f"consolidated({', '.join(dep_names)})"

    # Additive merges
    combined_tpm = _sum_series(
        [d.tokens_per_minute for d in deployments],
        target_timestamps,
        "TokensPerMinute",
    )
    combined_rpm = _sum_series(
        [d.requests_per_minute for d in deployments],
        target_timestamps,
        "RequestsPerMinute",
    )
    combined_throttled = _sum_series(
        [d.throttled_requests for d in deployments],
        target_timestamps,
        "ThrottledRequests",
    )
    combined_successful = _sum_series(
        [d.successful_requests for d in deployments],
        target_timestamps,
        "SuccessfulRequests",
    )
    has_complete_token_shape = all(
        d.prompt_tokens is not None
        and d.completion_tokens is not None
        and d.prompt_tokens.timestamps == target_timestamps
        and d.completion_tokens.timestamps == target_timestamps
        for d in deployments
    )
    combined_prompt = (
        _sum_series(
            [d.prompt_tokens for d in deployments],
            target_timestamps,
            "PromptTokens",
        )
        if has_complete_token_shape
        else None
    )
    combined_completion = (
        _sum_series(
            [d.completion_tokens for d in deployments],
            target_timestamps,
            "CompletionTokens",
        )
        if has_complete_token_shape
        else None
    )
    combined_active_tokens = (
        _sum_series(
            [d.active_tokens for d in deployments],
            target_timestamps,
            "ActiveTokens",
        )
        if all(d.active_tokens is not None for d in deployments)
        else None
    )
    combined_cache_match, cache_coverage_pct, cache_source = _weighted_cache_rate_series(
        deployments, target_timestamps
    )
    if not has_complete_token_shape:
        combined_cache_match = None
        cache_coverage_pct = 0.0
        cache_source = None

    # Latency: P50 and P95 weighted by request count; P99 = max
    request_weights = [d.requests_per_minute for d in deployments]

    combined_p50 = _weighted_avg_series(
        [d.time_to_first_byte_p50 for d in deployments],
        request_weights,
        target_timestamps,
        "TimeToFirstByte_P50",
    )
    combined_p95 = _weighted_avg_series(
        [d.time_to_first_byte_p95 for d in deployments],
        request_weights,
        target_timestamps,
        "TimeToFirstByte_P95",
    )
    combined_p99 = _max_series(
        [d.time_to_first_byte_p99 for d in deployments],
        target_timestamps,
        "TimeToFirstByte_P99",
    )

    model_name = deployments[0].model_name
    combined = DeploymentMetrics(
        deployment_name=combined_name,
        model_name=model_name,
        start_time=start_time,
        end_time=end_time,
        timestamps=target_timestamps,
        tokens_per_minute=combined_tpm,
        requests_per_minute=combined_rpm,
        throttled_requests=combined_throttled,
        successful_requests=combined_successful,
        prompt_tokens=combined_prompt,
        completion_tokens=combined_completion,
        cache_match_rate=combined_cache_match,
        active_tokens=combined_active_tokens,
        cache_coverage_pct=cache_coverage_pct,
        cache_source=cache_source,
        cache_missing_as_zero=cache_source is not None and cache_coverage_pct < 100.0,
        time_to_first_byte_p50=combined_p50,
        time_to_first_byte_p95=combined_p95,
        time_to_first_byte_p99=combined_p99,
    )

    # Attach a synthetic DeploymentInfo
    combined.deployment_info = DeploymentInfo(
        name=combined_name,
        model=model_name,
        sku_type="Standard",
        model_version=shared_model_version,
        sku_capacity=None,
    )

    return combined


def serialize_per_deployment_charts(
    individual_metrics: List[DeploymentMetrics],
    combined_timestamps_iso: List[str],
) -> Dict[str, Any]:
    """Build per-deployment chart series aligned to the combined timestamp axis.

    Returns a dict keyed by chart section (``tokens``, ``requests``,
    ``latency``, ``tpm``, ``throttling``) each containing a
    ``per_deployment`` dict mapping deployment names to their aligned
    time-series arrays.

    This is designed to be merged directly into the ``charts`` dict
    returned by ``_serialize_analysis()`` for consolidation responses.
    """
    from datetime import datetime as _dt

    # Parse combined ISO timestamps back to datetime for alignment
    combined_dt: List[_dt] = [_dt.fromisoformat(ts) for ts in combined_timestamps_iso]

    tokens_per_dep: Dict[str, Dict[str, List[float]]] = {}
    requests_per_dep: Dict[str, Dict[str, List[float]]] = {}
    latency_per_dep: Dict[str, Dict[str, List[float]]] = {}
    tpm_per_dep: Dict[str, List[float]] = {}
    throttling_per_dep: Dict[str, List[float]] = {}
    cache_per_dep: Dict[str, Dict[str, Any]] = {}

    for m in individual_metrics:
        name = m.deployment_name

        # --- Tokens ---
        prompt_vals = (
            _reindex_series(m.prompt_tokens, combined_dt)
            if m.prompt_tokens
            else [0.0] * len(combined_dt)
        )
        completion_vals = (
            _reindex_series(m.completion_tokens, combined_dt)
            if m.completion_tokens
            else [0.0] * len(combined_dt)
        )
        tokens_per_dep[name] = {
            "prompt": prompt_vals,
            "completion": completion_vals,
        }

        # --- Requests ---
        successful_vals = (
            _reindex_series(m.successful_requests, combined_dt)
            if m.successful_requests
            else [0.0] * len(combined_dt)
        )
        throttled_vals = (
            _reindex_series(m.throttled_requests, combined_dt)
            if m.throttled_requests
            else [0.0] * len(combined_dt)
        )
        requests_per_dep[name] = {
            "successful": successful_vals,
            "throttled": throttled_vals,
        }

        # --- Latency (overlaid, not stacked) ---
        p50_vals = (
            _reindex_series(m.time_to_first_byte_p50, combined_dt)
            if m.time_to_first_byte_p50
            else [0.0] * len(combined_dt)
        )
        p95_vals = (
            _reindex_series(m.time_to_first_byte_p95, combined_dt)
            if m.time_to_first_byte_p95
            else [0.0] * len(combined_dt)
        )
        p99_vals = (
            _reindex_series(m.time_to_first_byte_p99, combined_dt)
            if m.time_to_first_byte_p99
            else [0.0] * len(combined_dt)
        )
        latency_per_dep[name] = {
            "p50": p50_vals,
            "p95": p95_vals,
            "p99": p99_vals,
        }

        # --- TPM ---
        tpm_vals = (
            _reindex_series(m.tokens_per_minute, combined_dt)
            if m.tokens_per_minute
            else [0.0] * len(combined_dt)
        )
        tpm_per_dep[name] = tpm_vals

        # --- Throttling (429 events) ---
        throttle_event_vals = (
            _reindex_series(m.throttled_requests, combined_dt)
            if m.throttled_requests
            else [0.0] * len(combined_dt)
        )
        throttling_per_dep[name] = throttle_event_vals

        prompt_vals = (
            _reindex_series(m.prompt_tokens, combined_dt)
            if m.prompt_tokens
            else [0.0] * len(combined_dt)
        )
        cache_lookup: Dict[datetime, float] = (
            dict(zip(m.cache_match_rate.timestamps, m.cache_match_rate.values))
            if m.cache_match_rate
            else {}
        )
        cache_source = "observed" if cache_lookup else "unavailable"
        if m.active_tokens and m.completion_tokens:
            active_lookup = dict(zip(m.active_tokens.timestamps, m.active_tokens.values))
            completion_lookup = dict(
                zip(m.completion_tokens.timestamps, m.completion_tokens.values)
            )
            used_inferred = False
            for ts, prompt in zip(combined_dt, prompt_vals):
                if ts in cache_lookup:
                    continue
                if ts not in active_lookup or ts not in completion_lookup:
                    continue
                rate = infer_cache_match_rate(
                    prompt,
                    completion_lookup[ts],
                    active_lookup[ts],
                )
                if rate is not None:
                    cache_lookup[ts] = rate
                    used_inferred = True
            if used_inferred:
                cache_source = "mixed" if m.cache_match_rate else "inferred"
        cache_rates = [
            min(1.0, max(0.0, float(cache_lookup[ts]))) if ts in cache_lookup else None
            for ts in combined_dt
        ]
        cached_prompt = [
            prompt * rate if rate is not None else 0.0
            for prompt, rate in zip(prompt_vals, cache_rates)
        ]
        cache_per_dep[name] = {
            "match_rate_pct": [rate * 100.0 if rate is not None else None for rate in cache_rates],
            "cached_prompt_tokens": cached_prompt,
            "active_prompt_tokens": [
                prompt - cached for prompt, cached in zip(prompt_vals, cached_prompt)
            ],
            "source": cache_source,
        }

    return {
        "tokens": {"per_deployment": tokens_per_dep},
        "requests": {"per_deployment": requests_per_dep},
        "latency": {"per_deployment": latency_per_dep},
        "tpm": {"per_deployment": tpm_per_dep},
        "throttling": {"per_deployment": throttling_per_dep},
        "prompt_cache": {"per_deployment": cache_per_dep},
    }


def compute_individual_payg_cost(
    metrics: DeploymentMetrics,
    payg_blended_rate: float,
    payg_input_rate: Optional[float] = None,
    payg_cached_input_rate: Optional[float] = None,
    payg_output_rate: Optional[float] = None,
    cache_mode: str = "auto",
    cache_override_pct: Optional[float] = None,
) -> float:
    """Estimate monthly PAYG cost for a single deployment.

    Uses avg_tpm × 43,200 minutes/month / 1M × blended_rate.
    """
    if (
        metrics.prompt_tokens
        and metrics.completion_tokens
        and payg_input_rate is not None
        and payg_cached_input_rate is not None
        and payg_output_rate is not None
    ):
        from ptu_advisor.config import get_model_config
        from ptu_advisor.cost.cache import build_cache_impact

        model_config = get_model_config(metrics.model_name)
        impact = build_cache_impact(
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            cache_match_rate=metrics.cache_match_rate,
            active_tokens=metrics.active_tokens,
            output_multiplier=model_config.output_ratio if model_config else 1,
            input_tpm_per_ptu=model_config.input_tpm_per_ptu if model_config else 1,
            min_ptu=1,
            ptu_increment=1,
            cache_mode=cache_mode,  # type: ignore[arg-type]
            override_pct=cache_override_pct,
            coverage_pct_override=metrics.cache_coverage_pct,
        )
        avg_prompt = float(metrics.prompt_tokens.mean)
        avg_cached = (
            float(np.mean(impact.cached_prompt_tokens))
            if impact.applied and impact.cached_prompt_tokens
            else 0.0
        )
        avg_active = max(0.0, avg_prompt - avg_cached)
        avg_output = float(metrics.completion_tokens.mean)
        return (
            avg_active * 43_200 / 1_000_000 * payg_input_rate
            + avg_cached * 43_200 / 1_000_000 * payg_cached_input_rate
            + avg_output * 43_200 / 1_000_000 * payg_output_rate
        )

    if not metrics.tokens_per_minute:
        return 0.0
    avg_tpm = float(metrics.tokens_per_minute.mean)
    monthly_tokens = avg_tpm * 43_200  # 60 min × 24 h × 30 d
    return (monthly_tokens / 1_000_000) * payg_blended_rate
