"""Comprehensive tests for data models (TimeSeries, DeploymentMetrics, etc.)."""

import pytest
import warnings
from datetime import datetime, timezone, timedelta

from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentInfo,
    DeploymentMetrics,
    DimensionResult,
    DimensionScore,
    DimensionScores,
    MetricName,
    AggregationType,
    Recommendation,
    TimeSeries,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def hourly_timestamps():
    """Create 14 days of hourly timestamps (336 points)."""
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    return [base + timedelta(hours=i) for i in range(336)]


@pytest.fixture
def business_hour_timestamps():
    """Create timestamps covering 2 weeks with clear business/non-business hours."""
    base = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # Monday
    return [base + timedelta(hours=i) for i in range(336)]


def make_ts(timestamps, values, name="test_metric", unit=""):
    """Helper to create a TimeSeries."""
    return TimeSeries(
        timestamps=timestamps,
        values=values,
        metric_name=name,
        unit=unit,
    )


# ============================================================================
# TimeSeries - Basic Statistics
# ============================================================================


class TestTimeSeriesBasicStats:
    """Tests for basic statistical properties of TimeSeries."""

    def test_empty_values_return_zero(self):
        """All stats on empty TimeSeries should return 0."""
        ts = TimeSeries(timestamps=[], values=[], metric_name="empty")
        assert ts.mean == 0.0
        assert ts.std == 0.0
        assert ts.cv == 0.0
        assert ts.min == 0.0
        assert ts.max == 0.0
        assert ts.p50 == 0.0
        assert ts.p95 == 0.0
        assert ts.p99 == 0.0
        assert ts.total == 0.0
        assert ts.non_zero_count == 0
        assert ts.zero_percentage == 0.0

    def test_single_value(self):
        """TimeSeries with one value."""
        now = datetime.now(timezone.utc)
        ts = TimeSeries(timestamps=[now], values=[42.0], metric_name="single")
        assert ts.mean == 42.0
        assert ts.std == 0.0
        assert ts.cv == 0.0
        assert ts.min == 42.0
        assert ts.max == 42.0
        assert ts.total == 42.0
        assert ts.p50 == 42.0
        assert len(ts) == 1

    def test_known_statistics(self):
        """Test with known values: [10, 20, 30, 40, 50]."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(5)]
        ts = TimeSeries(timestamps=timestamps, values=[10, 20, 30, 40, 50], metric_name="known")
        
        assert ts.mean == 30.0
        assert ts.min == 10.0
        assert ts.max == 50.0
        assert ts.total == 150.0
        assert ts.p50 == 30.0
        assert ts.non_zero_count == 5
        assert ts.zero_percentage == 0.0
        assert ts.std > 0

    def test_cv_constant_values(self):
        """Constant values → CV = 0."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(10)]
        ts = TimeSeries(timestamps=timestamps, values=[100.0] * 10, metric_name="const")
        assert ts.cv == 0.0

    def test_cv_variable_values(self):
        """Variable values → CV > 0."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(4)]
        ts = TimeSeries(timestamps=timestamps, values=[10, 100, 10, 100], metric_name="var")
        assert ts.cv > 0

    def test_cv_all_zeros(self):
        """All zeros → CV = 0 (no division by zero)."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(5)]
        ts = TimeSeries(timestamps=timestamps, values=[0.0] * 5, metric_name="zeros")
        assert ts.cv == 0.0

    def test_zero_percentage(self):
        """Half zeros → zero_percentage = 0.5."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(10)]
        values = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        ts = TimeSeries(timestamps=timestamps, values=values, metric_name="half_zero")
        assert ts.zero_percentage == 0.5
        assert ts.non_zero_count == 5

    def test_percentile_arbitrary(self):
        """Test arbitrary percentile calculation."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(100)]
        values = list(range(100))
        ts = TimeSeries(timestamps=timestamps, values=values, metric_name="range")
        assert ts.percentile(0) == 0.0
        assert ts.percentile(100) == 99.0
        assert ts.p95 == pytest.approx(94.05, abs=1.0)

    def test_len(self):
        """__len__ returns count of values."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(minutes=i) for i in range(7)]
        ts = TimeSeries(timestamps=timestamps, values=[1] * 7, metric_name="len")
        assert len(ts) == 7


# ============================================================================
# TimeSeries - Utilization Pattern Metrics
# ============================================================================


class TestTimeSeriesUtilizationPatterns:
    """Tests for TimeSeries utilization pattern methods."""

    def test_hourly_distribution(self, hourly_timestamps):
        """Hourly distribution covers 0-23 hours."""
        values = [float(ts.hour) for ts in hourly_timestamps]
        ts = make_ts(hourly_timestamps, values, "hourly")
        dist = ts.hourly_distribution()
        assert len(dist) == 24
        assert all(h in dist for h in range(24))
        # Hour 0 should have avg ~0, hour 12 should have avg ~12
        assert dist[0] == pytest.approx(0.0, abs=0.1)
        assert dist[12] == pytest.approx(12.0, abs=0.1)

    def test_weekly_distribution(self, hourly_timestamps):
        """Weekly distribution covers 0-6 weekdays."""
        values = [float(ts.weekday()) for ts in hourly_timestamps]
        ts = make_ts(hourly_timestamps, values, "weekly")
        dist = ts.weekly_distribution()
        assert len(dist) == 7
        assert all(d in dist for d in range(7))

    def test_peak_to_average_ratio_stable(self):
        """Constant values → PAR close to 1.0."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(100)]
        ts = make_ts(timestamps, [100.0] * 100, "stable")
        assert ts.peak_to_average_ratio == pytest.approx(1.0, abs=0.01)

    def test_peak_to_average_ratio_spiky(self):
        """Spiky values → PAR > 2."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(100)]
        values = [10.0] * 80 + [1000.0] * 20  # 20% spike → P95=1000, mean≈208
        ts = make_ts(timestamps, values, "spiky")
        assert ts.peak_to_average_ratio > 2.0

    def test_peak_to_average_ratio_zero_mean(self):
        """Zero mean → PAR = 0."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(10)]
        ts = make_ts(timestamps, [0.0] * 10, "zeros")
        assert ts.peak_to_average_ratio == 0.0

    def test_sustained_utilization_rate_all_active(self):
        """All values above threshold → 100%."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(100)]
        ts = make_ts(timestamps, [100.0] * 100, "active")
        rate = ts.sustained_utilization_rate(threshold_pct=0.3)
        assert rate == 100.0

    def test_sustained_utilization_rate_all_zero(self):
        """All zero values → 0% sustained utilization."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(10)]
        ts = make_ts(timestamps, [0.0] * 10, "idle")
        rate = ts.sustained_utilization_rate(threshold_pct=0.3)
        assert rate == 0.0

    def test_sustained_utilization_rate_empty(self):
        """Empty values → 0%."""
        ts = TimeSeries(timestamps=[], values=[], metric_name="empty")
        assert ts.sustained_utilization_rate() == 0.0

    def test_sustained_utilization_rate_partial(self):
        """Half above threshold → ~50%."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(100)]
        values = [100.0] * 50 + [1.0] * 50  # 50 above 30% of 100=30, 50 below
        ts = make_ts(timestamps, values, "partial")
        rate = ts.sustained_utilization_rate(threshold_pct=0.3)
        assert rate == pytest.approx(50.0, abs=1.0)

    def test_active_hours_percentage(self):
        """Active hours with some zeros."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(100)]
        values = [100.0] * 70 + [0.0] * 30
        ts = make_ts(timestamps, values, "active_hours")
        pct = ts.active_hours_percentage
        assert pct > 60  # ~70% should have > 10% of mean activity

    def test_active_hours_empty(self):
        """Empty → 0%."""
        ts = TimeSeries(timestamps=[], values=[], metric_name="empty")
        assert ts.active_hours_percentage == 0.0

    def test_active_hours_all_zero(self):
        """All zeros → 0% (mean is 0 so no threshold can be exceeded)."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(10)]
        ts = make_ts(timestamps, [0.0] * 10, "zeros")
        assert ts.active_hours_percentage == 0.0

    def test_business_hours_concentration(self, hourly_timestamps):
        """Usage concentrated during business hours (9-18)."""
        # Only generate load during hours 9-18
        values = [100.0 if 9 <= ts.hour <= 18 else 0.0 for ts in hourly_timestamps]
        ts = make_ts(hourly_timestamps, values, "biz_hours")
        conc = ts.business_hours_concentration
        assert conc == 100.0  # All usage during 9-18

    def test_business_hours_concentration_empty(self):
        """Empty → 0."""
        ts = TimeSeries(timestamps=[], values=[], metric_name="empty")
        assert ts.business_hours_concentration == 0.0

    def test_business_hours_concentration_all_zero(self):
        """All zeros → 0 (total_sum = 0)."""
        now = datetime.now(timezone.utc)
        timestamps = [now + timedelta(hours=i) for i in range(24)]
        ts = make_ts(timestamps, [0.0] * 24, "zeros")
        assert ts.business_hours_concentration == 0.0

    def test_business_hours_uniform(self, hourly_timestamps):
        """Uniform usage → ~42% concentration (10 hours / 24)."""
        values = [100.0] * len(hourly_timestamps)
        ts = make_ts(hourly_timestamps, values, "uniform")
        conc = ts.business_hours_concentration
        # 10 hours (9-18 inclusive) out of 24 = 10/24 ≈ 41.7%
        assert 40 < conc < 45

    def test_weekend_vs_weekday_ratio(self, hourly_timestamps):
        """Equal usage → ratio close to 1.0."""
        values = [100.0] * len(hourly_timestamps)
        ts = make_ts(hourly_timestamps, values, "uniform")
        ratio = ts.weekend_vs_weekday_ratio
        assert ratio == pytest.approx(1.0, abs=0.01)

    def test_weekend_vs_weekday_ratio_no_weekday(self):
        """All weekend → weekday_avg=0 → ratio=0."""
        # Saturday and Sunday only
        base = datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc)  # Saturday
        timestamps = [base + timedelta(hours=i) for i in range(48)]
        ts = make_ts(timestamps, [100.0] * 48, "weekend_only")
        ratio = ts.weekend_vs_weekday_ratio
        assert ratio == 0.0  # weekday_avg = 0 → returns 0

    def test_weekend_lower_than_weekday(self, hourly_timestamps):
        """Weekend traffic lower → ratio < 1."""
        values = [
            100.0 if ts.weekday() < 5 else 20.0
            for ts in hourly_timestamps
        ]
        ts = make_ts(hourly_timestamps, values, "low_weekend")
        ratio = ts.weekend_vs_weekday_ratio
        assert ratio < 1.0
        assert ratio == pytest.approx(0.2, abs=0.05)


# ============================================================================
# DeploymentMetrics
# ============================================================================


class TestDeploymentMetrics:
    """Tests for DeploymentMetrics computed properties."""

    @pytest.fixture
    def base_timestamps(self):
        base = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # Monday
        return [base + timedelta(hours=i) for i in range(200)]

    def test_total_requests_from_success_and_throttled(self, base_timestamps):
        """total_requests sums successful + throttled."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            successful_requests=make_ts(base_timestamps, [10.0] * 200, "success"),
            throttled_requests=make_ts(base_timestamps, [2.0] * 200, "throttled"),
        )
        assert metrics.total_requests == 2400  # (10+2) * 200

    def test_total_requests_fallback_to_rpm(self, base_timestamps):
        """total_requests falls back to RPM sum when success/throttled = 0."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            requests_per_minute=make_ts(base_timestamps, [50.0] * 200, "rpm"),
        )
        assert metrics.total_requests == 10000  # 50 * 200

    def test_total_requests_no_data(self, base_timestamps):
        """total_requests with no data → 0."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
        )
        assert metrics.total_requests == 0

    def test_throttling_rate(self, base_timestamps):
        """throttling_rate as decimal."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            successful_requests=make_ts(base_timestamps, [90.0] * 200, "success"),
            throttled_requests=make_ts(base_timestamps, [10.0] * 200, "throttled"),
        )
        assert metrics.throttling_rate == pytest.approx(0.1, abs=0.001)

    def test_throttling_rate_no_throttling(self, base_timestamps):
        """No throttled requests → rate = 0."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            successful_requests=make_ts(base_timestamps, [100.0] * 200, "success"),
            throttled_requests=make_ts(base_timestamps, [0.0] * 200, "throttled"),
        )
        assert metrics.throttling_rate == 0.0

    def test_throttling_rate_no_data(self, base_timestamps):
        """Missing fields → rate = 0."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
        )
        assert metrics.throttling_rate == 0.0

    def test_avg_tokens_per_request(self, base_timestamps):
        """avg_tokens_per_request = total_tokens / total_requests."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            tokens_per_minute=make_ts(base_timestamps, [1000.0] * 200, "tpm"),
            requests_per_minute=make_ts(base_timestamps, [10.0] * 200, "rpm"),
        )
        assert metrics.avg_tokens_per_request == 100.0

    def test_avg_tokens_per_request_no_data(self, base_timestamps):
        """Missing data → 0."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
        )
        assert metrics.avg_tokens_per_request == 0.0

    def test_filter_business_hours(self, base_timestamps):
        """Filters to 9-18 weekdays only."""
        values = list(range(200))
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            tokens_per_minute=make_ts(base_timestamps, [float(v) for v in values], "tpm"),
            requests_per_minute=make_ts(base_timestamps, [float(v) for v in values], "rpm"),
        )
        filtered = metrics.filter_business_hours(start_hour=9, end_hour=18, weekdays_only=True)
        # Verify all timestamps are within business hours
        for ts in filtered.timestamps:
            assert ts.weekday() < 5  # weekday
            assert 9 <= ts.hour < 18
        # Should have fewer points than original
        assert len(filtered.timestamps) < len(base_timestamps)

    def test_filter_business_hours_no_match_returns_unfiltered(self):
        """When no timestamps match, return original with warning."""
        # All timestamps are on a Saturday at 3AM
        base = datetime(2026, 1, 3, 3, 0, tzinfo=timezone.utc)  # Saturday 3AM
        timestamps = [base + timedelta(minutes=i) for i in range(10)]
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            filtered = metrics.filter_business_hours()
            assert len(w) == 1
            assert "No data points matched" in str(w[0].message)
        # Returns original unfiltered
        assert len(filtered.timestamps) == 10

    def test_filter_preserves_none_fields(self, base_timestamps):
        """Fields that are None remain None after filtering."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=base_timestamps[0],
            end_time=base_timestamps[-1],
            timestamps=base_timestamps,
            tokens_per_minute=make_ts(base_timestamps, [100.0] * 200, "tpm"),
            # latency fields are None
        )
        filtered = metrics.filter_business_hours()
        assert filtered.time_to_first_byte_p50 is None
        assert filtered.time_to_first_byte_p95 is None
        assert filtered.tokens_per_minute is not None


