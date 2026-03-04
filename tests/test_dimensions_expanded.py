"""Expanded dimension analyzer tests — covers boundaries, edge cases, and all score paths."""

import pytest
from datetime import datetime, timezone, timedelta

import numpy as np

from ptu_advisor.config import AnalysisConfig, ThresholdConfig
from ptu_advisor.metrics.models import (
    DeploymentMetrics,
    DimensionScore,
    TimeSeries,
)
from ptu_advisor.analysis.dimensions import (
    WorkloadShapeAnalyzer,
    CapacityPressureAnalyzer,
    LatencySensitivityAnalyzer,
    LoadPredictabilityAnalyzer,
)


# ============================================================================
# Helpers
# ============================================================================


@pytest.fixture
def config():
    return AnalysisConfig(
        resource_group="rg", workspace="ws", deployment="dep",
    )


def _ts(n, base_val, noise=0.0, name="m"):
    """Helper to create a TimeSeries with n hourly points."""
    base = datetime(2026, 1, 5, tzinfo=timezone.utc)
    timestamps = [base + timedelta(hours=i) for i in range(n)]
    rng = np.random.default_rng(42)
    values = [max(0.0, base_val + rng.normal(0, noise)) for _ in range(n)]
    return TimeSeries(timestamps=timestamps, values=values, metric_name=name)


def _metrics(
    *,
    n=336,
    tpm_mean=10000,
    tpm_noise=0,
    throttled_mean=0,
    successful_mean=100,
    p50=500,
    p95=1000,
    p99=1500,
    rpm_mean=50,
    rpm_noise=0,
    prompt_mean=5000,
    completion_mean=5000,
    model_name="gpt-4o",
):
    """Build a DeploymentMetrics with controllable parameters."""
    base = datetime(2026, 1, 5, tzinfo=timezone.utc)
    timestamps = [base + timedelta(hours=i) for i in range(n)]
    return DeploymentMetrics(
        deployment_name="test",
        model_name=model_name,
        start_time=timestamps[0],
        end_time=timestamps[-1],
        timestamps=timestamps,
        tokens_per_minute=_ts(n, tpm_mean, tpm_noise, "tpm"),
        requests_per_minute=_ts(n, rpm_mean, rpm_noise, "rpm"),
        successful_requests=_ts(n, successful_mean, 0, "success"),
        throttled_requests=_ts(n, throttled_mean, 0, "throttled"),
        time_to_first_byte_p50=_ts(n, p50, 0, "p50"),
        time_to_first_byte_p95=_ts(n, p95, 0, "p95"),
        time_to_first_byte_p99=_ts(n, p99, 0, "p99"),
        prompt_tokens=_ts(n, prompt_mean, 0, "prompt"),
        completion_tokens=_ts(n, completion_mean, 0, "comp"),
    )


# ============================================================================
# WorkloadShapeAnalyzer
# ============================================================================


