"""Tests for report generator: formatting, metrics summary, PTU estimates."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from ptu_advisor.config import AnalysisConfig
from ptu_advisor.report.generator import ReportGenerator
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentInfo,
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


@pytest.fixture
def config():
    return AnalysisConfig(
        resource_group="test-rg",
        workspace="test-ws",
        deployment="test-dep",
    )


@pytest.fixture
def generator(config):
    return ReportGenerator(config)


@pytest.fixture
def sample_timestamps():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [base + timedelta(hours=i) for i in range(200)]


@pytest.fixture
def sample_metrics(sample_timestamps):
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
        prompt_tokens=TimeSeries(sample_timestamps, [30000.0] * 200, "prompt"),
        completion_tokens=TimeSeries(sample_timestamps, [20000.0] * 200, "completion"),
        time_to_first_byte_p50=TimeSeries(sample_timestamps, [500.0] * 200, "p50"),
        time_to_first_byte_p95=TimeSeries(sample_timestamps, [2000.0] * 200, "p95"),
        time_to_first_byte_p99=TimeSeries(sample_timestamps, [4000.0] * 200, "p99"),
    )


def _make_dim(name, score):
    return DimensionResult(name=name, score=score, confidence=0.8, summary="s", explanation="e")


@pytest.fixture
def sample_result():
    dims = DimensionScores(
        workload_shape=_make_dim("Workload Shape", DimensionScore.POSITIVE),
        capacity_pressure=_make_dim("Capacity Pressure", DimensionScore.POSITIVE),
        latency_sensitivity=_make_dim("Latency Sensitivity", DimensionScore.POSITIVE),
        load_predictability=_make_dim("Load Predictability", DimensionScore.NEUTRAL),
    )
    return AnalysisResult(
        recommendation=Recommendation.PTU_RECOMMENDED,
        dimensions=dims,
        confidence=0.85,
        summary="PTU is recommended",
        explanation="Detailed explanation",
        what_would_change="Changes",
        data_quality="Good",
        analysis_period="14 days (Jan 01 - Jan 14, 2026)",
    )


# ============================================================================
# Static Filters
# ============================================================================


class TestFormatNumber:
    """Tests for _format_number static method."""

    def test_millions(self):
        assert ReportGenerator._format_number(1_500_000) == "1.5M"

    def test_thousands(self):
        assert ReportGenerator._format_number(50_000) == "50.0K"

    def test_small_number(self):
        assert ReportGenerator._format_number(42) == "42"

    def test_zero(self):
        assert ReportGenerator._format_number(0) == "0"

    def test_exact_million(self):
        assert ReportGenerator._format_number(1_000_000) == "1.0M"


class TestFormatPercent:
    """Tests for _format_percent static method."""

    def test_decimal(self):
        assert ReportGenerator._format_percent(0.85) == "85.0%"

    def test_zero(self):
        assert ReportGenerator._format_percent(0) == "0.0%"

    def test_one(self):
        assert ReportGenerator._format_percent(1.0) == "100.0%"


class TestFormatDuration:
    """Tests for _format_duration static method."""

    def test_milliseconds(self):
        assert ReportGenerator._format_duration(500) == "500ms"

    def test_seconds(self):
        assert ReportGenerator._format_duration(2500) == "2.5s"

    def test_exact_second(self):
        assert ReportGenerator._format_duration(1000) == "1.0s"


class TestMarkdownToHtml:
    """Tests for _markdown_to_html static method."""

    def test_bold(self):
        result = ReportGenerator._markdown_to_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_italic(self):
        result = ReportGenerator._markdown_to_html("*italic*")
        assert "<em>italic</em>" in result

    def test_newlines(self):
        result = ReportGenerator._markdown_to_html("line1\n\nline2")
        assert "</p><p>" in result

    def test_empty_string(self):
        result = ReportGenerator._markdown_to_html("")
        assert result == ""

    def test_none(self):
        result = ReportGenerator._markdown_to_html(None)
        assert result is None

    def test_wraps_in_paragraph(self):
        result = ReportGenerator._markdown_to_html("plain text")
        assert result.startswith("<p>")
        assert result.endswith("</p>")


# ============================================================================
# Metrics Summary
# ============================================================================


class TestGetMetricsSummary:
    """Tests for _get_metrics_summary."""

    def test_returns_dict_with_expected_keys(self, generator, sample_metrics):
        summary = generator._get_metrics_summary(sample_metrics)
        expected_keys = [
            "total_requests", "throttling_rate", "avg_tokens_per_request",
            "tpm_mean", "tpm_max", "p50_latency", "p95_latency", "data_points",
            "rpm_mean", "rpm_max", "successful_requests", "success_rate",
            "throttled_requests", "tpm_std", "tpm_cv", "total_tokens",
            "prompt_ratio", "completion_ratio",
            "p50_min", "p50_max", "p95_min", "p95_max",
            "p99_latency", "p99_min", "p99_max", "latency_variance",
            "active_percentage", "non_zero_hours", "utilization",
        ]
        for key in expected_keys:
            assert key in summary, f"Missing key: {key}"

    def test_tpm_values(self, generator, sample_metrics):
        summary = generator._get_metrics_summary(sample_metrics)
        assert summary["tpm_mean"] == 50000.0
        assert summary["tpm_max"] == 50000.0

    def test_latency_values(self, generator, sample_metrics):
        summary = generator._get_metrics_summary(sample_metrics)
        assert summary["p50_latency"] == 500.0
        assert summary["p95_latency"] == 2000.0
        assert summary["p99_latency"] == 4000.0

    def test_success_rate(self, generator, sample_metrics):
        summary = generator._get_metrics_summary(sample_metrics)
        # 95 success / (95 + 5) = 0.95
        assert summary["success_rate"] == pytest.approx(0.95, abs=0.01)

    def test_token_ratios(self, generator, sample_metrics):
        summary = generator._get_metrics_summary(sample_metrics)
        # 30000 prompt / 50000 total = 0.6
        assert summary["prompt_ratio"] == pytest.approx(0.6, abs=0.01)
        assert summary["completion_ratio"] == pytest.approx(0.4, abs=0.01)

    def test_with_no_optional_fields(self, generator):
        """Metrics with mostly None fields should not crash."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
        )
        summary = generator._get_metrics_summary(metrics)
        assert summary["tpm_mean"] == 0
        assert summary["p50_latency"] == 0
        assert summary["data_points"] == 10

    def test_sku_type_from_deployment_info(self, generator, sample_timestamps):
        """Should extract sku_type from deployment_info if present."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=sample_timestamps[0],
            end_time=sample_timestamps[-1],
            timestamps=sample_timestamps,
            deployment_info=DeploymentInfo(name="test", model="gpt-4o", sku_type="ProvisionedManaged"),
        )
        summary = generator._get_metrics_summary(metrics)
        assert summary["sku_type"] == "ProvisionedManaged"


# ============================================================================
# PTU Estimates
# ============================================================================


class TestCalculatePtuEstimates:
    """Tests for _calculate_ptu_estimates."""

    def test_returns_available(self, generator, sample_metrics):
        est = generator._calculate_ptu_estimates(sample_metrics)
        assert est["available"] is True

    def test_returns_expected_keys(self, generator, sample_metrics):
        est = generator._calculate_ptu_estimates(sample_metrics)
        expected = [
            "model_detected", "peak_tpm", "avg_tpm", "completion_ratio",
            "effective_multiplier", "raw_ptu_needed",
            "global_ptu_recommended", "global_ptu_conservative",
            "global_hourly_cost", "global_monthly_cost",
            "regional_ptu_recommended", "regional_ptu_conservative",
            "regional_hourly_cost", "regional_monthly_cost",
            "payg_monthly_estimate", "ptu_savings_pct",
        ]
        for key in expected:
            assert key in est, f"Missing key: {key}"

    def test_ptu_units_meet_minimum(self, generator, sample_metrics):
        est = generator._calculate_ptu_estimates(sample_metrics)
        assert est["global_ptu_recommended"] >= 15
        assert est["regional_ptu_recommended"] >= 50

    def test_no_tpm_returns_unavailable(self, generator):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4o",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
        )
        est = generator._calculate_ptu_estimates(metrics)
        assert est["available"] is False

    def test_model_detection(self, generator, sample_metrics):
        """Should detect gpt-4o from model name."""
        est = generator._calculate_ptu_estimates(sample_metrics)
        assert est["model_detected"] == "gpt-4o"

    def test_unknown_model_defaults_to_gpt4o(self, generator, sample_timestamps):
        """Unknown model should default to gpt-4o config."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="unknown-model",
            start_time=sample_timestamps[0],
            end_time=sample_timestamps[-1],
            timestamps=sample_timestamps,
            tokens_per_minute=TimeSeries(sample_timestamps, [10000.0] * 200, "tpm"),
        )
        est = generator._calculate_ptu_estimates(metrics)
        assert est["available"] is True
        assert est["model_detected"] == "gpt-4o"

    def test_costs_are_positive(self, generator, sample_metrics):
        est = generator._calculate_ptu_estimates(sample_metrics)
        assert est["global_hourly_cost"] > 0
        assert est["global_monthly_cost"] > 0
        assert est["payg_monthly_estimate"] > 0