# ============================================================================
# DimensionResult & DimensionScores
# ============================================================================


class TestDimensionResult:
    """Tests for DimensionResult."""

    def test_is_positive_true(self):
        dr = DimensionResult(
            name="test", score=DimensionScore.POSITIVE, confidence=0.9,
            summary="s", explanation="e",
        )
        assert dr.is_positive is True

    def test_is_positive_false_for_negative(self):
        dr = DimensionResult(
            name="test", score=DimensionScore.NEGATIVE, confidence=0.9,
            summary="s", explanation="e",
        )
        assert dr.is_positive is False

    def test_is_positive_false_for_neutral(self):
        dr = DimensionResult(
            name="test", score=DimensionScore.NEUTRAL, confidence=0.5,
            summary="s", explanation="e",
        )
        assert dr.is_positive is False

    def test_is_positive_false_for_insufficient(self):
        dr = DimensionResult(
            name="test", score=DimensionScore.INSUFFICIENT, confidence=0.0,
            summary="s", explanation="e",
        )
        assert dr.is_positive is False

    def test_key_metrics_default_empty(self):
        dr = DimensionResult(
            name="test", score=DimensionScore.POSITIVE, confidence=0.5,
            summary="s", explanation="e",
        )
        assert dr.key_metrics == {}


class TestDimensionScores:
    """Tests for DimensionScores."""

    @staticmethod
    def _make_dim(name, score):
        return DimensionResult(
            name=name, score=score, confidence=0.8, summary="s", explanation="e"
        )

    def test_all_dimensions_returns_four(self):
        ds = DimensionScores(
            workload_shape=self._make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=self._make_dim("CP", DimensionScore.NEGATIVE),
            latency_sensitivity=self._make_dim("LS", DimensionScore.NEUTRAL),
            load_predictability=self._make_dim("LP", DimensionScore.INSUFFICIENT),
        )
        assert len(ds.all_dimensions) == 4

    def test_positive_count(self):
        ds = DimensionScores(
            workload_shape=self._make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=self._make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=self._make_dim("LS", DimensionScore.NEGATIVE),
            load_predictability=self._make_dim("LP", DimensionScore.NEUTRAL),
        )
        assert ds.positive_count == 2

    def test_positive_count_zero(self):
        ds = DimensionScores(
            workload_shape=self._make_dim("WS", DimensionScore.NEGATIVE),
            capacity_pressure=self._make_dim("CP", DimensionScore.NEGATIVE),
            latency_sensitivity=self._make_dim("LS", DimensionScore.NEUTRAL),
            load_predictability=self._make_dim("LP", DimensionScore.INSUFFICIENT),
        )
        assert ds.positive_count == 0

    def test_average_confidence(self):
        ds = DimensionScores(
            workload_shape=DimensionResult("WS", DimensionScore.POSITIVE, 0.8, "s", "e"),
            capacity_pressure=DimensionResult("CP", DimensionScore.POSITIVE, 0.6, "s", "e"),
            latency_sensitivity=DimensionResult("LS", DimensionScore.POSITIVE, 1.0, "s", "e"),
            load_predictability=DimensionResult("LP", DimensionScore.POSITIVE, 0.4, "s", "e"),
        )
        assert ds.average_confidence == pytest.approx(0.7, abs=0.01)


