"""Prompt templates for LLM-powered explanations.

These prompts are carefully crafted to produce consistent, insightful,
and actionable explanations for PTU recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class MetricsContext:
    """Structured metrics context for prompts."""
    
    # Deployment info
    deployment_name: str
    model_name: str
    analysis_period: str
    
    # Token metrics
    avg_tpm: float
    peak_tpm: float
    tpm_std: float
    tpm_cv: float  # Coefficient of variation
    
    # Utilization patterns
    peak_to_avg_ratio: float
    sustained_utilization: float
    active_hours_pct: float
    business_hours_concentration: float
    weekend_weekday_ratio: float
    
    # Capacity pressure
    throttling_rate: float
    total_requests: int
    throttled_requests: int
    
    # Latency
    latency_p50: float
    latency_p95: float
    latency_p99: float
    
    # Recommendation
    recommendation: str  # PTU_RECOMMENDED, BORDERLINE, PTU_NOT_RECOMMENDED
    confidence: float
    
    # Dimension scores
    workload_shape_score: str
    capacity_pressure_score: str
    latency_sensitivity_score: str
    load_predictability_score: str
    
    def to_prompt_context(self) -> str:
        """Format metrics as structured context for LLM."""
        return f"""
## Deployment Information
- **Deployment Name**: {self.deployment_name}
- **Model**: {self.model_name}
- **Analysis Period**: {self.analysis_period}

## Token Usage Metrics
- **Average TPM**: {self.avg_tpm:,.0f} tokens/minute
- **Peak TPM (P95)**: {self.peak_tpm:,.0f} tokens/minute
- **Standard Deviation**: {self.tpm_std:,.0f}
- **Coefficient of Variation**: {self.tpm_cv:.2f} (lower = more stable)

## Utilization Patterns
- **Peak-to-Average Ratio**: {self.peak_to_avg_ratio:.2f}x
  - < 1.5 = stable workload, > 2.0 = spiky workload
- **Sustained Utilization**: {self.sustained_utilization:.1f}%
  - % of time usage is above 30% of peak
- **Active Hours**: {self.active_hours_pct:.1f}%
  - % of hours with meaningful activity
- **Business Hours Concentration**: {self.business_hours_concentration:.1f}%
  - % of usage during 9 AM - 6 PM
- **Weekend/Weekday Ratio**: {self.weekend_weekday_ratio:.1%}
  - How weekend usage compares to weekdays

## Capacity Pressure
- **Throttling Rate**: {self.throttling_rate:.2f}%
  - Requests returning 429 (rate limited)
- **Total Requests**: {self.total_requests:,}
- **Throttled Requests**: {self.throttled_requests:,}

## Latency Performance
- **P50 Latency**: {self.latency_p50:,.0f} ms
- **P95 Latency**: {self.latency_p95:,.0f} ms
- **P99 Latency**: {self.latency_p99:,.0f} ms

## Analysis Scores
- **Workload Shape**: {self.workload_shape_score}
- **Capacity Pressure**: {self.capacity_pressure_score}
- **Latency Sensitivity**: {self.latency_sensitivity_score}
- **Load Predictability**: {self.load_predictability_score}

## Recommendation
- **Decision**: {self.recommendation}
- **Confidence**: {self.confidence:.0f}%
"""


class PromptTemplates:
    """Collection of prompt templates for different explanation types."""
    
    SYSTEM_PROMPT = """You are an expert Azure AI architect specializing in Foundry deployment optimization and cost management. Your role is to analyze deployment metrics and provide clear, actionable insights about whether PTU (Provisioned Throughput Units) or PAYG (Pay-As-You-Go) pricing is optimal.

## Your Expertise
- Deep understanding of Foundry pricing models (PTU vs PAYG)
- Expertise in workload characterization and capacity planning
- Knowledge of latency optimization and throughput management
- Experience with production AI deployments at scale

## Communication Style
- Be concise but thorough
- Use data to support every claim
- Provide specific, actionable recommendations
- Use markdown formatting for readability
- Include relevant emojis for visual scanning
- Avoid jargon without explanation

## Key PTU Decision Factors
1. **Workload Consistency**: PTU favors predictable, steady workloads
2. **Capacity Pressure**: High throttling rates signal PTU need
3. **Latency Requirements**: PTU provides guaranteed, lower latency
4. **Utilization**: PTU is cost-effective at >60% sustained utilization
5. **Business Requirements**: SLAs, compliance, cost predictability