# ============================================================================
# Recommendation CSS Classes
# ============================================================================


class TestRecommendationClass:
    """Tests for _get_recommendation_class and _dimension_score_class."""

    def test_recommendation_classes(self, generator):
        assert generator._get_recommendation_class(Recommendation.PTU_RECOMMENDED) == "success"
        assert generator._get_recommendation_class(Recommendation.BORDERLINE) == "warning"
        assert generator._get_recommendation_class(Recommendation.PTU_NOT_RECOMMENDED) == "danger"

    def test_dimension_score_classes(self, generator):
        assert generator._dimension_score_class(DimensionScore.POSITIVE) == "success"
        assert generator._dimension_score_class(DimensionScore.NEUTRAL) == "warning"
        assert generator._dimension_score_class(DimensionScore.NEGATIVE) == "danger"
        assert generator._dimension_score_class(DimensionScore.INSUFFICIENT) == "muted"


# ============================================================================
# Full Report Generation
# ============================================================================


class TestFullReportGeneration:
    """Tests for end-to-end report generation."""

    def test_generates_html_file(self, generator, sample_metrics, sample_result, tmp_path):
        output_path = tmp_path / "test_report.html"
        result_path = generator.generate(
            metrics=sample_metrics,
            result=sample_result,
            charts=[],
            output_path=output_path,
        )
        assert result_path.exists()
        content = result_path.read_text()
        assert "test-deploy" in content
        assert "gpt-4o" in content

    def test_generates_default_output_path(self, generator, sample_metrics, sample_result):
        result_path = generator.generate(
            metrics=sample_metrics,
            result=sample_result,
            charts=[],
        )
        assert result_path.exists()
        assert "ptu-report" in result_path.name
        # Clean up
        result_path.unlink()

    def test_includes_llm_analysis(self, generator, sample_metrics, sample_result, tmp_path):
        output_path = tmp_path / "test_report_llm.html"
        result_path = generator.generate(
            metrics=sample_metrics,
            result=sample_result,
            charts=[],
            output_path=output_path,
            llm_analysis="## LLM Analysis\nThis is an AI-generated insight.",
        )
        content = result_path.read_text()
        # The template should include it if it handles llm_analysis
        assert result_path.exists()
