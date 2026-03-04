"""Explanation generator for PTU recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionScore,
    Recommendation,
)


@dataclass
class ExplanationSection:
    """A section of the explanation."""
    
    title: str
    content: str
    importance: str = "normal"  # "high", "normal", "low"


class Explainer:
    """
    Generates human-readable explanations for PTU recommendations.
    
    Ensures every recommendation is fully explainable with:
    - Which metrics mattered
    - Which metrics didn't
    - What would change the decision
    """
    
    def generate_full_explanation(
        self,
        result: AnalysisResult,
        metrics: DeploymentMetrics,
    ) -> list[ExplanationSection]:
        """
        Generate a complete explanation for the recommendation.
        
        Args:
            result: The analysis result.
            metrics: The raw metrics data.
            
        Returns:
            List of explanation sections for the report.
        """
        sections = []
        
        # Executive summary
        sections.append(self._executive_summary(result))
        
        # Key factors
        sections.append(self._key_factors(result))
        
        # Each dimension in detail
        for dim in result.dimensions.all_dimensions:
            sections.append(self._dimension_detail(dim))
        
        # Data quality
        sections.append(self._data_quality_section(result, metrics))
        
        # What would change
        sections.append(self._what_would_change_section(result))
        
        # Next steps
        sections.append(self._next_steps(result))
        
        return sections
    
    def _executive_summary(self, result: AnalysisResult) -> ExplanationSection:
        """Generate executive summary section."""
        emoji = result.recommendation_emoji
        rec_text = result.recommendation.value.replace("_", " ").upper()
        
        return ExplanationSection(
            title="Executive Summary",
            content=(
                f"{emoji} **{rec_text}**\n\n"
                f"{result.summary}\n\n"
                f"Confidence: **{result.confidence:.0%}**\n"
                f"Analysis Period: {result.analysis_period}"
            ),
            importance="high",
        )
    
    def _key_factors(self, result: AnalysisResult) -> ExplanationSection:
        """Generate key factors section."""
        positive = []
        neutral = []
        negative = []
        
        for dim in result.dimensions.all_dimensions:
            if dim.score == DimensionScore.POSITIVE:
                positive.append(f"+ {dim.name}: {dim.summary}")
            elif dim.score == DimensionScore.NEGATIVE:
                negative.append(f"- {dim.name}: {dim.summary}")
            else:
                neutral.append(f"~ {dim.name}: {dim.summary}")
        
        content_parts = []
        
        if positive:
            content_parts.append("**Factors Favoring PTU:**\n" + "\n".join(positive))
        if negative:
            content_parts.append("**Factors Against PTU:**\n" + "\n".join(negative))
        if neutral:
            content_parts.append("**Neutral Factors:**\n" + "\n".join(neutral))
        
        return ExplanationSection(
            title="Key Factors",
            content="\n\n".join(content_parts),
            importance="high",
        )
    
    def _dimension_detail(self, dim) -> ExplanationSection:
        """Generate detailed section for a dimension."""
        # Format key metrics
        metrics_text = ""
        if dim.key_metrics:
            metrics_lines = []
            for key, value in dim.key_metrics.items():
                # Format the key nicely
                nice_key = key.replace("_", " ").title()
                
                # Format the value based on the metric type
                if isinstance(value, float):
                    if "utilization" in key or "pct" in key or "rate" in key:
                        formatted = f"{value:.1%}"
                    elif "variance_ratio" in key or "peak_to" in key:
                        formatted = f"{value:.1f}x"
                    elif "latency" in key or "_ms" in key:
                        formatted = f"{value:,.0f} ms"
                    elif value > 1000:
                        formatted = f"{value:,.0f}"
                    else:
                        formatted = f"{value:.2f}"
                else:
                    formatted = str(value)
                
                metrics_lines.append(f"• {nice_key}: {formatted}")
            
            metrics_text = "\n\n**Key Metrics:**\n" + "\n".join(metrics_lines)
        
        score_emoji = {
            DimensionScore.POSITIVE: "[+]",
            DimensionScore.NEUTRAL: "[~]",
            DimensionScore.NEGATIVE: "[-]",
            DimensionScore.INSUFFICIENT: "[?]",
        }.get(dim.score, "")
        
        return ExplanationSection(
            title=f"{score_emoji} {dim.name}",
            content=f"{dim.explanation}{metrics_text}",
            importance="normal",
        )
    
    def _data_quality_section(
        self, 
        result: AnalysisResult, 
        metrics: DeploymentMetrics
    ) -> ExplanationSection:
        """Generate data quality assessment section."""
        return ExplanationSection(
            title="Data Quality",
            content=(
                f"{result.data_quality}\n\n"
                f"**Data Summary:**\n"
                f"• Deployment: {metrics.deployment_name}\n"
                f"• Model: {metrics.model_name}\n"
                f"• Total Requests Analyzed: {metrics.total_requests:,}\n"
                f"• Data Points: {len(metrics.timestamps):,}"
            ),
            importance="normal",
        )
    
    def _what_would_change_section(self, result: AnalysisResult) -> ExplanationSection:
        """Generate what-would-change section."""
        return ExplanationSection(
            title="What Would Change This Recommendation",
            content=result.what_would_change,
            importance="normal",
        )
    
    def _next_steps(self, result: AnalysisResult) -> ExplanationSection:
        """Generate next steps section."""
        if result.recommendation == Recommendation.PTU_RECOMMENDED:
            content = (
                "**Recommended Next Steps:**\n\n"
                "1. **Calculate PTU sizing**: Use the Azure PTU calculator to "
                "determine the right number of PTUs based on your TPM requirements.\n\n"
                "2. **Review commitment options**: PTU offers monthly and yearly "
                "commitments with different pricing.\n\n"
                "3. **Plan migration**: Consider a gradual rollout - start with "
                "one deployment before migrating all workloads.\n\n"
                "4. **Set up monitoring**: Ensure you have alerts for PTU utilization "
                "to optimize capacity."
            )
        elif result.recommendation == Recommendation.BORDERLINE:
            content = (
                "**Recommended Next Steps:**\n\n"
                "1. **Run a load test**: Simulate production traffic to observe "
                "behavior under controlled conditions.\n\n"
                "2. **Extend analysis period**: Re-run this analysis after "
                "collecting 2-4 more weeks of data.\n\n"
                "3. **Evaluate cost tradeoffs**: Calculate the cost difference "
                "between PTU and PAYG for your specific usage.\n\n"
                "4. **Consult with your CSA**: Discuss your specific requirements "
                "and use case."
            )
        else:
            content = (
                "**Recommended Next Steps:**\n\n"
                "1. **Continue with PAYG**: Your current usage pattern is "
                "well-suited for pay-as-you-go pricing.\n\n"
                "2. **Monitor for changes**: If usage patterns change (more "
                "consistent, higher volume), re-evaluate PTU.\n\n"
                "3. **Optimize current usage**: Focus on request batching and "
                "caching to reduce costs.\n\n"
                "4. **Set up alerts**: Monitor throttling rates in case capacity "
                "needs change."
            )
        
        return ExplanationSection(
            title="Next Steps",
            content=content,
            importance="high",
        )