class TestWorkloadShapeAnalyzer:
    """Extended tests for workload shape dimension."""

    def test_insufficient_data(self, config):
        """< min_data_points → INSUFFICIENT."""
        analyzer = WorkloadShapeAnalyzer(config)
        m = _metrics(n=10, tpm_mean=1000)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.INSUFFICIENT
        assert result.confidence == 0.0
        assert "Insufficient" in result.summary

    def test_stable_workload_low_cv(self, config):
        """CV < 0.3 → POSITIVE."""
        analyzer = WorkloadShapeAnalyzer(config)
        m = _metrics(n=200, tpm_mean=10000, tpm_noise=100)  # noise/mean ≈ 0.01
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE
        assert result.key_metrics["tpm_coefficient_of_variation"] < 0.3

    def test_spiky_workload_high_cv(self, config):
        """CV > 0.7 → NEGATIVE."""
        analyzer = WorkloadShapeAnalyzer(config)
        m = _metrics(n=200, tpm_mean=1000, tpm_noise=1000)  # noise ≈ mean → CV ≈ 1
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEGATIVE

    def test_moderate_cv_neutral(self, config):
        """0.3 < CV < 0.7 → NEUTRAL."""
        analyzer = WorkloadShapeAnalyzer(config)
        # Construct values manually with CV ≈ 0.5
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        n = 200
        timestamps = [base + timedelta(hours=i) for i in range(n)]
        rng = np.random.default_rng(123)
        values = [max(0, 1000 + rng.normal(0, 500)) for _ in range(n)]
        tpm = TimeSeries(timestamps=timestamps, values=values, metric_name="tpm")
        assert 0.3 < tpm.cv < 0.7, f"Test setup: CV = {tpm.cv}"

        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
            tokens_per_minute=tpm,
        )
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEUTRAL

    def test_token_ratio_cv_computed(self, config):
        """When prompt and completion tokens exist, token_ratio_cv is computed."""
        analyzer = WorkloadShapeAnalyzer(config)
        m = _metrics(n=200, tpm_mean=10000, tpm_noise=100, prompt_mean=7000, completion_mean=3000)
        result = analyzer.analyze(m)
        assert "token_ratio_cv" in result.key_metrics
        assert result.key_metrics["token_ratio_cv"] >= 0.0

    def test_token_ratio_cv_zero_completions(self, config):
        """Completion tokens = 0 → division guard, no crash."""
        analyzer = WorkloadShapeAnalyzer(config)
        m = _metrics(n=200, tpm_mean=10000, tpm_noise=100, prompt_mean=5000, completion_mean=0)
        result = analyzer.analyze(m)
        # Should not crash; token_ratio_cv should be 0 (int or float)
        assert result.key_metrics["token_ratio_cv"] == 0

    def test_confidence_scales_with_data(self, config):
        """Confidence should scale with data size (min(1, len/500))."""
        analyzer = WorkloadShapeAnalyzer(config)
        m200 = _metrics(n=200, tpm_mean=10000, tpm_noise=100)
        m500 = _metrics(n=500, tpm_mean=10000, tpm_noise=100)
        r200 = analyzer.analyze(m200)
        r500 = analyzer.analyze(m500)
        assert r500.confidence >= r200.confidence
        assert r500.confidence == pytest.approx(1.0)


# ============================================================================
# CapacityPressureAnalyzer
# ============================================================================


class TestCapacityPressureAnalyzer:
    """Extended tests for capacity pressure dimension."""

    def test_high_throttling_positive(self, config):
        """Throttling > 5% → POSITIVE."""
        analyzer = CapacityPressureAnalyzer(config)
        m = _metrics(n=200, throttled_mean=10, successful_mean=100)
        # throttling_rate = 10/(100+10) ≈ 9%
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE
        assert "Throttling rate" in result.explanation

    def test_low_throttling_low_util_negative(self, config):
        """Throttling < 1% and low utilization → NEGATIVE."""
        analyzer = CapacityPressureAnalyzer(config)
        m = _metrics(n=200, throttled_mean=0, successful_mean=100, tpm_mean=1000)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEGATIVE

    def test_moderate_throttling_neutral(self, config):
        """1% < throttling < 5% with moderate util → NEUTRAL."""
        analyzer = CapacityPressureAnalyzer(config)
        # ~3% throttling
        m = _metrics(n=200, throttled_mean=3, successful_mean=97, tpm_mean=200000)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEUTRAL

    def test_model_config_lookup_used(self, config):
        """Known model → absolute utilization uses PAYG quota."""
        analyzer = CapacityPressureAnalyzer(config)
        # gpt-4o has payg_tpm_quota = 450000
        m = _metrics(n=200, tpm_mean=400000, throttled_mean=0, successful_mean=100, model_name="gpt-4o")
        result = analyzer.analyze(m)
        # Should reference PAYG quota in explanation
        assert "PAYG quota" in result.explanation or "450,000" in result.explanation

    def test_unknown_model_fallback(self, config):
        """Unknown model → falls back to relative utilization."""
        analyzer = CapacityPressureAnalyzer(config)
        m = _metrics(n=200, tpm_mean=5000, throttled_mean=0, successful_mean=100, model_name="custom-ft-model")
        result = analyzer.analyze(m)
        # Should still produce a result without crashing
        assert result.score in list(DimensionScore)

    def test_confidence_scales_with_requests(self, config):
        """Confidence = min(1, total_requests/10000)."""
        analyzer = CapacityPressureAnalyzer(config)
        # 200 points × 100 successful + 0 throttled = ~20000 total
        m = _metrics(n=200, successful_mean=100, throttled_mean=0, tpm_mean=1000)
        result = analyzer.analyze(m)
        assert result.confidence > 0.0

    def test_high_utilization_positive(self, config):
        """TPM utilization > 85% → POSITIVE (even with low throttling)."""
        analyzer = CapacityPressureAnalyzer(config)
        # gpt-4o quota = 450000; tpm_mean = 400000 → 89% utilization via p95
        m = _metrics(n=200, tpm_mean=400000, tpm_noise=10000, throttled_mean=0, successful_mean=100, model_name="gpt-4o")
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE


