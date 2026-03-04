"""Tests for demo scenario generation."""

import pytest
from datetime import datetime, timezone

from ptu_advisor.demo import (
    DemoScenario,
    ScenarioConfig,
    SCENARIOS,
    generate_demo_metrics,
    get_demo_deployment_info,
    list_demo_scenarios,
)
from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries, DeploymentInfo


# ============================================================================
# SCENARIOS dictionary
# ============================================================================


class TestScenarios:
    """Tests for the SCENARIOS configuration dictionary."""

    def test_all_three_scenarios_defined(self):
        assert DemoScenario.PTU_RECOMMENDED in SCENARIOS
        assert DemoScenario.PTU_NOT_RECOMMENDED in SCENARIOS
        assert DemoScenario.BORDERLINE in SCENARIOS

    def test_scenario_configs_have_required_fields(self):
        for scenario_key, config in SCENARIOS.items():
            assert isinstance(config, ScenarioConfig), f"{scenario_key} not ScenarioConfig"
            assert config.name, f"{scenario_key} missing name"
            assert config.description, f"{scenario_key} missing description"
            assert config.deployment_name, f"{scenario_key} missing deployment_name"
            assert config.model_name, f"{scenario_key} missing model_name"
            assert config.tpm_mean > 0, f"{scenario_key} tpm_mean <= 0"

    def test_ptu_recommended_has_high_throttling(self):
        cfg = SCENARIOS[DemoScenario.PTU_RECOMMENDED]
        assert cfg.throttling_rate >= 0.05  # High throttling

    def test_ptu_not_recommended_has_low_throttling(self):
        cfg = SCENARIOS[DemoScenario.PTU_NOT_RECOMMENDED]
        assert cfg.throttling_rate < 0.01  # Very low

    def test_borderline_moderate(self):
        cfg = SCENARIOS[DemoScenario.BORDERLINE]
        # Moderate characteristics
        assert 0.01 <= cfg.throttling_rate <= 0.10


# ============================================================================
# generate_demo_metrics
# ============================================================================


class TestGenerateDemoMetrics:
    """Tests for the generate_demo_metrics function."""

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_generates_valid_metrics(self, scenario):
        """All scenarios should produce valid DeploymentMetrics."""
        metrics, config = generate_demo_metrics(scenario)
        
        assert isinstance(metrics, DeploymentMetrics)
        assert isinstance(config, ScenarioConfig)
        assert metrics.deployment_name == config.deployment_name
        assert metrics.model_name == config.model_name

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_timestamps_populated(self, scenario):
        metrics, _ = generate_demo_metrics(scenario)
        assert len(metrics.timestamps) > 0
        assert metrics.start_time < metrics.end_time

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_core_timeseries_populated(self, scenario):
        """Core time series should be present and have data."""
        metrics, _ = generate_demo_metrics(scenario)
        
        assert metrics.tokens_per_minute is not None
        assert len(metrics.tokens_per_minute) > 0
        
        assert metrics.requests_per_minute is not None
        assert len(metrics.requests_per_minute) > 0

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_latency_timeseries_populated(self, scenario):
        """Latency percentiles should be present."""
        metrics, _ = generate_demo_metrics(scenario)
        assert metrics.time_to_first_byte_p50 is not None
        assert metrics.time_to_first_byte_p95 is not None
        assert metrics.time_to_first_byte_p99 is not None

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_latency_ordering(self, scenario):
        """P50 <= P95 <= P99 on average."""
        metrics, _ = generate_demo_metrics(scenario)
        p50_mean = metrics.time_to_first_byte_p50.mean
        p95_mean = metrics.time_to_first_byte_p95.mean
        p99_mean = metrics.time_to_first_byte_p99.mean
        assert p50_mean <= p95_mean <= p99_mean

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_token_timeseries_populated(self, scenario):
        """Prompt and completion tokens should be present."""
        metrics, _ = generate_demo_metrics(scenario)
        assert metrics.prompt_tokens is not None
        assert metrics.completion_tokens is not None

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_throttled_requests_populated(self, scenario):
        """Throttled and successful requests should be present."""
        metrics, _ = generate_demo_metrics(scenario)
        assert metrics.throttled_requests is not None
        assert metrics.successful_requests is not None

    def test_custom_lookback_days(self):
        """Custom lookback_days changes the data size."""
        metrics_7, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED, lookback_days=7)
        metrics_14, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED, lookback_days=14)
        # 14 days should produce approximately 2x data points
        assert len(metrics_14.timestamps) > len(metrics_7.timestamps)

    def test_ptu_recommended_high_throttling_rate(self):
        """PTU_RECOMMENDED scenario should generate notable throttling."""
        metrics, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED)
        assert metrics.throttling_rate > 0.01  # Should have meaningful throttling

    def test_ptu_not_recommended_low_utilization(self):
        """PTU_NOT_RECOMMENDED should have lower TPM."""
        metrics, _ = generate_demo_metrics(DemoScenario.PTU_NOT_RECOMMENDED)
        # Mean TPM should be much lower than PTU_RECOMMENDED
        rec_metrics, _ = generate_demo_metrics(DemoScenario.PTU_RECOMMENDED)
        assert metrics.tokens_per_minute.mean < rec_metrics.tokens_per_minute.mean


# ============================================================================
# get_demo_deployment_info
# ============================================================================


class TestGetDemoDeploymentInfo:
    """Tests for get_demo_deployment_info."""

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_returns_deployment_info(self, scenario):
        info = get_demo_deployment_info(scenario)
        assert isinstance(info, DeploymentInfo)
        assert info.name
        assert info.model
        assert info.sku_type


# ============================================================================
# list_demo_scenarios
# ============================================================================


class TestListDemoScenarios:
    """Tests for list_demo_scenarios."""

    def test_does_not_raise(self):
        """Should run without error (prints to console)."""
        list_demo_scenarios()
