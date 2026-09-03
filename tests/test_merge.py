"""Tests for ptu_advisor.metrics.merge — time-series merging for consolidation analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import pytest

from ptu_advisor.metrics.merge import (
    _align_timestamps,
    _max_series,
    _reindex_series,
    _sum_series,
    _weighted_avg_series,
    compute_individual_payg_cost,
    merge_deployment_metrics,
    serialize_per_deployment_charts,
)
from ptu_advisor.metrics.models import DeploymentInfo, DeploymentMetrics, TimeSeries


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _ts(minutes_offset: int, base: Optional[datetime] = None) -> datetime:
    """Helper to create timestamps relative to a base time."""
    if base is None:
        base = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes_offset)


BASE = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)


def _make_series(
    offsets: List[int],
    values: List[float],
    metric_name: str = "TestMetric",
    unit: str = "Count",
) -> TimeSeries:
    return TimeSeries(
        timestamps=[_ts(o) for o in offsets],
        values=values,
        metric_name=metric_name,
        unit=unit,
    )


def _make_deployment(
    name: str,
    model: str,
    offsets: List[int],
    tpm_values: List[float],
    rpm_values: Optional[List[float]] = None,
    throttled_values: Optional[List[float]] = None,
    successful_values: Optional[List[float]] = None,
    p50_values: Optional[List[float]] = None,
    p95_values: Optional[List[float]] = None,
    p99_values: Optional[List[float]] = None,
    prompt_values: Optional[List[float]] = None,
    completion_values: Optional[List[float]] = None,
    cache_values: Optional[List[float]] = None,
) -> DeploymentMetrics:
    timestamps = [_ts(o) for o in offsets]
    n = len(offsets)

    rpm = rpm_values or [v / 100 for v in tpm_values]
    throttled = throttled_values or [0.0] * n
    successful = successful_values or rpm
    p50 = p50_values or [300.0] * n
    p95 = p95_values or [1500.0] * n
    p99 = p99_values or [3000.0] * n
    prompt = prompt_values or [v * 0.6 for v in tpm_values]
    completion = completion_values or [v * 0.4 for v in tpm_values]

    metrics = DeploymentMetrics(
        deployment_name=name,
        model_name=model,
        start_time=timestamps[0],
        end_time=timestamps[-1],
        timestamps=timestamps,
        tokens_per_minute=TimeSeries(
            timestamps=timestamps,
            values=tpm_values,
            metric_name="TokensPerMinute",
            unit="Count",
        ),
        requests_per_minute=TimeSeries(
            timestamps=timestamps,
            values=rpm,
            metric_name="RequestsPerMinute",
            unit="Count",
        ),
        throttled_requests=TimeSeries(
            timestamps=timestamps,
            values=throttled,
            metric_name="ThrottledRequests",
            unit="Count",
        ),
        successful_requests=TimeSeries(
            timestamps=timestamps,
            values=successful,
            metric_name="SuccessfulRequests",
            unit="Count",
        ),
        prompt_tokens=TimeSeries(
            timestamps=timestamps,
            values=prompt,
            metric_name="PromptTokens",
            unit="Count",
        ),
        completion_tokens=TimeSeries(
            timestamps=timestamps,
            values=completion,
            metric_name="CompletionTokens",
            unit="Count",
        ),
        cache_match_rate=(
            TimeSeries(
                timestamps=timestamps,
                values=cache_values,
                metric_name="CacheMatchRate",
                unit="Ratio",
            )
            if cache_values is not None
            else None
        ),
        time_to_first_byte_p50=TimeSeries(
            timestamps=timestamps,
            values=p50,
            metric_name="TimeToFirstByte_P50",
            unit="Milliseconds",
        ),
        time_to_first_byte_p95=TimeSeries(
            timestamps=timestamps,
            values=p95,
            metric_name="TimeToFirstByte_P95",
            unit="Milliseconds",
        ),
        time_to_first_byte_p99=TimeSeries(
            timestamps=timestamps,
            values=p99,
            metric_name="TimeToFirstByte_P99",
            unit="Milliseconds",
        ),
    )
    metrics.deployment_info = DeploymentInfo(
        name=name,
        model=model,
        sku_type="Standard",
        sku_capacity=None,
    )
    return metrics


# ===================================================================
# _align_timestamps
# ===================================================================


class TestAlignTimestamps:
    def test_union_of_two_overlapping_series(self):
        s1 = _make_series([0, 5, 10], [1, 2, 3])
        s2 = _make_series([5, 10, 15], [4, 5, 6])
        result = _align_timestamps([s1, s2])
        assert result == [_ts(0), _ts(5), _ts(10), _ts(15)]

    def test_identical_timestamps(self):
        s1 = _make_series([0, 5, 10], [1, 2, 3])
        s2 = _make_series([0, 5, 10], [4, 5, 6])
        result = _align_timestamps([s1, s2])
        assert result == [_ts(0), _ts(5), _ts(10)]

    def test_non_overlapping_series(self):
        s1 = _make_series([0, 5], [1, 2])
        s2 = _make_series([10, 15], [3, 4])
        result = _align_timestamps([s1, s2])
        assert result == [_ts(0), _ts(5), _ts(10), _ts(15)]

    def test_single_series(self):
        s1 = _make_series([0, 5, 10], [1, 2, 3])
        result = _align_timestamps([s1])
        assert result == [_ts(0), _ts(5), _ts(10)]

    def test_empty_series(self):
        result = _align_timestamps([])
        assert result == []


# ===================================================================
# _reindex_series
# ===================================================================


class TestReindexSeries:
    def test_exact_match_returns_original_values(self):
        series = _make_series([0, 5, 10], [100, 200, 300])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _reindex_series(series, target)
        assert result == [100, 200, 300]

    def test_zero_fill_missing_timestamps(self):
        series = _make_series([0, 10], [100, 300])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _reindex_series(series, target)
        assert result == [100, 0.0, 300]

    def test_target_before_first_value_returns_zero(self):
        series = _make_series([5, 10], [200, 300])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _reindex_series(series, target)
        assert result == [0.0, 200, 300]  # _ts(0) is before series start

    def test_empty_target_returns_empty(self):
        series = _make_series([0, 5], [100, 200])
        result = _reindex_series(series, [])
        assert result == []


# ===================================================================
# _sum_series
# ===================================================================


class TestSumSeries:
    def test_sum_two_aligned_series(self):
        s1 = _make_series([0, 5, 10], [100, 200, 300])
        s2 = _make_series([0, 5, 10], [10, 20, 30])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _sum_series([s1, s2], target, "SumMetric")
        assert result is not None
        assert result.values == [110, 220, 330]

    def test_sum_with_misaligned_timestamps(self):
        s1 = _make_series([0, 5], [100, 200])
        s2 = _make_series([5, 10], [10, 20])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _sum_series([s1, s2], target, "SumMetric")
        assert result is not None
        # s1: [100, 200, 0(missing)], s2: [0(before), 10, 20]
        assert result.values == [100, 210, 20]

    def test_sum_ignores_none_series(self):
        s1 = _make_series([0, 5], [100, 200])
        target = [_ts(0), _ts(5)]
        result = _sum_series([s1, None], target, "SumMetric")
        assert result is not None
        assert result.values == [100, 200]

    def test_all_none_returns_none(self):
        target = [_ts(0), _ts(5)]
        result = _sum_series([None, None], target, "SumMetric")
        assert result is None


# ===================================================================
# _weighted_avg_series
# ===================================================================


class TestWeightedAvgSeries:
    def test_weighted_average_by_request_count(self):
        # Deploy A: latency 300ms, 100 requests
        # Deploy B: latency 500ms, 300 requests
        # Weighted avg = (300*100 + 500*300) / (100+300) = 450ms
        lat_a = _make_series([0], [300.0])
        lat_b = _make_series([0], [500.0])
        wt_a = _make_series([0], [100.0])
        wt_b = _make_series([0], [300.0])
        target = [_ts(0)]
        result = _weighted_avg_series([lat_a, lat_b], [wt_a, wt_b], target, "WAvg")
        assert result is not None
        assert abs(result.values[0] - 450.0) < 0.01

    def test_falls_back_to_simple_avg_when_weights_zero(self):
        lat_a = _make_series([0], [300.0])
        lat_b = _make_series([0], [500.0])
        wt_a = _make_series([0], [0.0])
        wt_b = _make_series([0], [0.0])
        target = [_ts(0)]
        result = _weighted_avg_series([lat_a, lat_b], [wt_a, wt_b], target, "WAvg")
        assert result is not None
        assert abs(result.values[0] - 400.0) < 0.01  # Simple avg

    def test_all_none_returns_none(self):
        target = [_ts(0)]
        result = _weighted_avg_series([None, None], [None, None], target, "WAvg")
        assert result is None


# ===================================================================
# _max_series
# ===================================================================


class TestMaxSeries:
    def test_element_wise_max(self):
        s1 = _make_series([0, 5, 10], [100, 500, 200])
        s2 = _make_series([0, 5, 10], [300, 100, 400])
        target = [_ts(0), _ts(5), _ts(10)]
        result = _max_series([s1, s2], target, "MaxMetric")
        assert result is not None
        assert result.values == [300, 500, 400]

    def test_all_none_returns_none(self):
        target = [_ts(0)]
        result = _max_series([None, None], target, "MaxMetric")
        assert result is None


# ===================================================================
# merge_deployment_metrics
# ===================================================================


class TestMergeDeploymentMetrics:
    def test_two_same_model_deployments_merge_correctly(self):
        dep_a = _make_deployment(
            "dep-a",
            "gpt-4o",
            offsets=[0, 5, 10],
            tpm_values=[10000.0, 20000.0, 15000.0],
            rpm_values=[100.0, 200.0, 150.0],
        )
        dep_b = _make_deployment(
            "dep-b",
            "gpt-4o",
            offsets=[0, 5, 10],
            tpm_values=[5000.0, 8000.0, 6000.0],
            rpm_values=[50.0, 80.0, 60.0],
        )

        combined = merge_deployment_metrics([dep_a, dep_b])

        assert "consolidated(" in combined.deployment_name
        assert combined.model_name == "gpt-4o"

        # TPM should be summed
        tpm = combined.tokens_per_minute
        assert tpm is not None
        assert tpm.values == [15000.0, 28000.0, 21000.0]

        # RPM should be summed
        rpm = combined.requests_per_minute
        assert rpm is not None
        assert rpm.values == [150.0, 280.0, 210.0]

    def test_rejects_fewer_than_2_deployments(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        with pytest.raises(ValueError, match="at least 2"):
            merge_deployment_metrics([dep_a])

    def test_rejects_different_models(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o-mini", [0, 5], [1000, 2000])
        with pytest.raises(ValueError, match="different models"):
            merge_deployment_metrics([dep_a, dep_b])

    def test_rejects_different_sku_types(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        dep_b.deployment_info = DeploymentInfo(
            name="dep-b",
            model="gpt-4o",
            sku_type="ProvisionedManaged",
            sku_capacity=100,
        )
        with pytest.raises(ValueError, match="different SKU types"):
            merge_deployment_metrics([dep_a, dep_b])

    def test_accepts_same_sku_types(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        # Both have sku_type="Standard" by default from _make_deployment
        combined = merge_deployment_metrics([dep_a, dep_b])
        assert combined.model_name == "gpt-4o"

    def test_preserves_shared_model_version(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        dep_a.deployment_info.model_version = "2024-11-20"
        dep_b.deployment_info.model_version = "2024-11-20"

        combined = merge_deployment_metrics([dep_a, dep_b])

        assert combined.deployment_info is not None
        assert combined.deployment_info.model_version == "2024-11-20"

    def test_rejects_different_model_versions(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        dep_a.deployment_info.model_version = "2024-08-06"
        dep_b.deployment_info.model_version = "2024-11-20"

        with pytest.raises(ValueError, match="different model versions"):
            merge_deployment_metrics([dep_a, dep_b])

    def test_skips_sku_validation_when_no_deployment_info(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        dep_a.deployment_info = None
        dep_b.deployment_info = None
        # Should not raise — no SKU info to validate
        combined = merge_deployment_metrics([dep_a, dep_b])
        assert combined.model_name == "gpt-4o"

    def test_handles_misaligned_timestamps(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [5, 10], [3000, 4000])

        combined = merge_deployment_metrics([dep_a, dep_b])

        tpm = combined.tokens_per_minute
        assert tpm is not None
        # Timestamps: [0, 5, 10]
        # dep_a aligned: [1000, 2000, 0(missing)]
        # dep_b aligned: [0(before), 3000, 4000]
        assert len(tpm.values) == 3
        assert tpm.values[0] == 1000.0  # 1000 + 0
        assert tpm.values[1] == 5000.0  # 2000 + 3000
        assert tpm.values[2] == 4000.0

    def test_cache_rate_uses_active_tokens_fallback_per_deployment(self):
        dep_direct = _make_deployment(
            "direct",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
            cache_values=[0.5],
        )
        dep_inferred = _make_deployment(
            "inferred",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
        )
        dep_inferred.active_tokens = _make_series([0], [600], "ActiveTokens")

        combined = merge_deployment_metrics([dep_direct, dep_inferred])

        assert combined.cache_match_rate is not None
        assert combined.cache_match_rate.values == pytest.approx([0.5])
        assert combined.cache_coverage_pct == pytest.approx(100.0)
        assert combined.cache_source == "mixed"

    def test_cache_rate_rejects_invalid_active_tokens_fallback(self):
        dep_invalid = _make_deployment(
            "invalid",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
        )
        dep_missing = _make_deployment(
            "missing",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
        )
        dep_invalid.active_tokens = _make_series([0], [50], "ActiveTokens")

        combined = merge_deployment_metrics([dep_invalid, dep_missing])

        assert combined.cache_match_rate is None
        assert combined.cache_coverage_pct == 0.0
        assert combined.cache_source is None

    def test_cache_coverage_tracks_missing_deployment_evidence(self):
        dep_observed = _make_deployment(
            "observed",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
            cache_values=[0.5],
        )
        dep_missing = _make_deployment(
            "missing",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
        )

        combined = merge_deployment_metrics([dep_observed, dep_missing])

        assert combined.cache_coverage_pct == pytest.approx(50.0)
        assert combined.cache_source == "observed"
        assert combined.cache_missing_as_zero is True

    def test_missing_token_shape_disables_partial_consolidated_shape(self):
        dep_complete = _make_deployment("complete", "gpt-4o", [0], [1100])
        dep_missing = _make_deployment("missing", "gpt-4o", [0], [2200])
        dep_missing.prompt_tokens = None
        dep_missing.completion_tokens = None

        combined = merge_deployment_metrics([dep_complete, dep_missing])

        assert combined.tokens_per_minute is not None
        assert combined.tokens_per_minute.values == [3300]
        assert combined.prompt_tokens is None
        assert combined.completion_tokens is None

    def test_sparse_token_shape_disables_cache_aware_consolidated_shape(self):
        dep_complete = _make_deployment("complete", "gpt-4o", [0, 5], [1100, 1100])
        dep_sparse = _make_deployment("sparse", "gpt-4o", [0, 5], [2200, 2200])
        dep_sparse.prompt_tokens = _make_series([0], [1320], "PromptTokens")
        dep_sparse.completion_tokens = _make_series([0], [880], "CompletionTokens")

        combined = merge_deployment_metrics([dep_complete, dep_sparse])

        assert combined.prompt_tokens is None
        assert combined.completion_tokens is None

    def test_time_window_spans_all_deployments(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [10, 15], [3000, 4000])

        combined = merge_deployment_metrics([dep_a, dep_b])
        assert combined.start_time == _ts(0)
        assert combined.end_time == _ts(15)

    def test_three_deployments_merge(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [500, 1000])
        dep_c = _make_deployment("dep-c", "gpt-4o", [0, 5], [200, 300])

        combined = merge_deployment_metrics([dep_a, dep_b, dep_c])
        tpm = combined.tokens_per_minute
        assert tpm is not None
        assert tpm.values == [1700.0, 3300.0]

    def test_latency_p99_uses_max(self):
        dep_a = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0, 5],
            [1000, 2000],
            p99_values=[3000.0, 4000.0],
        )
        dep_b = _make_deployment(
            "dep-b",
            "gpt-4o",
            [0, 5],
            [1000, 2000],
            p99_values=[5000.0, 2000.0],
        )
        combined = merge_deployment_metrics([dep_a, dep_b])
        p99 = combined.time_to_first_byte_p99
        assert p99 is not None
        assert p99.values == [5000.0, 4000.0]

    def test_latency_p50_uses_weighted_average(self):
        dep_a = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0],
            [10000],
            rpm_values=[100.0],
            p50_values=[300.0],
        )
        dep_b = _make_deployment(
            "dep-b",
            "gpt-4o",
            [0],
            [5000],
            rpm_values=[300.0],
            p50_values=[500.0],
        )
        combined = merge_deployment_metrics([dep_a, dep_b])
        p50 = combined.time_to_first_byte_p50
        assert p50 is not None
        # Weighted avg: (300*100 + 500*300) / (100+300) = 450
        assert abs(p50.values[0] - 450.0) < 0.01

    def test_combined_deployment_info_set(self):
        dep_a = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep_b = _make_deployment("dep-b", "gpt-4o", [0, 5], [1000, 2000])
        combined = merge_deployment_metrics([dep_a, dep_b])
        assert combined.deployment_info is not None
        assert combined.deployment_info.model == "gpt-4o"
        assert "consolidated" in combined.deployment_info.name

    def test_cache_rate_is_prompt_token_weighted(self):
        dep_a = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0],
            [1100],
            prompt_values=[1000],
            completion_values=[100],
            cache_values=[0.8],
        )
        dep_b = _make_deployment(
            "dep-b",
            "gpt-4o",
            [0],
            [110],
            prompt_values=[100],
            completion_values=[10],
            cache_values=[0.0],
        )

        combined = merge_deployment_metrics([dep_a, dep_b])

        assert combined.cache_match_rate is not None
        assert combined.cache_match_rate.values[0] == pytest.approx(800 / 1100)


class TestSerializePerDeploymentCacheCharts:
    def test_includes_cache_attribution_per_deployment(self):
        from ptu_advisor.metrics.merge import serialize_per_deployment_charts

        dep = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0, 5],
            [1100, 2200],
            prompt_values=[1000, 2000],
            completion_values=[100, 200],
            cache_values=[0.5, 0.25],
        )
        timestamps = [_ts(0).isoformat(), _ts(5).isoformat()]

        payload = serialize_per_deployment_charts([dep], timestamps)

        cache = payload["prompt_cache"]["per_deployment"]["dep-a"]
        assert cache["match_rate_pct"] == [50.0, 25.0]
        assert cache["cached_prompt_tokens"] == [500.0, 500.0]
        assert cache["active_prompt_tokens"] == [500.0, 1500.0]

    def test_missing_cache_intervals_remain_null(self):
        dep = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0, 5],
            [1100, 2200],
            prompt_values=[1000, 2000],
            completion_values=[100, 200],
        )

        payload = serialize_per_deployment_charts(
            [dep],
            [_ts(0).isoformat(), _ts(5).isoformat()],
        )

        assert payload["prompt_cache"]["per_deployment"]["dep-a"]["match_rate_pct"] == [
            None,
            None,
        ]


# ===================================================================
# compute_individual_payg_cost
# ===================================================================


class TestComputeIndividualPaygCost:
    def test_basic_cost_calculation(self):
        dep = _make_deployment("dep-a", "gpt-4o", [0, 5], [10000.0, 10000.0])
        # avg_tpm = 10000, monthly_tokens = 10000 * 43200 = 432M
        # cost = 432M / 1M * blended_rate = 432 * 5.0 = 2160
        cost = compute_individual_payg_cost(dep, payg_blended_rate=5.0)
        assert abs(cost - 2160.0) < 0.01

    def test_zero_tpm_returns_zero(self):
        dep = _make_deployment("dep-a", "gpt-4o", [0, 5], [0.0, 0.0])
        cost = compute_individual_payg_cost(dep, payg_blended_rate=5.0)
        assert cost == 0.0

    def test_no_tpm_series_returns_zero(self):
        dep = _make_deployment("dep-a", "gpt-4o", [0, 5], [1000, 2000])
        dep.tokens_per_minute = None
        cost = compute_individual_payg_cost(dep, payg_blended_rate=5.0)
        assert cost == 0.0

    def test_cache_aware_cost_prices_cached_input_separately(self):
        dep = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0, 5],
            [1100.0, 1100.0],
            prompt_values=[1000.0, 1000.0],
            completion_values=[100.0, 100.0],
            cache_values=[0.5, 0.5],
        )

        cost = compute_individual_payg_cost(
            dep,
            payg_blended_rate=5.0,
            payg_input_rate=2.0,
            payg_cached_input_rate=1.0,
            payg_output_rate=8.0,
        )

        expected = 500 * 43_200 / 1_000_000 * 2.0
        expected += 500 * 43_200 / 1_000_000 * 1.0
        expected += 100 * 43_200 / 1_000_000 * 8.0
        assert cost == pytest.approx(expected)

    def test_disabled_cache_mode_ignores_observed_cache(self):
        dep = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0],
            [1100.0],
            prompt_values=[1000.0],
            completion_values=[100.0],
            cache_values=[0.8],
        )

        cost = compute_individual_payg_cost(
            dep,
            payg_blended_rate=5.0,
            payg_input_rate=2.0,
            payg_cached_input_rate=1.0,
            payg_output_rate=8.0,
            cache_mode="disabled",
        )

        expected = 1000 * 43_200 / 1_000_000 * 2.0
        expected += 100 * 43_200 / 1_000_000 * 8.0
        assert cost == pytest.approx(expected)

    def test_cache_override_replaces_observed_rate(self):
        dep = _make_deployment(
            "dep-a",
            "gpt-4o",
            [0],
            [1100.0],
            prompt_values=[1000.0],
            completion_values=[100.0],
            cache_values=[0.1],
        )

        cost = compute_individual_payg_cost(
            dep,
            payg_blended_rate=5.0,
            payg_input_rate=2.0,
            payg_cached_input_rate=1.0,
            payg_output_rate=8.0,
            cache_mode="override",
            cache_override_pct=50.0,
        )

        expected = 500 * 43_200 / 1_000_000 * 2.0
        expected += 500 * 43_200 / 1_000_000 * 1.0
        expected += 100 * 43_200 / 1_000_000 * 8.0
        assert cost == pytest.approx(expected)