# ============================================================================
# AnalysisResult
# ============================================================================


class TestAnalysisResult:
    """Tests for AnalysisResult."""

    @staticmethod
    def _make_result(rec):
        dim = DimensionResult("d", DimensionScore.POSITIVE, 0.8, "s", "e")
        dims = DimensionScores(dim, dim, dim, dim)
        return AnalysisResult(
            recommendation=rec,
            dimensions=dims,
            confidence=0.85,
            summary="Summary",
            explanation="Explanation",
            what_would_change="Changes",
            data_quality="Good",
            analysis_period="14 days",
        )

    def test_recommendation_emoji_ptu(self):
        r = self._make_result(Recommendation.PTU_RECOMMENDED)
        assert r.recommendation_emoji == "✅"

    def test_recommendation_emoji_borderline(self):
        r = self._make_result(Recommendation.BORDERLINE)
        assert r.recommendation_emoji == "⚠️"

    def test_recommendation_emoji_not_recommended(self):
        r = self._make_result(Recommendation.PTU_NOT_RECOMMENDED)
        assert r.recommendation_emoji == "❌"

    def test_cost_estimate_default_none(self):
        r = self._make_result(Recommendation.PTU_RECOMMENDED)
        assert r.cost_estimate is None


# ============================================================================
# Enums
# ============================================================================


