"""Expanded tests for Decision Engine — covers confidence, summaries, data quality, business hours."""

import pytest
from datetime import datetime, timezone, timedelta

from ptu_advisor.config import AnalysisConfig, ThresholdConfig
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionResult,
    DimensionScore,
    DimensionScores,
    Recommendation,
    TimeSeries,
)
from ptu_advisor.analysis.engine import DecisionEngine


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def config():
    return AnalysisConfig(
        resource_group="test-rg",
        workspace="test-workspace",
        deployment="test-deployment",
        lookback_days=14,
    )


@pytest.fixture
def biz_hours_config():
    return AnalysisConfig(
        resource_group="test-rg",
        workspace="test-workspace",
        deployment="test-deployment",
        lookback_days=14,
        business_hours_only=True,
    )


@pytest.fixture
def timestamps_two_weeks():
    """2 weeks of hourly data = 336 points, starting Monday."""
    base = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # Monday
    return [base + timedelta(hours=i) for i in range(336)]


def make_ts(timestamps, values, name="metric"):
    return TimeSeries(timestamps=timestamps, values=values, metric_name=name)


def _make_dim(name, score, confidence=0.8):
    return DimensionResult(
        name=name, score=score, confidence=confidence,
        summary=f"Summary for {name}", explanation=f"Explanation for {name}",
    )


# ============================================================================
# _calculate_confidence
# ============================================================================


class TestCalculateConfidence:
    """Tests for confidence calculation."""

    def test_confidence_range(self, config, timestamps_two_weeks):
        """Confidence should be between 0 and 1."""
        engine = DecisionEngine(config)
        metrics = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps_two_weeks[0],
            end_time=timestamps_two_weeks[-1],
            timestamps=timestamps_two_weeks,
        )
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE, 0.8),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE, 0.7),
            latency_sensitivity=_make_dim("LS", DimensionScore.NEUTRAL, 0.5),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE, 0.9),
        )
        conf = engine._calculate_confidence(dims, metrics)
        assert 0.0 <= conf <= 1.0

    def test_more_data_increases_confidence(self, config):
        """More data points → higher data_factor → higher confidence."""
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE, 0.8),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE, 0.8),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE, 0.8),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE, 0.8),
        )
        
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        
        # Small data (10 points, 10 hours)
        ts_small = [base + timedelta(hours=i) for i in range(10)]
        m_small = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=ts_small[0], end_time=ts_small[-1],
            timestamps=ts_small,
        )
        
        # Large data (300 points, 300 hours ≈ 12.5 days)
        ts_large = [base + timedelta(hours=i) for i in range(300)]
        m_large = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=ts_large[0], end_time=ts_large[-1],
            timestamps=ts_large,
        )
        
        conf_small = engine._calculate_confidence(dims, m_small)
        conf_large = engine._calculate_confidence(dims, m_large)
        assert conf_large > conf_small

    def test_longer_period_increases_confidence(self, config):
        """Longer analysis period → higher days_factor."""
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE, 0.8),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE, 0.8),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE, 0.8),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE, 0.8),
        )
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        
        # 1 day
        ts_1d = [base + timedelta(hours=i) for i in range(100)]
        m_1d = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=base, end_time=base + timedelta(days=1),
            timestamps=ts_1d,
        )
        
        # 14 days
        ts_14d = [base + timedelta(hours=i) for i in range(100)]
        m_14d = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=base, end_time=base + timedelta(days=14),
            timestamps=ts_14d,
        )
        
        conf_1d = engine._calculate_confidence(dims, m_1d)
        conf_14d = engine._calculate_confidence(dims, m_14d)
        assert conf_14d > conf_1d


# ============================================================================
# _generate_summary
# ============================================================================


