"""Tests for LLM provider, prompts, and explainer."""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from ptu_advisor.llm.provider import (
    LLMConfig,
    LLMResponse,
    MockProvider,
    get_provider,
)
from ptu_advisor.llm.prompts import MetricsContext, PromptTemplates
from ptu_advisor.llm.explainer import PTUExplainer, ExplanationResult
from ptu_advisor.config import AnalysisConfig
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
from ptu_advisor.demo import DemoScenario, generate_demo_metrics


# ============================================================================
# LLMConfig
# ============================================================================


class TestLLMConfig:
    """Tests for LLM configuration."""

    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.provider == "azure"
        assert cfg.model == "gpt-4o"
        assert cfg.temperature == 0.3
        assert cfg.max_tokens == 1500

    def test_from_env_defaults(self, monkeypatch):
        """from_env without env vars uses defaults."""
        # Clear any existing env vars
        for key in ["PTU_ADVISOR_LLM_PROVIDER", "PTU_ADVISOR_LLM_MODEL",
                     "AZURE_OPENAI_ENDPOINT", "OPENAI_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        cfg = LLMConfig.from_env()
        assert cfg.provider == "azure"
        assert cfg.model == "gpt-4o"

    def test_from_env_with_vars(self, monkeypatch):
        monkeypatch.setenv("PTU_ADVISOR_LLM_PROVIDER", "openai")
        monkeypatch.setenv("PTU_ADVISOR_LLM_MODEL", "gpt-5")
        monkeypatch.setenv("PTU_ADVISOR_LLM_TEMPERATURE", "0.7")
        cfg = LLMConfig.from_env()
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-5"
        assert cfg.temperature == 0.7


# ============================================================================
# MockProvider
# ============================================================================


class TestMockProvider:
    """Tests for MockProvider."""

    @pytest.fixture
    def mock_provider(self):
        cfg = LLMConfig(provider="mock")
        return MockProvider(cfg)

    def test_generate_sync_returns_response(self, mock_provider):
        response = mock_provider.generate_sync(
            system_prompt="You are an expert.",
            user_prompt="Analyze PTU recommendation for this deployment.",
        )
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
        assert response.model == "mock-gpt-4o"

    def test_generate_sync_ptu_recommended(self, mock_provider):
        response = mock_provider.generate_sync(
            system_prompt="You are an expert.",
            user_prompt="Decision: PTU_RECOMMENDED. Analyze this.",
        )
        assert "PTU" in response.content or "provision" in response.content.lower()

    def test_generate_sync_not_recommended(self, mock_provider):
        response = mock_provider.generate_sync(
            system_prompt="You are an expert.",
            user_prompt="Decision: PTU_NOT_RECOMMENDED. Analyze this.",
        )
        assert len(response.content) > 0

    def test_generate_sync_borderline(self, mock_provider):
        response = mock_provider.generate_sync(
            system_prompt="You are an expert.",
            user_prompt="Decision: BORDERLINE. Analyze this.",
        )
        assert len(response.content) > 0

    def test_generate_async(self, mock_provider):
        response = asyncio.run(mock_provider.generate(
            system_prompt="System",
            user_prompt="User prompt",
        ))
        assert isinstance(response, LLMResponse)


# ============================================================================
# get_provider factory
# ============================================================================


class TestGetProvider:
    """Tests for the provider factory function."""

    def test_mock_provider(self):
        cfg = LLMConfig(provider="mock")
        provider = get_provider(cfg)
        assert isinstance(provider, MockProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider="invalid_xyz")


# ============================================================================
# MetricsContext
# ============================================================================


class TestMetricsContext:
    """Tests for MetricsContext prompt formatting."""

    @pytest.fixture
    def context(self):
        return MetricsContext(
            deployment_name="test-deploy",
            model_name="gpt-4o",
            analysis_period="14 days",
            avg_tpm=50000,
            peak_tpm=80000,
            tpm_std=15000,
            tpm_cv=0.3,
            peak_to_avg_ratio=1.6,
            sustained_utilization=75.0,
            active_hours_pct=80.0,
            business_hours_concentration=65.0,
            weekend_weekday_ratio=0.3,
            throttling_rate=5.0,
            total_requests=500000,
            throttled_requests=25000,
            latency_p50=500,
            latency_p95=2000,
            latency_p99=5000,
            recommendation="PTU_RECOMMENDED",
            confidence=0.85,
            workload_shape_score="positive",
            capacity_pressure_score="positive",
            latency_sensitivity_score="neutral",
            load_predictability_score="positive",
        )

    def test_to_prompt_context_returns_string(self, context):
        text = context.to_prompt_context()
        assert isinstance(text, str)
        assert "test-deploy" in text
        assert "gpt-4o" in text

    def test_prompt_context_contains_metrics(self, context):
        text = context.to_prompt_context()
        assert "50,000" in text or "50000" in text
        assert "PTU_RECOMMENDED" in text
        assert "positive" in text.lower()


# ============================================================================
# PromptTemplates
# ============================================================================


class TestPromptTemplates:
    """Tests for prompt template builders."""

    @pytest.fixture
    def context(self):
        return MetricsContext(
            deployment_name="test", model_name="gpt-4o", analysis_period="14d",
            avg_tpm=50000, peak_tpm=80000, tpm_std=15000, tpm_cv=0.3,
            peak_to_avg_ratio=1.6, sustained_utilization=75, active_hours_pct=80,
            business_hours_concentration=65, weekend_weekday_ratio=0.3,
            throttling_rate=5, total_requests=500000, throttled_requests=25000,
            latency_p50=500, latency_p95=2000, latency_p99=5000,
            recommendation="PTU_RECOMMENDED", confidence=0.85,
            workload_shape_score="positive", capacity_pressure_score="positive",
            latency_sensitivity_score="neutral", load_predictability_score="positive",
        )

    def test_build_main_analysis_prompt(self, context):
        sys_prompt, user_prompt = PromptTemplates.build_main_analysis_prompt(context)
        assert isinstance(sys_prompt, str)
        assert isinstance(user_prompt, str)
        assert len(sys_prompt) > 0
        assert len(user_prompt) > 0

    def test_build_dimension_prompt(self, context):
        sys_prompt, user_prompt = PromptTemplates.build_dimension_prompt(
            context, "Workload Shape", "positive"
        )
        assert "Workload Shape" in user_prompt

    def test_build_executive_summary_prompt(self, context):
        sys_prompt, user_prompt = PromptTemplates.build_executive_summary_prompt(context)
        assert len(sys_prompt) > 0
        assert len(user_prompt) > 0

    def test_build_what_if_prompt(self, context):
        sys_prompt, user_prompt = PromptTemplates.build_what_if_prompt(
            context, "What if throttling doubles?"
        )
        assert "What if throttling doubles?" in user_prompt

    def test_system_prompt_contains_ptu_context(self):
        assert "PTU" in PromptTemplates.SYSTEM_PROMPT
        assert "PAYG" in PromptTemplates.SYSTEM_PROMPT


# ============================================================================
# PTUExplainer integration with MockProvider
# ============================================================================


class TestPTUExplainer:
    """Integration tests for PTUExplainer with mock provider."""

    @pytest.fixture
    def config(self):
        return AnalysisConfig(
            resource_group="rg", workspace="ws", deployment="dep",
            enable_llm=True, llm_provider="mock",
        )

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_build_context(self, config, scenario):
        """build_context should produce MetricsContext for all scenarios."""
        metrics, _ = generate_demo_metrics(scenario)
        engine = DecisionEngine(config)
        analysis = engine.analyze(metrics)
        
        explainer = PTUExplainer(provider=None, config=LLMConfig(provider="mock"))
        ctx = explainer.build_context(metrics, analysis)
        
        assert isinstance(ctx, MetricsContext)
        assert ctx.avg_tpm > 0
        assert ctx.deployment_name == metrics.deployment_name

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_generate_main_analysis(self, config, scenario):
        """Mock explainer should generate analysis for all scenarios."""
        metrics, _ = generate_demo_metrics(scenario)
        engine = DecisionEngine(config)
        analysis = engine.analyze(metrics)
        
        llm_config = LLMConfig(provider="mock")
        provider = get_provider(llm_config)
        explainer = PTUExplainer(provider=provider, config=llm_config)
        
        result = explainer.generate_main_analysis(metrics, analysis)
        assert isinstance(result, ExplanationResult)
        assert len(result.content) > 0

    @pytest.mark.parametrize("scenario", list(DemoScenario))
    def test_generate_executive_summary(self, config, scenario):
        metrics, _ = generate_demo_metrics(scenario)
        engine = DecisionEngine(config)
        analysis = engine.analyze(metrics)
        
        llm_config = LLMConfig(provider="mock")
        provider = get_provider(llm_config)
        explainer = PTUExplainer(provider=provider, config=llm_config)
        
        result = explainer.generate_executive_summary(metrics, analysis)
        assert isinstance(result, ExplanationResult)
        assert len(result.content) > 0