## PTU Pricing Context
- PTU is billed hourly regardless of usage
- Minimum deployments: 15 PTU (Global/DataZone), 50 PTU (Regional)
- 1-Year reservation saves ~65% vs hourly rates
- PAYG charges per 1K tokens consumed"""

    MAIN_ANALYSIS_PROMPT = """Based on the following deployment metrics, provide a comprehensive analysis explaining the PTU recommendation. Focus on the specific numbers and patterns observed.

{metrics_context}

## Your Task
Provide a detailed analysis in the following format:

### 📊 Executive Summary
A 2-3 sentence summary of the recommendation and key drivers.

### 🔍 Key Observations
Analyze the most important metrics that influenced the decision. Reference specific numbers.

### 💡 Insight
Explain the underlying business/technical reason why this recommendation makes sense.

### ⚡ Recommended Action
Provide specific, actionable next steps.

Keep your response under 400 words. Focus on insights, not just restating metrics."""

    DIMENSION_EXPLANATION_PROMPT = """Analyze this specific dimension of the PTU analysis:

**Dimension**: {dimension_name}
**Score**: {dimension_score}

{metrics_context}

Explain in 2-3 sentences why this dimension received this score. Reference specific metrics that drove the scoring. Be precise and data-driven."""

    WHAT_IF_PROMPT = """Based on these current metrics:

{metrics_context}

The user is asking: "{user_question}"

Provide a thoughtful analysis of this what-if scenario. Consider:
- How the change would affect key metrics
- Whether the PTU recommendation would change
- Specific thresholds or volumes where the decision would flip
- Any risks or considerations

Keep your response under 200 words and be specific with numbers."""

    COST_COMPARISON_PROMPT = """Generate a clear cost comparison based on these metrics:

{metrics_context}

## Additional Context
- PTU Hourly Rate: ${ptu_hourly_rate}/PTU/hour
- PAYG Input Rate: ${payg_input_rate}/1K tokens
- PAYG Output Rate: ${payg_output_rate}/1K tokens
- Estimated Input/Output Ratio: {io_ratio}

Calculate and explain:
1. Estimated monthly PAYG cost at current usage
2. PTU cost for recommended sizing
3. Break-even utilization point
4. Which option is more cost-effective and by how much

Be specific with dollar amounts and percentages."""

    EXECUTIVE_SUMMARY_PROMPT = """Generate a brief executive summary (suitable for a slide or email) based on this analysis:

{metrics_context}

The summary should be:
- 3-4 bullet points maximum
- Suitable for non-technical stakeholders
- Include the recommendation, key reason, and estimated cost impact
- Actionable and clear"""

    @classmethod
    def build_main_analysis_prompt(cls, context: MetricsContext) -> tuple[str, str]:
        """Build system and user prompts for main analysis."""
        return (
            cls.SYSTEM_PROMPT,
            cls.MAIN_ANALYSIS_PROMPT.format(metrics_context=context.to_prompt_context())
        )
    
    @classmethod
    def build_dimension_prompt(
        cls, 
        context: MetricsContext,
        dimension_name: str,
        dimension_score: str
    ) -> tuple[str, str]:
        """Build prompts for dimension-specific explanation."""
        return (
            cls.SYSTEM_PROMPT,
            cls.DIMENSION_EXPLANATION_PROMPT.format(
                dimension_name=dimension_name,
                dimension_score=dimension_score,
                metrics_context=context.to_prompt_context()
            )
        )
    
    @classmethod
    def build_what_if_prompt(
        cls,
        context: MetricsContext,
        user_question: str
    ) -> tuple[str, str]:
        """Build prompts for what-if scenario analysis."""
        return (
            cls.SYSTEM_PROMPT,
            cls.WHAT_IF_PROMPT.format(
                metrics_context=context.to_prompt_context(),
                user_question=user_question
            )
        )
    
    @classmethod
    def build_cost_comparison_prompt(
        cls,
        context: MetricsContext,
        ptu_hourly_rate: float = 2.0,
        payg_input_rate: float = 0.0025,
        payg_output_rate: float = 0.01,
        io_ratio: float = 0.4
    ) -> tuple[str, str]:
        """Build prompts for cost comparison analysis."""
        return (
            cls.SYSTEM_PROMPT,
            cls.COST_COMPARISON_PROMPT.format(
                metrics_context=context.to_prompt_context(),
                ptu_hourly_rate=ptu_hourly_rate,
                payg_input_rate=payg_input_rate,
                payg_output_rate=payg_output_rate,
                io_ratio=io_ratio
            )
        )
    
    @classmethod  
    def build_executive_summary_prompt(cls, context: MetricsContext) -> tuple[str, str]:
        """Build prompts for executive summary."""
        return (
            cls.SYSTEM_PROMPT,
            cls.EXECUTIVE_SUMMARY_PROMPT.format(
                metrics_context=context.to_prompt_context()
            )
        )
