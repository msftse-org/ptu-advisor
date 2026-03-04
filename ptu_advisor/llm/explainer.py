"""PTU Explainer - LLM-powered explanation generation.

This module provides the main interface for generating AI-powered
explanations of PTU recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

from ptu_advisor.llm.provider import LLMProvider, LLMConfig, get_provider, LLMResponse
from ptu_advisor.llm.prompts import PromptTemplates, MetricsContext
from ptu_advisor.metrics.models import DeploymentMetrics, AnalysisResult, DimensionScores

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    """Result of LLM-generated explanation."""
    
    content: str
    source: str  # "llm" or "fallback"
    model: Optional[str] = None
    tokens_used: int = 0
    cached: bool = False
    error: Optional[str] = None


class PTUExplainer:
    """
    LLM-powered explanation generator for PTU recommendations.
    
    This class orchestrates the generation of AI-powered explanations
    by coordinating between the LLM provider and prompt templates.
    It includes fallback logic for when LLM is unavailable.
    """
    
    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        config: Optional[LLMConfig] = None,
        enable_fallback: bool = True
    ):
        """
        Initialize the PTU Explainer.
        
        Args:
            provider: Optional LLM provider instance. If not provided,
                     one will be created from config or environment.
            config: Optional LLM configuration.
            enable_fallback: Whether to use template-based fallback
                           when LLM is unavailable.
        """
        self.enable_fallback = enable_fallback
        self._provider: Optional[LLMProvider] = provider
        self._config = config or LLMConfig.from_env()
    
    @property
    def provider(self) -> LLMProvider:
        """Lazy initialization of LLM provider."""
        if self._provider is None:
            self._provider = get_provider(self._config)
        return self._provider
    
    def build_context(
        self,
        metrics: DeploymentMetrics,
        analysis: AnalysisResult
    ) -> MetricsContext:
        """
        Build structured metrics context from deployment data.
        
        Args:
            metrics: Collected deployment metrics.
            analysis: Analysis result with recommendation.
            
        Returns:
            MetricsContext ready for prompt templates.
        """
        tpm = metrics.tokens_per_minute
        
        return MetricsContext(
            # Deployment info
            deployment_name=metrics.deployment_name,
            model_name=metrics.model_name,
            analysis_period=analysis.analysis_period,
            
            # Token metrics
            avg_tpm=tpm.mean if tpm else 0,
            peak_tpm=tpm.p95 if tpm else 0,
            tpm_std=tpm.std if tpm else 0,
            tpm_cv=tpm.cv if tpm else 0,
            
            # Utilization patterns
            peak_to_avg_ratio=tpm.peak_to_average_ratio if tpm else 0,
            sustained_utilization=tpm.sustained_utilization_rate(0.3) if tpm else 0,
            active_hours_pct=tpm.active_hours_percentage if tpm else 0,
            business_hours_concentration=tpm.business_hours_concentration if tpm else 0,
            weekend_weekday_ratio=tpm.weekend_vs_weekday_ratio if tpm else 0,
            
            # Capacity pressure
            throttling_rate=metrics.throttling_rate * 100,
            total_requests=metrics.total_requests,
            throttled_requests=int(metrics.throttled_requests.total) if metrics.throttled_requests else 0,
            
            # Latency
            latency_p50=metrics.time_to_first_byte_p50.mean if metrics.time_to_first_byte_p50 else 0,
            latency_p95=metrics.time_to_first_byte_p95.mean if metrics.time_to_first_byte_p95 else 0,
            latency_p99=metrics.time_to_first_byte_p99.mean if metrics.time_to_first_byte_p99 else 0,
            
            # Recommendation
            recommendation=str(analysis.recommendation),
            confidence=analysis.confidence * 100,
            
            # Dimension scores
            workload_shape_score=str(analysis.dimensions.workload_shape.score),
            capacity_pressure_score=str(analysis.dimensions.capacity_pressure.score),
            latency_sensitivity_score=str(analysis.dimensions.latency_sensitivity.score),
            load_predictability_score=str(analysis.dimensions.load_predictability.score),
        )
    
    def generate_main_analysis(
        self,
        metrics: DeploymentMetrics,
        analysis: AnalysisResult
    ) -> ExplanationResult:
        """
        Generate the main AI-powered analysis explanation.
        
        Args:
            metrics: Collected deployment metrics.
            analysis: Analysis result with recommendation.
            
        Returns:
            ExplanationResult with generated content.
        """
        context = self.build_context(metrics, analysis)
        system_prompt, user_prompt = PromptTemplates.build_main_analysis_prompt(context)
        
        try:
            response = self.provider.generate_sync(system_prompt, user_prompt)
            
            return ExplanationResult(
                content=response.content,
                source="llm",
                model=response.model,
                tokens_used=response.usage.get("total_tokens", 0),
                cached=response.cached,
            )
            
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            
            if self.enable_fallback:
                return self._fallback_main_analysis(analysis)
            
            return ExplanationResult(
                content="Unable to generate AI analysis.",
                source="error",
                error=str(e),
            )
    
    def generate_dimension_explanation(
        self,
        metrics: DeploymentMetrics,
        analysis: AnalysisResult,
        dimension_name: str
    ) -> ExplanationResult:
        """
        Generate explanation for a specific dimension.
        
        Args:
            metrics: Collected deployment metrics.
            analysis: Analysis result.
            dimension_name: Name of dimension to explain.
            
        Returns:
            ExplanationResult with generated content.
        """
        context = self.build_context(metrics, analysis)
        
        # Get dimension score
        dim_map = {
            "Workload Shape": analysis.dimensions.workload_shape,
            "Capacity Pressure": analysis.dimensions.capacity_pressure,
            "Latency Sensitivity": analysis.dimensions.latency_sensitivity,
            "Load Predictability": analysis.dimensions.load_predictability,
        }
        
        dimension = dim_map.get(dimension_name)
        if dimension is None:
            return ExplanationResult(
                content=f"Unknown dimension: {dimension_name}",
                source="error",
                error="Invalid dimension name",
            )
        
        system_prompt, user_prompt = PromptTemplates.build_dimension_prompt(
            context, dimension_name, str(dimension.score)
        )
        
        try:
            response = self.provider.generate_sync(system_prompt, user_prompt)
            
            return ExplanationResult(
                content=response.content,
                source="llm",
                model=response.model,
                tokens_used=response.usage.get("total_tokens", 0),
                cached=response.cached,
            )
            
        except Exception as e:
            logger.warning(f"LLM generation failed for dimension {dimension_name}: {e}")
            
            if self.enable_fallback:
                return ExplanationResult(
                    content=dimension.explanation,
                    source="fallback",
                )
            
            return ExplanationResult(
                content="Unable to generate explanation.",
                source="error",
                error=str(e),
            )
    
    def generate_what_if_analysis(
        self,
        metrics: DeploymentMetrics,
        analysis: AnalysisResult,
        question: str
    ) -> ExplanationResult:
        """
        Generate what-if scenario analysis.
        
        Args:
            metrics: Collected deployment metrics.
            analysis: Analysis result.
            question: User's what-if question.
            
        Returns:
            ExplanationResult with generated content.
        """
        context = self.build_context(metrics, analysis)
        system_prompt, user_prompt = PromptTemplates.build_what_if_prompt(
            context, question
        )
        
        try:
            response = self.provider.generate_sync(system_prompt, user_prompt)
            
            return ExplanationResult(
                content=response.content,
                source="llm",
                model=response.model,
                tokens_used=response.usage.get("total_tokens", 0),
                cached=response.cached,
            )
            
        except Exception as e:
            logger.warning(f"LLM what-if generation failed: {e}")
            
            return ExplanationResult(
                content="Unable to generate what-if analysis. Please try again.",
                source="error",
                error=str(e),
            )
    
    def generate_executive_summary(
        self,
        metrics: DeploymentMetrics,
        analysis: AnalysisResult
    ) -> ExplanationResult:
        """
        Generate executive summary for stakeholders.
        
        Args:
            metrics: Collected deployment metrics.
            analysis: Analysis result.
            
        Returns:
            ExplanationResult with generated content.
        """
        context = self.build_context(metrics, analysis)
        system_prompt, user_prompt = PromptTemplates.build_executive_summary_prompt(context)
        
        try:
            response = self.provider.generate_sync(system_prompt, user_prompt)
            
            return ExplanationResult(
                content=response.content,
                source="llm",
                model=response.model,
                tokens_used=response.usage.get("total_tokens", 0),
                cached=response.cached,
            )
            
        except Exception as e:
            logger.warning(f"LLM executive summary generation failed: {e}")
            
            if self.enable_fallback:
                return self._fallback_executive_summary(analysis)
            
            return ExplanationResult(
                content="Unable to generate executive summary.",
                source="error",
                error=str(e),
            )
    
    def _fallback_main_analysis(self, analysis: AnalysisResult) -> ExplanationResult:
        """Generate fallback main analysis using templates."""
        return ExplanationResult(
            content=analysis.explanation,
            source="fallback",
        )
    
    def _fallback_executive_summary(self, analysis: AnalysisResult) -> ExplanationResult:
        """Generate fallback executive summary."""
        rec = analysis.recommendation
        emoji = "✅" if "RECOMMENDED" in str(rec) and "NOT" not in str(rec) else "💰" if "NOT" in str(rec) else "⚖️"
        
        content = f"""
**{emoji} Recommendation: {str(rec).replace('_', ' ').title()}**

- {analysis.summary}
- Confidence: {analysis.confidence * 100:.0f}%
- Key factors: {', '.join(d.name for d in analysis.dimensions.all_dimensions if d.is_positive) or 'None strongly favor PTU'}
"""
        
        return ExplanationResult(
            content=content,
            source="fallback",
        )


# Convenience function for quick usage
def explain(
    metrics: DeploymentMetrics,
    analysis: AnalysisResult,
    provider: str = "mock"
) -> str:
    """
    Quick function to generate AI explanation.
    
    Args:
        metrics: Deployment metrics.
        analysis: Analysis result.
        provider: LLM provider to use ("azure", "openai", "mock").
        
    Returns:
        Generated explanation string.
    """
    config = LLMConfig(provider=provider)
    explainer = PTUExplainer(config=config)
    result = explainer.generate_main_analysis(metrics, analysis)
    return result.content
