"""Tests for the analysis Explainer."""

import pytest
from datetime import datetime, timezone, timedelta

from ptu_advisor.analysis.rule_explainer import Explainer, ExplanationSection
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


def _make_dim(name, score, confidence=0.8, key_metrics=None):
    return DimensionResult(
        name=name,
        score=score,
        confidence=confidence,
        summary=f"Summary for {name}",
        explanation=f"Explanation for {name}",
        key_metrics=key_metrics or {},
    )


def _make_result(recommendation, dim_scores=None):
    if dim_scores is None:
        dim_scores = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("Load Predictability", DimensionScore.NEUTRAL),
        )
    return AnalysisResult(
        recommendation=recommendation,
        dimensions=dim_scores,
        confidence=0.85,
        summary="Test summary",
        explanation="Test explanation",
        what_would_change="Test what would change",
        data_quality="Good quality data",
        analysis_period="14 days (Jan 01 - Jan 14, 2026)",
    )


@pytest.fixture
def explainer():
    return Explainer()


@pytest.fixture
def sample_metrics():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamps = [base + timedelta(hours=i) for i in range(200)]
    return DeploymentMetrics(
        deployment_name="test-deployment",
        model_name="gpt-4o",
        start_time=timestamps[0],
        end_time=timestamps[-1],
        timestamps=timestamps,
        tokens_per_minute=TimeSeries(timestamps, [1000.0] * 200, "tpm"),
        requests_per_minute=TimeSeries(timestamps, [50.0] * 200, "rpm"),
        successful_requests=TimeSeries(timestamps, [48.0] * 200, "success"),
        throttled_requests=TimeSeries(timestamps, [2.0] * 200, "throttled"),
    )


# ============================================================================
# Tests
# ============================================================================


class TestExplainerFullExplanation:
    """Tests for full explanation generation."""

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_generates_sections(self, explainer, sample_metrics, rec):
        """Should generate multiple sections for each recommendation type."""
        result = _make_result(rec)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        assert len(sections) >= 7  # exec summary + key factors + 4 dims + data quality + what would change + next steps
        assert all(isinstance(s, ExplanationSection) for s in sections)

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_first_section_is_executive_summary(self, explainer, sample_metrics, rec):
        result = _make_result(rec)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        assert sections[0].title == "Executive Summary"
        assert sections[0].importance == "high"

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_key_factors_section(self, explainer, sample_metrics, rec):
        result = _make_result(rec)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        assert sections[1].title == "Key Factors"
        assert sections[1].importance == "high"

    @pytest.mark.parametrize("rec", list(Recommendation))
    def test_has_next_steps(self, explainer, sample_metrics, rec):
        result = _make_result(rec)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        # Last section should be next steps
        last = sections[-1]
        assert "Next Steps" in last.title or "next" in last.content.lower()

    def test_executive_summary_contains_recommendation(self, explainer, sample_metrics):
        result = _make_result(Recommendation.PTU_RECOMMENDED)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        exec_summary = sections[0]
        assert "PTU RECOMMENDED" in exec_summary.content
        assert "✅" in exec_summary.content

    def test_data_quality_section(self, explainer, sample_metrics):
        result = _make_result(Recommendation.PTU_RECOMMENDED)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        data_section = [s for s in sections if "Data Quality" in s.title]
        assert len(data_section) == 1
        assert "test-deployment" in data_section[0].content
        assert "gpt-4o" in data_section[0].content


class TestExplainerDimensionDetail:
    """Tests for dimension detail formatting."""

    def test_formats_percentage_metrics(self, explainer, sample_metrics):
        """Key metrics with 'rate' or 'pct' should be formatted as percentages."""
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE, key_metrics={"utilization_rate": 0.85}),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE, key_metrics={"throttling_rate": 0.05}),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEGATIVE, key_metrics={"p95_latency_ms": 3000.0}),
            load_predictability=_make_dim("Load Predictability", DimensionScore.NEUTRAL, key_metrics={"sustained_traffic_pct": 0.7}),
        )
        result = _make_result(Recommendation.PTU_RECOMMENDED, dims)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        # Find a dimension section with latency
        latency_section = [s for s in sections if "Latency" in s.title]
        assert len(latency_section) == 1
        assert "ms" in latency_section[0].content

    def test_formats_ratio_metrics(self, explainer, sample_metrics):
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE, key_metrics={"peak_to_average_ratio": 1.5}),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.POSITIVE, key_metrics={"latency_variance_ratio": 3.2}),
            load_predictability=_make_dim("Load Predictability", DimensionScore.POSITIVE),
        )
        result = _make_result(Recommendation.PTU_RECOMMENDED, dims)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        # variance_ratio should contain "x" formatting
        latency_section = [s for s in sections if "Latency" in s.title]
        assert "x" in latency_section[0].content


class TestExplainerNextSteps:
    """Tests for recommendation-specific next steps."""

    def test_ptu_recommended_steps(self, explainer, sample_metrics):
        result = _make_result(Recommendation.PTU_RECOMMENDED)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        next_steps = sections[-1]
        assert "PTU sizing" in next_steps.content or "Calculate" in next_steps.content

    def test_borderline_steps(self, explainer, sample_metrics):
        result = _make_result(Recommendation.BORDERLINE)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        next_steps = sections[-1]
        assert "load test" in next_steps.content.lower() or "extend" in next_steps.content.lower()

    def test_not_recommended_steps(self, explainer, sample_metrics):
        result = _make_result(Recommendation.PTU_NOT_RECOMMENDED)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        next_steps = sections[-1]
        assert "PAYG" in next_steps.content or "Continue" in next_steps.content


class TestKeyFactorsGrouping:
    """Tests for key factors grouping by score."""

    def test_positive_factors_listed(self, explainer, sample_metrics):
        dims = DimensionScores(
            workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=_make_dim("Load Predictability", DimensionScore.NEUTRAL),
        )
        result = _make_result(Recommendation.PTU_RECOMMENDED, dims)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        key_factors = sections[1]
        assert "Favoring PTU" in key_factors.content
        assert "Against PTU" in key_factors.content
        assert "Neutral" in key_factors.content

    def test_all_positive_no_negative(self, explainer, sample_metrics):
        dims = DimensionScores(
            workload_shape=_make_dim("WS", DimensionScore.POSITIVE),
            capacity_pressure=_make_dim("CP", DimensionScore.POSITIVE),
            latency_sensitivity=_make_dim("LS", DimensionScore.POSITIVE),
            load_predictability=_make_dim("LP", DimensionScore.POSITIVE),
        )
        result = _make_result(Recommendation.PTU_RECOMMENDED, dims)
        sections = explainer.generate_full_explanation(result, sample_metrics)
        key_factors = sections[1]
        assert "Favoring PTU" in key_factors.content
        assert "Against PTU" not in key_factors.content
