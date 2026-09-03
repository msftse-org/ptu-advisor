"""Tests for configuration classes and model config lookup."""

import pytest
from ptu_advisor.config import (
    AnalysisConfig,
    BusinessHoursConfig,
    ModelCapacityConfig,
    ThresholdConfig,
    MODEL_CAPACITY_CONFIGS,
    get_model_config,
)


# ============================================================================
# ThresholdConfig
# ============================================================================


class TestThresholdConfig:
    """Tests for ThresholdConfig defaults and consistency."""

    def test_defaults(self):
        tc = ThresholdConfig()
        assert tc.tpm_cv_stable_threshold == 0.3
        assert tc.tpm_cv_spiky_threshold == 0.7
        assert tc.throttling_rate_low == 0.01
        assert tc.throttling_rate_high == 0.05
        assert tc.tpm_utilization_ceiling == 0.85
        assert tc.p95_latency_good == 2000.0
        assert tc.p95_latency_poor == 5000.0
        assert tc.latency_variance_stable == 2.0
        assert tc.latency_variance_unstable == 4.0
        assert tc.sustained_traffic_threshold == 0.6
        assert tc.day_similarity_threshold == 0.7
        assert tc.min_positive_for_ptu == 3
        assert tc.min_positive_for_borderline == 2
        assert tc.min_data_points == 100
        assert tc.min_days_for_confidence == 3

    def test_threshold_ordering(self):
        """Thresholds should be logically ordered."""
        tc = ThresholdConfig()
        assert tc.tpm_cv_stable_threshold < tc.tpm_cv_spiky_threshold
        assert tc.throttling_rate_low < tc.throttling_rate_high
        assert tc.p95_latency_good < tc.p95_latency_poor
        assert tc.latency_variance_stable < tc.latency_variance_unstable
        assert tc.min_positive_for_borderline < tc.min_positive_for_ptu

    def test_custom_thresholds(self):
        tc = ThresholdConfig(tpm_cv_stable_threshold=0.2, min_data_points=50)
        assert tc.tpm_cv_stable_threshold == 0.2
        assert tc.min_data_points == 50


# ============================================================================
# BusinessHoursConfig
# ============================================================================


class TestBusinessHoursConfig:
    """Tests for BusinessHoursConfig."""

    def test_defaults(self):
        bhc = BusinessHoursConfig()
        assert bhc.start_hour == 9
        assert bhc.end_hour == 18
        assert bhc.timezone == "UTC"
        assert bhc.weekdays_only is True


# ============================================================================
# AnalysisConfig
# ============================================================================


class TestAnalysisConfig:
    """Tests for AnalysisConfig validation."""

    def test_valid_config(self):
        config = AnalysisConfig(
            resource_group="rg",
            workspace="ws",
            deployment="dep",
        )
        assert config.lookback_days == 14
        assert config.aggregation_interval_minutes == 5
        assert config.verbose is False
        assert config.enable_llm is False

    def test_lookback_days_too_low(self):
        with pytest.raises(ValueError, match="at least 1"):
            AnalysisConfig(
                resource_group="rg",
                workspace="ws",
                deployment="dep",
                lookback_days=0,
            )

    def test_lookback_days_too_high(self):
        with pytest.raises(ValueError, match="cannot exceed 90"):
            AnalysisConfig(
                resource_group="rg",
                workspace="ws",
                deployment="dep",
                lookback_days=91,
            )

    def test_lookback_days_boundary_valid(self):
        """Boundary values 1 and 90 should be valid."""
        c1 = AnalysisConfig(resource_group="rg", workspace="ws", deployment="dep", lookback_days=1)
        assert c1.lookback_days == 1
        c90 = AnalysisConfig(resource_group="rg", workspace="ws", deployment="dep", lookback_days=90)
        assert c90.lookback_days == 90

    def test_invalid_aggregation_interval(self):
        with pytest.raises(ValueError, match="must be 1, 5, 15, 30, or 60"):
            AnalysisConfig(
                resource_group="rg",
                workspace="ws",
                deployment="dep",
                aggregation_interval_minutes=10,
            )

    def test_valid_aggregation_intervals(self):
        for interval in [1, 5, 15, 30]:
            config = AnalysisConfig(
                resource_group="rg",
                workspace="ws",
                deployment="dep",
                aggregation_interval_minutes=interval,
            )
            assert config.aggregation_interval_minutes == interval

    def test_nested_configs_defaults(self):
        config = AnalysisConfig(resource_group="rg", workspace="ws", deployment="dep")
        assert isinstance(config.thresholds, ThresholdConfig)
        assert isinstance(config.business_hours, BusinessHoursConfig)

    def test_custom_thresholds(self):
        custom_th = ThresholdConfig(min_data_points=50)
        config = AnalysisConfig(
            resource_group="rg",
            workspace="ws",
            deployment="dep",
            thresholds=custom_th,
        )
        assert config.thresholds.min_data_points == 50


# ============================================================================
# ModelCapacityConfig & get_model_config
# ============================================================================


class TestModelCapacityConfigs:
    """Tests for MODEL_CAPACITY_CONFIGS and get_model_config."""

    def test_all_known_models_present(self):
        expected = ["gpt-5", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
                     "gpt-4o", "gpt-4o-mini", "o1", "o3-mini", "o4-mini"]
        for model in expected:
            assert model in MODEL_CAPACITY_CONFIGS, f"Missing config for {model}"

    def test_model_configs_have_positive_values(self):
        for name, cfg in MODEL_CAPACITY_CONFIGS.items():
            assert cfg.payg_tpm_quota > 0, f"{name} payg_tpm_quota"
            assert cfg.input_tpm_per_ptu > 0, f"{name} input_tpm_per_ptu"
            assert cfg.output_ratio > 0, f"{name} output_ratio"
            assert cfg.global_min_ptu > 0, f"{name} global_min_ptu"
            assert cfg.regional_min_ptu > 0, f"{name} regional_min_ptu"

    def test_get_model_config_exact_match(self):
        cfg = get_model_config("gpt-4o")
        assert cfg is not None
        assert cfg.payg_tpm_quota == 450_000

    def test_get_model_config_fuzzy_match(self):
        """Model name with version/suffix should still match."""
        cfg = get_model_config("gpt-4o (2024-11-20)")
        assert cfg is not None
        assert cfg == MODEL_CAPACITY_CONFIGS["gpt-4o"]

    def test_get_model_config_case_insensitive(self):
        cfg = get_model_config("GPT-4O")
        assert cfg is not None

    def test_get_model_config_longest_match_first(self):
        """'gpt-4o-mini' should match 'gpt-4o-mini' not 'gpt-4o'."""
        cfg = get_model_config("gpt-4o-mini")
        assert cfg is not None
        assert cfg == MODEL_CAPACITY_CONFIGS["gpt-4o-mini"]

    def test_get_model_config_longest_match_nano(self):
        """'gpt-4.1-nano' should match 'gpt-4.1-nano' not 'gpt-4.1'."""
        cfg = get_model_config("gpt-4.1-nano")
        assert cfg is not None
        assert cfg == MODEL_CAPACITY_CONFIGS["gpt-4.1-nano"]

    def test_get_model_config_unknown_model(self):
        cfg = get_model_config("unknown-model-xyz")
        assert cfg is None

    def test_get_model_config_empty_string(self):
        cfg = get_model_config("")
        assert cfg is None
