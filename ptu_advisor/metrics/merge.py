"""Merge multiple same-model DeploymentMetrics into a combined virtual deployment.

Used by the consolidation analysis endpoint to evaluate whether grouping
several PAYG deployments onto a shared PTU reservation is cost-effective.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ptu_advisor.metrics.models import DeploymentInfo, DeploymentMetrics, TimeSeries


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
    """Reindex a TimeSeries onto *target_timestamps*, forward-filling gaps.

    If a timestamp appears before the first value in *series*, 0.0 is used.
    """
    lookup: Dict[datetime, float] = dict(zip(series.timestamps, series.values))
    result: List[float] = []
    last_value = 0.0
    for ts in target_timestamps:
        if ts in lookup:
            last_value = lookup[ts]
        result.append(last_value)
    return result


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
    combined_prompt = _sum_series(
        [d.prompt_tokens for d in deployments],
        target_timestamps,
        "PromptTokens",
    )
    combined_completion = _sum_series(
        [d.completion_tokens for d in deployments],
        target_timestamps,
        "CompletionTokens",
    )

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
        time_to_first_byte_p50=combined_p50,
        time_to_first_byte_p95=combined_p95,
        time_to_first_byte_p99=combined_p99,
    )

    # Attach a synthetic DeploymentInfo
    combined.deployment_info = DeploymentInfo(
        name=combined_name,
        model=model_name,
        sku_type="Standard",
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

    return {
        "tokens": {"per_deployment": tokens_per_dep},
        "requests": {"per_deployment": requests_per_dep},
        "latency": {"per_deployment": latency_per_dep},
        "tpm": {"per_deployment": tpm_per_dep},
        "throttling": {"per_deployment": throttling_per_dep},
    }


def compute_individual_payg_cost(
    metrics: DeploymentMetrics,
    payg_blended_rate: float,
) -> float:
    """Estimate monthly PAYG cost for a single deployment.

    Uses avg_tpm × 43,200 minutes/month / 1M × blended_rate.
    """
    if not metrics.tokens_per_minute:
        return 0.0
    avg_tpm = float(metrics.tokens_per_minute.mean)
    monthly_tokens = avg_tpm * 43_200  # 60 min × 24 h × 30 d
    return (monthly_tokens / 1_000_000) * payg_blended_rate
