"""Tests for chart generation."""

import pytest
from datetime import datetime, timezone, timedelta

from ptu_advisor.visualization.charts import ChartGenerator, Chart
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionResult,
    DimensionScore,
    DimensionScores,
    Recommendation,
    TimeSeries,
)


# ============================================================================
# Fixtures
# ============================================================================


def _make_dim(name, score):
    return DimensionResult(name=name, score=score, confidence=0.8, summary="s", explanation="e")


@pytest.fixture
def sample_timestamps():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [base + timedelta(hours=i) for i in range(200)]


@pytest.fixture
def full_metrics(sample_timestamps):
    """Metrics with all fields populated."""
    return DeploymentMetrics(
        deployment_name="test-deploy",
        model_name="gpt-4o",
        start_time=sample_timestamps[0],
        end_time=sample_timestamps[-1],
        timestamps=sample_timestamps,
        tokens_per_minute=TimeSeries(sample_timestamps, [50000.0] * 200, "tpm"),
        requests_per_minute=TimeSeries(sample_timestamps, [100.0] * 200, "rpm"),
        successful_requests=TimeSeries(sample_timestamps, [95.0] * 200, "success"),
        throttled_requests=TimeSeries(sample_timestamps, [5.0] * 200, "throttled"),
        time_to_first_byte_p50=TimeSeries(sample_timestamps, [500.0] * 200, "p50"),
        time_to_first_byte_p95=TimeSeries(sample_timestamps, [2000.0] * 200, "p95"),
        time_to_first_byte_p99=TimeSeries(sample_timestamps, [4000.0] * 200, "p99"),
        prompt_tokens=TimeSeries(sample_timestamps, [30000.0] * 200, "prompt"),
        completion_tokens=TimeSeries(sample_timestamps, [20000.0] * 200, "completion"),
        cache_match_rate=TimeSeries(sample_timestamps, [0.6] * 200, "cache", unit="Ratio"),
    )


@pytest.fixture
def sample_result():
    dims = DimensionScores(
        workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
        capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
        latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEGATIVE),
        load_predictability=_make_dim("Load Predictability", DimensionScore.NEUTRAL),
    )
    return AnalysisResult(
        recommendation=Recommendation.PTU_RECOMMENDED,
        dimensions=dims,
        confidence=0.85,
        summary="PTU recommended",
        explanation="Explanation",
        what_would_change="Changes",
        data_quality="Good",
        analysis_period="14 days",
    )


@pytest.fixture
def generator():
    from ptu_advisor.config import AnalysisConfig
    config = AnalysisConfig(
        resource_group="test-rg",
        workspace="test-ws",
        deployment="test-deploy",
    )
    return ChartGenerator(config)


# ============================================================================
# Chart Generation
# ============================================================================


class TestChartGenerator:
    """Tests for ChartGenerator."""

    def test_generate_returns_charts(self, generator, full_metrics, sample_result):
        charts = generator.generate(full_metrics, sample_result)
        assert isinstance(charts, list)
        assert len(charts) > 0
        assert all(isinstance(c, Chart) for c in charts)

    def test_chart_has_required_fields(self, generator, full_metrics, sample_result):
        charts = generator.generate(full_metrics, sample_result)
        for chart in charts:
            assert chart.name
            assert chart.title
            assert chart.image_base64
            assert len(chart.image_base64) > 100  # Non-trivial base64

    def test_chart_names(self, generator, full_metrics, sample_result):
        """Should produce TPM, requests, latency, throttling, radar charts."""
        charts = generator.generate(full_metrics, sample_result)
        names = [c.name for c in charts]
        # At minimum: tpm, requests, latency, throttling, radar
        assert len(names) >= 4
        assert "prompt_cache" in names

    def test_html_img_tag(self, generator, full_metrics, sample_result):
        charts = generator.generate(full_metrics, sample_result)
        for chart in charts:
            tag = chart.html_img_tag
            assert tag.startswith("<img")
            assert "base64" in tag

    def test_with_missing_metrics(self, sample_timestamps, generator, sample_result):
        """Should handle missing optional metrics gracefully."""
        minimal_metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=sample_timestamps[0],
            end_time=sample_timestamps[-1],
            timestamps=sample_timestamps,
            tokens_per_minute=TimeSeries(sample_timestamps, [1000.0] * 200, "tpm"),
        )
        # Should not crash, but may produce fewer charts
        charts = generator.generate(minimal_metrics, sample_result)
        assert isinstance(charts, list)

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_radar_chart_different_recommendations(
        self, generator, full_metrics, rec
    ):
        """Radar chart should work for all recommendation types."""
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE),
        )
        result = AnalysisResult(
            recommendation=rec,
            dimensions=dims,
            confidence=0.85,
            summary="s",
            explanation="e",
            what_would_change="w",
            data_quality="Good",
            analysis_period="14 days",
        )
        charts = generator.generate(full_metrics, result)
        assert len(charts) > 0