class TestEnums:
    """Tests for enum values."""

    def test_metric_names(self):
        assert MetricName.REQUESTS == "AzureOpenAIRequests"
        assert MetricName.TOKENS_PER_MINUTE == "TotalTokens"
        assert MetricName.TIME_TO_FIRST_BYTE == "AzureOpenAITimeToResponse"
        assert MetricName.PTU_UTILIZATION == "AzureOpenAIProvisionedManagedUtilizationV2"

    def test_aggregation_types(self):
        assert AggregationType.TOTAL == "Total"
        assert AggregationType.AVERAGE == "Average"

    def test_dimension_scores(self):
        assert DimensionScore.POSITIVE == "positive"
        assert DimensionScore.INSUFFICIENT == "insufficient"

    def test_recommendation_values(self):
        assert Recommendation.PTU_RECOMMENDED == "ptu_recommended"
        assert Recommendation.BORDERLINE == "borderline"
        assert Recommendation.PTU_NOT_RECOMMENDED == "ptu_not_recommended"


# ============================================================================
# DeploymentInfo
# ============================================================================


class TestDeploymentInfo:
    """Tests for DeploymentInfo model."""

    def test_basic_creation(self):
        info = DeploymentInfo(name="my-deploy", model="gpt-4o", sku_type="Standard")
        assert info.name == "my-deploy"
        assert info.model == "gpt-4o"
        assert info.sku_type == "Standard"
        assert info.sku_capacity is None
        assert info.created_date is None

    def test_with_all_fields(self):
        now = datetime.now(timezone.utc)
        info = DeploymentInfo(
            name="my-deploy",
            model="gpt-4o",
            sku_type="ProvisionedManaged",
            sku_capacity=100,
            created_date=now,
        )
        assert info.sku_capacity == 100
        assert info.created_date == now