# ============================================================================
# LatencySensitivityAnalyzer
# ============================================================================


class TestLatencySensitivityAnalyzer:
    """Extended tests for latency sensitivity dimension."""

    def test_no_latency_data_insufficient(self, config):
        """No latency data → INSUFFICIENT."""
        analyzer = LatencySensitivityAnalyzer(config)
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        timestamps = [base + timedelta(hours=i) for i in range(200)]
        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
        )
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.INSUFFICIENT

    def test_high_p95_positive(self, config):
        """P95 > 5000ms → POSITIVE."""
        analyzer = LatencySensitivityAnalyzer(config)
        m = _metrics(n=200, p50=1000, p95=6000, p99=8000)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE
        assert result.key_metrics["p95_latency_ms"] > 5000

    def test_high_variance_ratio_positive(self, config):
        """P99/P50 > 4 → POSITIVE (even if P95 < 5000)."""
        analyzer = LatencySensitivityAnalyzer(config)
        m = _metrics(n=200, p50=500, p95=2000, p99=3000)
        # variance ratio = 3000/500 = 6 > 4
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE
        assert result.key_metrics["latency_variance_ratio"] > 4.0

    def test_stable_low_latency_negative(self, config):
        """P95 < 2000 and ratio < 2.0 → NEGATIVE."""
        analyzer = LatencySensitivityAnalyzer(config)
        m = _metrics(n=200, p50=500, p95=800, p99=900)
        # variance ratio = 900/500 = 1.8 < 2.0
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEGATIVE

    def test_neutral_case(self, config):
        """Moderate latency → NEUTRAL."""
        analyzer = LatencySensitivityAnalyzer(config)
        # P95 = 3000 (between 2000 and 5000), ratio = 4500/1500 = 3 (between 2 and 4)
        m = _metrics(n=200, p50=1500, p95=3000, p99=4500)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEUTRAL

    def test_p50_zero_no_division_error(self, config):
        """P50 = 0 → no ZeroDivisionError in ratio calculation."""
        analyzer = LatencySensitivityAnalyzer(config)
        m = _metrics(n=200, p50=0, p95=1000, p99=2000)
        result = analyzer.analyze(m)
        # ratio defaults to 0 when p50 = 0
        assert result.key_metrics["latency_variance_ratio"] == 0.0
        assert result.score in list(DimensionScore)

    def test_key_metrics_populated(self, config):
        """All 4 latency key metrics should be present."""
        analyzer = LatencySensitivityAnalyzer(config)
        m = _metrics(n=200, p50=500, p95=1000, p99=1500)
        result = analyzer.analyze(m)
        assert "p50_latency_ms" in result.key_metrics
        assert "p95_latency_ms" in result.key_metrics
        assert "p99_latency_ms" in result.key_metrics
        assert "latency_variance_ratio" in result.key_metrics


# ============================================================================
# LoadPredictabilityAnalyzer
# ============================================================================