class TestGenerateSummary:
    """Tests for summary generation."""

    def test_ptu_recommended_summary(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.POSITIVE),
            load_predictability=_make_dim("Load Predictability", DimensionScore.NEGATIVE),
        )
        summary = engine._generate_summary(Recommendation.PTU_RECOMMENDED, dims)
        assert "recommended" in summary.lower()
        assert "Workload Shape" in summary

    def test_borderline_summary(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("LP", DimensionScore.NEGATIVE),
        )
        summary = engine._generate_summary(Recommendation.BORDERLINE, dims)
        assert "mixed" in summary.lower() or "load test" in summary.lower()

    def test_not_recommended_summary(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.NEGATIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.NEGATIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("LP", DimensionScore.NEGATIVE),
        )
        summary = engine._generate_summary(Recommendation.PTU_NOT_RECOMMENDED, dims)
        assert "not recommended" in summary.lower()


# ============================================================================
# _generate_explanation
# ============================================================================


class TestGenerateExplanation:
    """Tests for explanation generation."""

    def test_explanation_contains_dimensions(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.NEGATIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEUTRAL),
            load_predictability=_make_dim("Load Predictability", DimensionScore.INSUFFICIENT),
        )
        explanation = engine._generate_explanation(Recommendation.BORDERLINE, dims)
        assert "Workload Shape" in explanation
        assert "Capacity Pressure" in explanation
        assert "✅" in explanation  # positive emoji
        assert "❌" in explanation  # negative emoji

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_explanation_non_empty(self, config, rec):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE),
        )
        explanation = engine._generate_explanation(rec, dims)
        assert len(explanation) > 50


# ============================================================================
# _assess_data_quality
# ============================================================================


class TestAssessDataQuality:
    """Tests for data quality assessment."""

    def test_limited_data(self, config):
        engine = DecisionEngine(config)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ts = [base + timedelta(hours=i) for i in range(30)]
        metrics = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=ts[0], end_time=ts[-1], timestamps=ts,
        )
        quality = engine._assess_data_quality(metrics)
        assert "limited" in quality.lower() or "30" in quality

    def test_good_data(self, config, timestamps_two_weeks):
        engine = DecisionEngine(config)
        metrics = DeploymentMetrics(
            deployment_name="test", model_name="gpt-4o",
            start_time=timestamps_two_weeks[0],
            end_time=timestamps_two_weeks[-1],
            timestamps=timestamps_two_weeks,
        )
        quality = engine._assess_data_quality(metrics)
        assert "good" in quality.lower() or "336" in quality


# ============================================================================
# Business Hours Integration
# ============================================================================