class TestLoadPredictabilityAnalyzer:
    """Extended tests for load predictability dimension."""

    def test_insufficient_data(self, config):
        """< min_data_points → INSUFFICIENT."""
        analyzer = LoadPredictabilityAnalyzer(config)
        m = _metrics(n=10, rpm_mean=50)
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.INSUFFICIENT

    def test_sustained_predictable_positive(self, config):
        """High sustained rate + high similarity → POSITIVE."""
        analyzer = LoadPredictabilityAnalyzer(config)
        # Create a repeating daily pattern with 14 days (336 hours)
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        n = 336
        timestamps = [base + timedelta(hours=i) for i in range(n)]
        # Predictable daily pattern: higher during business hours, baseline above 30% threshold
        values = []
        for i in range(n):
            hour = i % 24
            if 8 <= hour <= 18:
                values.append(100.0)
            else:
                values.append(50.0)  # Off-hours still above 30% of 100=30 threshold
        rpm = TimeSeries(timestamps=timestamps, values=values, metric_name="rpm")
        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=rpm,
        )
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.POSITIVE

    def test_sparse_negative(self, config):
        """Mostly idle → NEGATIVE."""
        analyzer = LoadPredictabilityAnalyzer(config)
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        n = 336
        timestamps = [base + timedelta(hours=i) for i in range(n)]
        # Mostly zeros with occasional spikes
        rng = np.random.default_rng(42)
        values = [0.0] * n
        for i in rng.choice(n, size=20, replace=False):
            values[i] = 100.0
        rpm = TimeSeries(timestamps=timestamps, values=values, metric_name="rpm")
        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=rpm,
        )
        result = analyzer.analyze(m)
        assert result.score == DimensionScore.NEGATIVE

    def test_moderate_neutral(self, config):
        """Medium sustained rate or low similarity → NEUTRAL."""
        analyzer = LoadPredictabilityAnalyzer(config)
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        n = 336
        timestamps = [base + timedelta(hours=i) for i in range(n)]
        # Moderate: 50% sustained with random pattern (low similarity)
        rng = np.random.default_rng(99)
        values = [rng.uniform(30, 100) if rng.random() > 0.4 else 0.0 for _ in range(n)]
        rpm = TimeSeries(timestamps=timestamps, values=values, metric_name="rpm")
        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=rpm,
        )
        result = analyzer.analyze(m)
        assert result.score in (DimensionScore.NEUTRAL, DimensionScore.NEGATIVE)

    def test_similarity_with_short_data(self, config):
        """48 < n < 168 → daily correlation only (not weekly)."""
        analyzer = LoadPredictabilityAnalyzer(config)
        m = _metrics(n=120, rpm_mean=50, rpm_noise=5)  # 5 days
        result = analyzer.analyze(m)
        assert result.key_metrics["day_over_day_similarity"] >= 0.0

    def test_similarity_exactly_48_points(self, config):
        """Boundary: exactly 48 data points is minimum for similarity calc."""
        analyzer = LoadPredictabilityAnalyzer(config)
        # With min_data_points default = 100, this will be INSUFFICIENT
        # So test with a threshold override
        custom = AnalysisConfig(
            resource_group="rg", workspace="ws", deployment="dep",
            thresholds=ThresholdConfig(min_data_points=40),
        )
        analyzer2 = LoadPredictabilityAnalyzer(custom)
        m = _metrics(n=48, rpm_mean=50, rpm_noise=1)
        result = analyzer2.analyze(m)
        assert result.score in list(DimensionScore)

    def test_constant_values_zero_std(self, config):
        """All identical values → std = 0 → similarity defaults to 0.5."""
        analyzer = LoadPredictabilityAnalyzer(config)
        base = datetime(2026, 1, 5, tzinfo=timezone.utc)
        n = 200
        timestamps = [base + timedelta(hours=i) for i in range(n)]
        values = [100.0] * n  # Constant
        rpm = TimeSeries(timestamps=timestamps, values=values, metric_name="rpm")
        m = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps[0], end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=rpm,
        )
        result = analyzer.analyze(m)
        # std = 0 → autocorrelation fallback to 0.5
        assert result.key_metrics["day_over_day_similarity"] == pytest.approx(0.5)

    def test_key_metrics_populated(self, config):
        """All expected key_metrics are present."""
        analyzer = LoadPredictabilityAnalyzer(config)
        m = _metrics(n=200, rpm_mean=50, rpm_noise=10)
        result = analyzer.analyze(m)
        assert "sustained_traffic_pct" in result.key_metrics
        assert "day_over_day_similarity" in result.key_metrics
        assert "total_data_points" in result.key_metrics


# ============================================================================
# Cross-dimension integration: each analyzer returns correct result type
# ============================================================================


class TestAllAnalyzersReturnCorrectStructure:
    """Ensure every analyzer returns a well-formed DimensionResult."""

    @pytest.mark.parametrize("AnalyzerCls", [
        WorkloadShapeAnalyzer,
        CapacityPressureAnalyzer,
        LatencySensitivityAnalyzer,
        LoadPredictabilityAnalyzer,
    ])
    def test_result_structure(self, config, AnalyzerCls):
        m = _metrics(n=200)
        analyzer = AnalyzerCls(config)
        result = analyzer.analyze(m)
        assert result.name
        assert result.score in list(DimensionScore)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.summary, str)
        assert isinstance(result.explanation, str)
        assert isinstance(result.key_metrics, dict)