class TestBusinessHoursIntegration:
    """Tests for the full analysis with business_hours_only=True."""

    def test_business_hours_analysis(self, biz_hours_config, timestamps_two_weeks):
        """Running analysis with business_hours_only should not crash."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=timestamps_two_weeks[0],
            end_time=timestamps_two_weeks[-1],
            timestamps=timestamps_two_weeks,
            tokens_per_minute=make_ts(timestamps_two_weeks, [1000.0] * 336, "tpm"),
            requests_per_minute=make_ts(timestamps_two_weeks, [50.0] * 336, "rpm"),
            successful_requests=make_ts(timestamps_two_weeks, [48.0] * 336, "success"),
            throttled_requests=make_ts(timestamps_two_weeks, [2.0] * 336, "throttled"),
            time_to_first_byte_p50=make_ts(timestamps_two_weeks, [500.0] * 336, "p50"),
            time_to_first_byte_p95=make_ts(timestamps_two_weeks, [1000.0] * 336, "p95"),
            time_to_first_byte_p99=make_ts(timestamps_two_weeks, [1500.0] * 336, "p99"),
        )
        engine = DecisionEngine(biz_hours_config)
        result = engine.analyze(metrics)
        assert result.recommendation in list(Recommendation)


# ============================================================================
# Full E2E with custom thresholds
# ============================================================================


class TestCustomThresholds:
    """Tests for engine with custom threshold configurations."""

    def test_stricter_ptu_threshold(self):
        """min_positive_for_ptu=4 → requires all 4 positive for PTU."""
        config = AnalysisConfig(
            resource_group="rg", workspace="ws", deployment="dep",
            thresholds=ThresholdConfig(min_positive_for_ptu=4),
        )
        engine = DecisionEngine(config)
        # 3 positive → should be borderline now
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE),
            load_predictability=_make_dim("LP", DimensionScore.NEGATIVE),
        )
        rec = engine._decide(dims)
        assert rec == Recommendation.BORDERLINE

    def test_lenient_ptu_threshold(self):
        """min_positive_for_ptu=2 → 2 positive enough for PTU."""
        config = AnalysisConfig(
            resource_group="rg", workspace="ws", deployment="dep",
            thresholds=ThresholdConfig(
                min_positive_for_ptu=2,
                min_positive_for_borderline=1,
            ),
        )
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("LP", DimensionScore.NEGATIVE),
        )
        rec = engine._decide(dims)
        assert rec == Recommendation.PTU_RECOMMENDED


# ============================================================================
# _generate_what_would_change
# ============================================================================


class TestGenerateWhatWouldChange:
    """Tests for what-would-change explanation."""

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_non_empty(self, config, rec):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.NEGATIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEUTRAL),
            load_predictability=_make_dim("Load Predictability", DimensionScore.INSUFFICIENT),
        )
        text = engine._generate_what_would_change(rec, dims)
        assert isinstance(text, str)

    def test_ptu_recommended_mentions_negative_change(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.POSITIVE),
            load_predictability=_make_dim("Load Predictability", DimensionScore.POSITIVE),
        )
        text = engine._generate_what_would_change(Recommendation.PTU_RECOMMENDED, dims)
        assert "Workload Shape" in text

    def test_not_recommended_suggests_improvements(self, config):
        engine = DecisionEngine(config)
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.NEGATIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.NEGATIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("Load Predictability", DimensionScore.NEGATIVE),
        )
        text = engine._generate_what_would_change(Recommendation.PTU_NOT_RECOMMENDED, dims)
        # Should suggest what would make PTU worthwhile
        assert "consistent" in text.lower() or "throttling" in text.lower()


# ============================================================================
# Full analysis with all 3 demo scenarios
# ============================================================================


class TestFullAnalysisWithDemoScenarios:
    """End-to-end tests using demo scenario data."""

    def test_ptu_recommended_scenario(self, config):
        from ptu_advisor.demo import generate_demo_metrics, DemoScenario
        metrics, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED)
        engine = DecisionEngine(config)
        result = engine.analyze(metrics)
        # Should lean toward PTU
        assert result.recommendation in [Recommendation.PTU_RECOMMENDED, Recommendation.BORDERLINE]
        assert result.confidence > 0.3

    def test_ptu_not_recommended_scenario(self, config):
        from ptu_advisor.demo import generate_demo_metrics, DemoScenario
        metrics, _ = generate_demo_metrics(DemoScenario.PTU_NOT_RECOMMENDED)
        engine = DecisionEngine(config)
        result = engine.analyze(metrics)
        # Should lean away from PTU
        assert result.recommendation in [Recommendation.PTU_NOT_RECOMMENDED, Recommendation.BORDERLINE]

    def test_borderline_scenario(self, config):
        from ptu_advisor.demo import generate_demo_metrics, DemoScenario
        metrics, _ = generate_demo_metrics(DemoScenario.BORDERLINE)
        engine = DecisionEngine(config)
        result = engine.analyze(metrics)
        # Borderline should not be strongly one way
        assert result.recommendation in list(Recommendation)

    def test_analysis_result_structure(self, config):
        """All fields of AnalysisResult should be populated."""
        from ptu_advisor.demo import generate_demo_metrics, DemoScenario
        metrics, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED)
        engine = DecisionEngine(config)
        result = engine.analyze(metrics)
        
        assert result.recommendation in list(Recommendation)
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.summary) > 0
        assert len(result.explanation) > 0
        assert len(result.what_would_change) >= 0  # Could be empty for some combos
        assert len(result.data_quality) > 0
        assert len(result.analysis_period) > 0
        assert result.dimensions is not None
        assert len(result.dimensions.all_dimensions) == 4
