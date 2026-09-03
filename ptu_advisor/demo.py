"""Demo mode with simulated scenarios for PTU Advisor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

# Use numpy RNG exclusively for reproducibility (np.random.seed controls all)
_rng = np.random.default_rng()
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ptu_advisor.metrics.models import (
    DeploymentInfo,
    DeploymentMetrics,
    TimeSeries,
)


console = Console()


class DemoScenario(str, Enum):
    """Available demo scenarios."""

    # Legacy / general scenarios (kept for CLI compatibility)
    PTU_RECOMMENDED = "ptu-recommended"
    PTU_NOT_RECOMMENDED = "ptu-not-recommended"
    BORDERLINE = "borderline"

    # Cost Reduction focus
    COST_HIGH_VOLUME = "cost-high-volume"
    COST_LOW_VOLUME = "cost-low-volume"

    # Throttling & Reliability focus
    THROTTLE_HEAVY = "throttle-heavy"
    THROTTLE_MINIMAL = "throttle-minimal"

    # Latency Optimization focus
    LATENCY_SLA_CRITICAL = "latency-sla-critical"
    LATENCY_TOLERANT = "latency-tolerant"

    # Predictable Billing focus
    BILLING_STEADY = "billing-steady"
    BILLING_VARIABLE = "billing-variable"

    # Guaranteed Capacity focus
    CAPACITY_MISSION_CRITICAL = "capacity-mission-critical"
    CAPACITY_BEST_EFFORT = "capacity-best-effort"

    # Consolidation focus
    CONSOLIDATE_WORTH_IT = "consolidate-worth-it"
    CONSOLIDATE_NOT_WORTH_IT = "consolidate-not-worth-it"


@dataclass
class ScenarioConfig:
    """Configuration for a demo scenario."""

    name: str
    description: str
    deployment_name: str
    model_name: str

    # Workload shape parameters
    tpm_mean: float
    tpm_std: float
    tpm_spikes: bool

    # Capacity pressure parameters
    throttling_rate: float
    utilization_pct: float

    # Latency parameters
    latency_p50: float
    latency_p95: float
    latency_p99: float
    latency_variance: float

    # Load predictability
    active_hours_pct: float
    daily_pattern_consistency: float

    # Request patterns
    avg_requests_per_hour: float
    avg_tokens_per_request: float


# Pre-defined scenarios
SCENARIOS = {
    DemoScenario.PTU_RECOMMENDED: ScenarioConfig(
        name="High-Volume Cost Optimization Workload",
        description=(
            "Enterprise AI platform running 24/7 across customer support, document processing, "
            "and internal automation. Sustained high token volume far exceeds the PAYG cost "
            "breakeven point — PTU delivers significant cost savings at this scale. "
            "Predictable daily patterns and constant capacity pressure make reserved capacity "
            "the clear cost-effective choice."
        ),
        deployment_name="gpt-4o-enterprise-platform-prod",
        model_name="gpt-4o (2024-11-20)",
        # Very stable, high-volume workload — ideal for cost savings on PTU
        tpm_mean=120000.0,
        tpm_std=5000.0,
        tpm_spikes=False,
        # High capacity pressure — consistently hitting PAYG limits costs more
        throttling_rate=0.07,  # 7% throttled — above 5% threshold for POSITIVE
        utilization_pct=0.88,  # 88% utilized — well above breakeven
        # Moderate latency variance — shared PAYG infra shows inconsistency
        latency_p50=350.0,
        latency_p95=1800.0,
        latency_p99=3500.0,
        latency_variance=1.0,
        # Near-24/7 usage with moderate business-hour peaks — PTU capacity well utilized
        active_hours_pct=0.75,
        daily_pattern_consistency=0.95,
        # Very high sustained volume — the cost advantage of PTU shines here
        avg_requests_per_hour=3200.0,
        avg_tokens_per_request=780.0,
    ),
    DemoScenario.PTU_NOT_RECOMMENDED: ScenarioConfig(
        name="Internal Dev/Test Assistant",
        description=(
            "AI coding assistant used by a 15-person development team. "
            "Usage is sporadic - mostly during code reviews and debugging sessions. "
            "No SLA requirements, team is cost-conscious."
        ),
        deployment_name="gpt-4o-dev-assistant",
        model_name="gpt-4o-mini (2024-07-18)",
        # Spiky, inconsistent workload
        tpm_mean=8000.0,
        tpm_std=15000.0,  # High variance
        tpm_spikes=True,
        # Low capacity pressure
        throttling_rate=0.002,  # 0.2% throttled
        utilization_pct=0.15,  # 15% utilized
        # Good latency
        latency_p50=320.0,
        latency_p95=580.0,
        latency_p99=850.0,
        latency_variance=0.3,
        # Unpredictable, sparse usage
        active_hours_pct=0.25,
        daily_pattern_consistency=0.35,
        # Low volume
        avg_requests_per_hour=45.0,
        avg_tokens_per_request=1200.0,
    ),
    DemoScenario.BORDERLINE: ScenarioConfig(
        name="E-commerce Product Recommendations",
        description=(
            "AI-powered product recommendation engine for mid-size e-commerce platform. "
            "Traffic follows weekly patterns with weekend spikes. "
            "Some throttling during flash sales but generally stable."
        ),
        deployment_name="gpt-4o-recommendations",
        model_name="gpt-4o (2024-11-20)",
        # Moderately variable workload
        tpm_mean=35000.0,
        tpm_std=18000.0,
        tpm_spikes=True,
        # Moderate capacity pressure
        throttling_rate=0.025,  # 2.5% throttled
        utilization_pct=0.65,
        # Moderate latency
        latency_p50=380.0,
        latency_p95=1500.0,
        latency_p99=3200.0,
        latency_variance=0.8,
        # Somewhat predictable
        active_hours_pct=0.55,
        daily_pattern_consistency=0.68,
        # Medium volume
        avg_requests_per_hour=850.0,
        avg_tokens_per_request=620.0,
    ),
    # =========================================================================
    # COST REDUCTION FOCUS SCENARIOS
    # =========================================================================
    DemoScenario.COST_HIGH_VOLUME: ScenarioConfig(
        name="Enterprise AI Platform (24/7)",
        description=(
            "Enterprise AI platform processing customer support tickets, document analysis, "
            "and internal automation around the clock. Monthly PAYG spend exceeds $15K with "
            "steady growth. Stable, high-volume usage makes PTU significantly cheaper."
        ),
        deployment_name="gpt-4o-enterprise-platform-prod",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=130000.0,
        tpm_std=8000.0,
        tpm_spikes=False,
        throttling_rate=0.08,
        utilization_pct=0.85,
        latency_p50=500.0,
        latency_p95=5200.0,
        latency_p99=9500.0,
        latency_variance=2.0,
        active_hours_pct=0.85,
        daily_pattern_consistency=0.95,
        avg_requests_per_hour=3500.0,
        avg_tokens_per_request=750.0,
    ),
    DemoScenario.COST_LOW_VOLUME: ScenarioConfig(
        name="Internal Summarization Tool",
        description=(
            "Small internal tool used by a 10-person team for ad-hoc document summarization. "
            "Sporadic usage during business hours only. Monthly spend under $500 — well below "
            "the PTU break-even point. PAYG is the clear cost winner."
        ),
        deployment_name="gpt-4o-mini-internal-tools",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=5000.0,
        tpm_std=8000.0,
        tpm_spikes=True,
        throttling_rate=0.001,
        utilization_pct=0.10,
        latency_p50=280.0,
        latency_p95=450.0,
        latency_p99=700.0,
        latency_variance=0.3,
        active_hours_pct=0.20,
        daily_pattern_consistency=0.30,
        avg_requests_per_hour=30.0,
        avg_tokens_per_request=1500.0,
    ),
    # =========================================================================
    # THROTTLING & RELIABILITY FOCUS SCENARIOS
    # =========================================================================
    DemoScenario.THROTTLE_HEAVY: ScenarioConfig(
        name="Customer Chatbot — Severe Throttling",
        description=(
            "Customer-facing chatbot with 15% of requests throttled during peak business hours. "
            "Each HTTP 429 error means a customer sees 'try again later' — directly impacting "
            "satisfaction and conversion. Retry storms amplify the problem further."
        ),
        deployment_name="gpt-4o-customer-chatbot-prod",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=95000.0,
        tpm_std=12000.0,
        tpm_spikes=False,
        throttling_rate=0.15,
        utilization_pct=0.95,
        latency_p50=600.0,
        latency_p95=3500.0,
        latency_p99=8000.0,
        latency_variance=1.5,
        active_hours_pct=0.75,
        daily_pattern_consistency=0.85,
        avg_requests_per_hour=2200.0,
        avg_tokens_per_request=650.0,
    ),
    DemoScenario.THROTTLE_MINIMAL: ScenarioConfig(
        name="Analytics Helper — Comfortable Headroom",
        description=(
            "Internal analytics helper with comfortable PAYG capacity headroom. "
            "Throttling rate is below 0.5% — the shared quota is more than sufficient. "
            "No reliability concerns at current usage levels."
        ),
        deployment_name="gpt-4o-mini-analytics-helper",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=25000.0,
        tpm_std=5000.0,
        tpm_spikes=False,
        throttling_rate=0.003,
        utilization_pct=0.40,
        latency_p50=250.0,
        latency_p95=500.0,
        latency_p99=750.0,
        latency_variance=0.2,
        active_hours_pct=0.50,
        daily_pattern_consistency=0.65,
        avg_requests_per_hour=600.0,
        avg_tokens_per_request=700.0,
    ),
    # =========================================================================
    # LATENCY OPTIMIZATION FOCUS SCENARIOS
    # =========================================================================
    DemoScenario.LATENCY_SLA_CRITICAL: ScenarioConfig(
        name="Real-Time Support Agent — Strict SLA",
        description=(
            "Real-time customer support agent with a <2 second SLA on first response. "
            "Shared PAYG infrastructure causes unpredictable latency spikes — P99 reaches "
            "12 seconds during peak hours, violating SLA for 5% of interactions. "
            "PTU's dedicated capacity delivers consistent sub-second responses."
        ),
        deployment_name="gpt-4o-realtime-support-prod",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=80000.0,
        tpm_std=10000.0,
        tpm_spikes=False,
        throttling_rate=0.07,
        utilization_pct=0.80,
        latency_p50=800.0,
        latency_p95=5500.0,
        latency_p99=14000.0,
        latency_variance=2.5,
        active_hours_pct=0.80,
        daily_pattern_consistency=0.88,
        avg_requests_per_hour=2000.0,
        avg_tokens_per_request=650.0,
    ),
    DemoScenario.LATENCY_TOLERANT: ScenarioConfig(
        name="Background Batch Summarization",
        description=(
            "Nightly batch document summarization pipeline. Processes 10K documents in "
            "background queues with no real-time SLA. Occasional latency spikes are fine — "
            "throughput and cost matter more than individual response time."
        ),
        deployment_name="gpt-4o-batch-summarizer",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=40000.0,
        tpm_std=10000.0,
        tpm_spikes=True,
        throttling_rate=0.01,
        utilization_pct=0.50,
        latency_p50=300.0,
        latency_p95=600.0,
        latency_p99=1200.0,
        latency_variance=0.3,
        active_hours_pct=0.40,
        daily_pattern_consistency=0.50,
        avg_requests_per_hour=1000.0,
        avg_tokens_per_request=900.0,
    ),
    # =========================================================================
    # PREDICTABLE BILLING FOCUS SCENARIOS
    # =========================================================================
    DemoScenario.BILLING_STEADY: ScenarioConfig(
        name="Enterprise Copilot — Fixed IT Budget",
        description=(
            "Enterprise AI copilot powering 500+ employees. Finance requires predictable "
            "monthly costs for annual budget planning. Current PAYG bills vary ±30% month-to-month, "
            "causing quarterly budget re-forecasting. PTU provides a fixed monthly line item."
        ),
        deployment_name="gpt-4o-enterprise-copilot",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=100000.0,
        tpm_std=6000.0,
        tpm_spikes=False,
        throttling_rate=0.06,
        utilization_pct=0.80,
        latency_p50=400.0,
        latency_p95=5500.0,
        latency_p99=10000.0,
        latency_variance=2.5,
        active_hours_pct=0.90,
        daily_pattern_consistency=0.95,
        avg_requests_per_hour=2800.0,
        avg_tokens_per_request=700.0,
    ),
    DemoScenario.BILLING_VARIABLE: ScenarioConfig(
        name="Startup MVP — Rapidly Changing Usage",
        description=(
            "Early-stage startup MVP with product-market fit exploration. Usage doubles or halves "
            "week-to-week as features are tested. A fixed PTU commitment would be risky — PAYG's "
            "pay-per-use flexibility is ideal while the product is still evolving."
        ),
        deployment_name="gpt-4o-mini-startup-mvp",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=15000.0,
        tpm_std=20000.0,
        tpm_spikes=True,
        throttling_rate=0.005,
        utilization_pct=0.25,
        latency_p50=200.0,
        latency_p95=400.0,
        latency_p99=600.0,
        latency_variance=0.3,
        active_hours_pct=0.35,
        daily_pattern_consistency=0.40,
        avg_requests_per_hour=200.0,
        avg_tokens_per_request=1100.0,
    ),
    # =========================================================================
    # GUARANTEED CAPACITY FOCUS SCENARIOS
    # =========================================================================
    DemoScenario.CAPACITY_MISSION_CRITICAL: ScenarioConfig(
        name="Healthcare Clinical AI — 99.9% SLA",
        description=(
            "Healthcare clinical decision support system used in emergency departments. "
            "Regulatory SLA requires 99.9% availability — every HTTP 429 is a compliance incident. "
            "Patient safety depends on guaranteed AI responses. PTU provides dedicated GPU capacity "
            "that eliminates shared-infrastructure risks."
        ),
        deployment_name="gpt-4o-healthcare-clinical-prod",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=70000.0,
        tpm_std=7000.0,
        tpm_spikes=False,
        throttling_rate=0.10,
        utilization_pct=0.80,
        latency_p50=500.0,
        latency_p95=5200.0,
        latency_p99=9000.0,
        latency_variance=2.0,
        active_hours_pct=0.90,
        daily_pattern_consistency=0.92,
        avg_requests_per_hour=1800.0,
        avg_tokens_per_request=680.0,
    ),
    DemoScenario.CAPACITY_BEST_EFFORT: ScenarioConfig(
        name="Internal Team Assistant — No SLA",
        description=(
            "Internal team assistant for brainstorming and document drafts. Best-effort "
            "availability is perfectly acceptable — the team can wait or retry manually. "
            "No external SLA, no compliance requirements, no need for guaranteed capacity."
        ),
        deployment_name="gpt-4o-mini-team-assistant",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=12000.0,
        tpm_std=9000.0,
        tpm_spikes=True,
        throttling_rate=0.005,
        utilization_pct=0.20,
        latency_p50=220.0,
        latency_p95=400.0,
        latency_p99=650.0,
        latency_variance=0.3,
        active_hours_pct=0.30,
        daily_pattern_consistency=0.40,
        avg_requests_per_hour=150.0,
        avg_tokens_per_request=1300.0,
    ),
    # =========================================================================
    # CONSOLIDATION FOCUS SCENARIOS
    # =========================================================================
    # These scenarios define the *first* sibling deployment only. The
    # ``generate_consolidation_demo_metrics()`` function uses these as a
    # template and generates 2 additional sibling deployments with scaled
    # parameters.
    DemoScenario.CONSOLIDATE_WORTH_IT: ScenarioConfig(
        name="Customer Chat (Consolidation — Worth It)",
        description=(
            "High-volume customer chat deployment that, combined with sibling doc-processing "
            "and batch-analytics deployments, crosses the PTU break-even threshold. "
            "Individually each deployment is borderline, but together they justify PTU."
        ),
        deployment_name="gpt-4o-customer-chat",
        model_name="gpt-4o (2024-11-20)",
        tpm_mean=15000.0,
        tpm_std=3000.0,
        tpm_spikes=False,
        throttling_rate=0.02,
        utilization_pct=0.55,
        latency_p50=350.0,
        latency_p95=1800.0,
        latency_p99=3500.0,
        latency_variance=0.8,
        active_hours_pct=0.70,
        daily_pattern_consistency=0.80,
        avg_requests_per_hour=800.0,
        avg_tokens_per_request=700.0,
    ),
    DemoScenario.CONSOLIDATE_NOT_WORTH_IT: ScenarioConfig(
        name="Internal Summaries (Consolidation — Not Worth It)",
        description=(
            "Low-volume internal summarization deployment that, even combined with sibling "
            "deployments, stays well below the PTU break-even point. PAYG remains cheaper."
        ),
        deployment_name="gpt-4o-mini-summaries",
        model_name="gpt-4o-mini (2024-07-18)",
        tpm_mean=3000.0,
        tpm_std=2000.0,
        tpm_spikes=True,
        throttling_rate=0.0,
        utilization_pct=0.10,
        latency_p50=250.0,
        latency_p95=500.0,
        latency_p99=750.0,
        latency_variance=0.3,
        active_hours_pct=0.25,
        daily_pattern_consistency=0.35,
        avg_requests_per_hour=40.0,
        avg_tokens_per_request=1200.0,
    ),
}

# Sibling deployment definitions for consolidation demo scenarios.
# Each entry maps a consolidation scenario to a list of
# (deployment_name, tpm_scale, throttle_scale) tuples describing how to
# derive siblings from the base ScenarioConfig.
_CONSOLIDATION_SIBLINGS: Dict[DemoScenario, List[Tuple[str, float, float]]] = {
    DemoScenario.CONSOLIDATE_WORTH_IT: [
        # Deployment B: doc-processing — 80% of base TPM, 75% throttle
        ("gpt-4o-doc-processing", 0.80, 0.75),
        # Deployment C: batch-analytics — 53% of base TPM, 25% throttle
        ("gpt-4o-batch-analytics", 0.53, 0.25),
    ],
    DemoScenario.CONSOLIDATE_NOT_WORTH_IT: [
        # Deployment B — 50% of base TPM, no throttle
        ("gpt-4o-mini-reports", 0.50, 0.0),
        # Deployment C — 27% of base TPM, no throttle
        ("gpt-4o-mini-qa-bot", 0.27, 0.0),
    ],
}


# =============================================================================
# Focus Topics → Scenario Mapping (used by the dashboard)
# =============================================================================

FOCUS_TOPICS = {
    "Cost Reduction": {
        "icon": "¤",
        "tagline": "Find out if PTU saves money at your usage level",
        "scenarios": {
            DemoScenario.COST_HIGH_VOLUME: "Enterprise 24/7 platform — clear PTU savings",
            DemoScenario.COST_LOW_VOLUME: "Internal tool with low usage — PAYG wins",
        },
    },
    "Throttling & Reliability": {
        "icon": "⊘",
        "tagline": "Evaluate if PTU would eliminate HTTP 429 rate-limiting",
        "scenarios": {
            DemoScenario.THROTTLE_HEAVY: "Customer chatbot with 15% request failures",
            DemoScenario.THROTTLE_MINIMAL: "Analytics helper with <1% throttling",
        },
    },
    "Latency Optimization": {
        "icon": "◷",
        "tagline": "Assess if dedicated PTU capacity improves response times",
        "scenarios": {
            DemoScenario.LATENCY_SLA_CRITICAL: "Real-time support agent with <2s SLA",
            DemoScenario.LATENCY_TOLERANT: "Background batch pipeline — latency tolerant",
        },
    },
    "Predictable Billing": {
        "icon": "▦",
        "tagline": "Compare fixed PTU costs vs variable PAYG bills",
        "scenarios": {
            DemoScenario.BILLING_STEADY: "Enterprise copilot with fixed IT budget",
            DemoScenario.BILLING_VARIABLE: "Startup MVP with rapidly changing patterns",
        },
    },
    "Guaranteed Capacity": {
        "icon": "⬢",
        "tagline": "Reserve dedicated GPU capacity for mission-critical workloads",
        "scenarios": {
            DemoScenario.CAPACITY_MISSION_CRITICAL: "Healthcare AI with 99.9% SLA requirement",
            DemoScenario.CAPACITY_BEST_EFFORT: "Internal team assistant — no SLA needed",
        },
    },
}


def generate_demo_metrics(
    scenario: DemoScenario,
    lookback_days: int = 14,
    granularity_minutes: int = 60,
) -> Tuple[DeploymentMetrics, ScenarioConfig]:
    """
    Generate realistic demo metrics for a scenario.

    Args:
        scenario: The demo scenario to generate.
        lookback_days: Number of days of data to generate.
        granularity_minutes: Aggregation interval in minutes (5, 15, 30, 60).

    Returns:
        Tuple of (DeploymentMetrics, ScenarioConfig).
    """
    config = SCENARIOS[scenario]

    # Generate timestamps at the selected granularity for the lookback period.
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    granularity = granularity_minutes if granularity_minutes in (1, 5, 15, 30, 60) else 5
    point_count = max(2, int((lookback_days * 24 * 60) / granularity))
    timestamps = [start_time + timedelta(minutes=i * granularity) for i in range(point_count)]

    # Generate TPM based on scenario
    tpm_values = _generate_tpm_series(config, timestamps)

    # Generate RPM (requests per minute)
    rpm_values = _generate_rpm_series(config, timestamps)

    # Generate throttling
    throttled, successful = _generate_throttling_series(config, timestamps, rpm_values)

    # Generate latency
    p50_values, p95_values, p99_values = _generate_latency_series(config, timestamps)

    # Generate token breakdown
    prompt_tokens, completion_tokens = _generate_token_series(config, timestamps, tpm_values)

    # Synthesize prompt-cache hit rate
    cache_match_values = _generate_cache_match_series(config, timestamps)

    metrics = DeploymentMetrics(
        deployment_name=config.deployment_name,
        model_name=config.model_name,
        start_time=start_time,
        end_time=end_time,
        timestamps=timestamps,
        tokens_per_minute=TimeSeries(
            timestamps=timestamps,
            values=tpm_values,
            metric_name="TokensPerMinute",
            unit="Count",
        ),
        requests_per_minute=TimeSeries(
            timestamps=timestamps,
            values=rpm_values,
            metric_name="RequestsPerMinute",
            unit="Count",
        ),
        throttled_requests=TimeSeries(
            timestamps=timestamps,
            values=throttled,
            metric_name="ThrottledRequests",
            unit="Count",
        ),
        successful_requests=TimeSeries(
            timestamps=timestamps,
            values=successful,
            metric_name="SuccessfulRequests",
            unit="Count",
        ),
        prompt_tokens=TimeSeries(
            timestamps=timestamps,
            values=prompt_tokens,
            metric_name="PromptTokens",
            unit="Count",
        ),
        completion_tokens=TimeSeries(
            timestamps=timestamps,
            values=completion_tokens,
            metric_name="CompletionTokens",
            unit="Count",
        ),
        time_to_first_byte_p50=TimeSeries(
            timestamps=timestamps,
            values=p50_values,
            metric_name="TimeToFirstByte_P50",
            unit="Milliseconds",
        ),
        time_to_first_byte_p95=TimeSeries(
            timestamps=timestamps,
            values=p95_values,
            metric_name="TimeToFirstByte_P95",
            unit="Milliseconds",
        ),
        time_to_first_byte_p99=TimeSeries(
            timestamps=timestamps,
            values=p99_values,
            metric_name="TimeToFirstByte_P99",
            unit="Milliseconds",
        ),
        cache_match_rate=TimeSeries(
            timestamps=timestamps,
            values=cache_match_values,
            metric_name="AzureOpenAIContextTokensCacheMatchRate",
            unit="Percent",
        ),
    )

    metrics.deployment_info = DeploymentInfo(
        name=config.deployment_name,
        model=config.model_name,
        sku_type="Standard",
        sku_capacity=None,
    )

    return metrics, config


def generate_consolidation_demo_metrics(
    scenario: DemoScenario,
    lookback_days: int = 14,
    granularity_minutes: int = 60,
) -> List[DeploymentMetrics]:
    """Generate a list of sibling DeploymentMetrics for a consolidation demo.

    Each consolidation scenario produces 3 same-model deployments:
    - Deployment A: generated directly from the scenario config.
    - Deployments B, C: derived by scaling TPM/throttle from A's config.

    Args:
        scenario: Must be a consolidation scenario
            (CONSOLIDATE_WORTH_IT or CONSOLIDATE_NOT_WORTH_IT).
        lookback_days: Number of days of data to generate.
        granularity_minutes: Aggregation interval in minutes.

    Returns:
        List of 3 DeploymentMetrics (all sharing the same model name).
    """
    if scenario not in _CONSOLIDATION_SIBLINGS:
        raise ValueError(
            f"{scenario.value} is not a consolidation scenario. "
            f"Use one of: {[s.value for s in _CONSOLIDATION_SIBLINGS]}"
        )

    base_config = SCENARIOS[scenario]
    siblings_spec = _CONSOLIDATION_SIBLINGS[scenario]

    # Generate Deployment A from the base scenario config
    dep_a, _ = generate_demo_metrics(scenario, lookback_days, granularity_minutes)
    all_deployments: List[DeploymentMetrics] = [dep_a]

    # Generate siblings B, C by cloning the base config with scaled params
    for sib_name, tpm_scale, throttle_scale in siblings_spec:
        sibling_config = ScenarioConfig(
            name=f"{base_config.name} — sibling",
            description=base_config.description,
            deployment_name=sib_name,
            model_name=base_config.model_name,
            tpm_mean=base_config.tpm_mean * tpm_scale,
            tpm_std=base_config.tpm_std * tpm_scale,
            tpm_spikes=base_config.tpm_spikes,
            throttling_rate=base_config.throttling_rate * throttle_scale,
            utilization_pct=base_config.utilization_pct * tpm_scale,
            latency_p50=base_config.latency_p50 * (0.9 + 0.2 * tpm_scale),
            latency_p95=base_config.latency_p95 * (0.9 + 0.2 * tpm_scale),
            latency_p99=base_config.latency_p99 * (0.9 + 0.2 * tpm_scale),
            latency_variance=base_config.latency_variance,
            active_hours_pct=base_config.active_hours_pct,
            daily_pattern_consistency=base_config.daily_pattern_consistency,
            avg_requests_per_hour=base_config.avg_requests_per_hour * tpm_scale,
            avg_tokens_per_request=base_config.avg_tokens_per_request,
        )

        # Temporarily inject sibling config into SCENARIOS so
        # generate_demo_metrics can look it up. We reuse the base scenario
        # key but swap the config, then restore afterward.
        # Instead, we just call the internal generators directly:
        # All siblings share the exact same buckets so consolidation can use
        # zero-fill semantics for genuinely missing intervals.
        start_time = dep_a.start_time
        end_time = dep_a.end_time
        timestamps = list(dep_a.timestamps)

        tpm_values = _generate_tpm_series(sibling_config, timestamps)
        rpm_values = _generate_rpm_series(sibling_config, timestamps)
        throttled, successful = _generate_throttling_series(sibling_config, timestamps, rpm_values)
        p50_values, p95_values, p99_values = _generate_latency_series(sibling_config, timestamps)
        prompt_tokens, completion_tokens = _generate_token_series(
            sibling_config, timestamps, tpm_values
        )
        cache_match_values = _generate_cache_match_series(sibling_config, timestamps)

        sib_metrics = DeploymentMetrics(
            deployment_name=sibling_config.deployment_name,
            model_name=sibling_config.model_name,
            start_time=start_time,
            end_time=end_time,
            timestamps=timestamps,
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=tpm_values,
                metric_name="TokensPerMinute",
                unit="Count",
            ),
            requests_per_minute=TimeSeries(
                timestamps=timestamps,
                values=rpm_values,
                metric_name="RequestsPerMinute",
                unit="Count",
            ),
            throttled_requests=TimeSeries(
                timestamps=timestamps,
                values=throttled,
                metric_name="ThrottledRequests",
                unit="Count",
            ),
            successful_requests=TimeSeries(
                timestamps=timestamps,
                values=successful,
                metric_name="SuccessfulRequests",
                unit="Count",
            ),
            prompt_tokens=TimeSeries(
                timestamps=timestamps,
                values=prompt_tokens,
                metric_name="PromptTokens",
                unit="Count",
            ),
            completion_tokens=TimeSeries(
                timestamps=timestamps,
                values=completion_tokens,
                metric_name="CompletionTokens",
                unit="Count",
            ),
            time_to_first_byte_p50=TimeSeries(
                timestamps=timestamps,
                values=p50_values,
                metric_name="TimeToFirstByte_P50",
                unit="Milliseconds",
            ),
            time_to_first_byte_p95=TimeSeries(
                timestamps=timestamps,
                values=p95_values,
                metric_name="TimeToFirstByte_P95",
                unit="Milliseconds",
            ),
            time_to_first_byte_p99=TimeSeries(
                timestamps=timestamps,
                values=p99_values,
                metric_name="TimeToFirstByte_P99",
                unit="Milliseconds",
            ),
            cache_match_rate=TimeSeries(
                timestamps=timestamps,
                values=cache_match_values,
                metric_name="AzureOpenAIContextTokensCacheMatchRate",
                unit="Percent",
            ),
        )

        sib_metrics.deployment_info = DeploymentInfo(
            name=sibling_config.deployment_name,
            model=sibling_config.model_name,
            sku_type="Standard",
            sku_capacity=None,
        )
        all_deployments.append(sib_metrics)

    return all_deployments


def _generate_tpm_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
) -> List[float]:
    """Generate tokens per minute time series.

    The ``daily_pattern_consistency`` parameter controls how much random
    noise is added.  High consistency (0.9+) produces a nearly-deterministic
    daily cycle that the engine's autocorrelation check can detect.
    """
    values = []

    # Scale random noise inversely with consistency so that
    # high-consistency workloads produce high autocorrelation.
    noise_scale = (1.0 - config.daily_pattern_consistency) * 0.5 + 0.02

    # Flatten daily amplitude for consistent workloads so TPM CV stays
    # below the 0.3 threshold when consistency is high.
    pattern_amplitude = 1.0 - config.daily_pattern_consistency * 0.7

    for ts in timestamps:
        hour = ts.hour
        weekday = ts.weekday()

        # Base value with noise (scaled by consistency)
        base = config.tpm_mean
        noise = np.random.normal(0, config.tpm_std * noise_scale)

        # Business hours multiplier — scaled by pattern_amplitude so
        # consistent workloads have a flatter daily curve.
        if 9 <= hour <= 18:
            multiplier = 1.0 + config.active_hours_pct * 0.5 * pattern_amplitude
        else:
            multiplier = 1.0 - config.active_hours_pct * 0.3 * pattern_amplitude

        # Weekend reduction — flatten for 24/7 workloads
        # High active_hours_pct → mild weekend dip; low → steep dip
        if weekday >= 5:
            weekend_factor = 0.6 * (1 - config.active_hours_pct) + config.active_hours_pct
            multiplier *= weekend_factor

        # Add spikes if configured
        if config.tpm_spikes and np.random.random() < 0.05:
            multiplier *= np.random.uniform(2.0, 4.0)

        # Add occasional zeros for sparse usage
        if config.active_hours_pct < 0.5 and np.random.random() > config.active_hours_pct:
            value = 0.0
        else:
            value = max(0, (base + noise) * multiplier)

        values.append(value)

    return values


def _generate_rpm_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
) -> List[float]:
    """Generate requests per minute time series.

    Uses ``daily_pattern_consistency`` to scale random noise so that
    high-consistency workloads produce strong autocorrelation signals.
    """
    values = []

    # Flatten daily and weekly cycles based on active_hours_pct.
    # Use a less aggressive flattening (× 0.6) so the deterministic
    # daily pattern remains detectable by the autocorrelation check
    # even for near-24/7 workloads.
    flatten = config.active_hours_pct * 0.6

    # Scale noise inversely with consistency — keep noise well below
    # the deterministic signal so autocorrelation stays high.
    noise_scale = (1.0 - config.daily_pattern_consistency) * 0.5 + 0.02

    for ts in timestamps:
        hour = ts.hour
        weekday = ts.weekday()

        # Base value with noise (scaled by consistency)
        base = config.avg_requests_per_hour / 60  # Convert to per minute
        noise = np.random.normal(0, base * noise_scale)

        # Business hours pattern — blend toward 1.0 for 24/7 workloads
        if 9 <= hour <= 18:
            raw_mult = 1.2
        elif 6 <= hour <= 9 or 18 <= hour <= 22:
            raw_mult = 0.7
        else:
            raw_mult = 0.3
        multiplier = raw_mult * (1 - flatten) + flatten

        # Weekend reduction — flatten for 24/7 workloads
        if weekday >= 5:
            weekend_factor = 0.5 * (1 - flatten) + flatten
            multiplier *= weekend_factor

        # Sparse usage handling
        if config.active_hours_pct < 0.5 and np.random.random() > config.active_hours_pct:
            value = 0.0
        else:
            value = max(0, (base + noise) * multiplier)

        values.append(value)

    return values


def _generate_throttling_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
    rpm_values: List[float],
) -> Tuple[List[float], List[float]]:
    """Generate throttled and successful request series."""
    throttled = []
    successful = []

    for i, ts in enumerate(timestamps):
        total_requests = rpm_values[i] * 60  # Requests per hour

        # Higher throttling during peak hours if throttling rate is high
        hour = ts.hour
        if 10 <= hour <= 16 and config.throttling_rate > 0.03:
            effective_rate = config.throttling_rate * 1.5
        else:
            effective_rate = config.throttling_rate * 0.7

        # Add randomness
        actual_rate = max(0, effective_rate + np.random.normal(0, effective_rate * 0.3))

        throttled_count = total_requests * actual_rate
        successful_count = total_requests - throttled_count

        throttled.append(max(0, throttled_count))
        successful.append(max(0, successful_count))

    return throttled, successful


def _generate_latency_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
) -> Tuple[List[float], List[float], List[float]]:
    """Generate latency percentile series."""
    p50_values = []
    p95_values = []
    p99_values = []

    for ts in timestamps:
        hour = ts.hour

        # Base latencies
        p50_base = config.latency_p50
        p95_base = config.latency_p95
        p99_base = config.latency_p99

        # Peak hours have higher latency if there's variance
        if 10 <= hour <= 16:
            multiplier = 1.0 + config.latency_variance * 0.3
        else:
            multiplier = 1.0 - config.latency_variance * 0.1

        # Add noise
        p50 = p50_base * multiplier * (1 + np.random.normal(0, 0.1))
        p95 = p95_base * multiplier * (1 + np.random.normal(0, 0.15))
        p99 = p99_base * multiplier * (1 + np.random.normal(0, 0.2))

        # Ensure ordering p50 <= p95 <= p99
        p50 = max(100, p50)
        p95 = max(p50 * 1.5, p95)
        p99 = max(p95 * 1.2, p99)

        p50_values.append(p50)
        p95_values.append(p95)
        p99_values.append(p99)

    return p50_values, p95_values, p99_values


def _generate_token_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
    tpm_values: List[float],
) -> Tuple[List[float], List[float]]:
    """Generate prompt and completion token series."""
    prompt_tokens = []
    completion_tokens = []

    for tpm in tpm_values:
        # Typical ratio: 60% prompt, 40% completion
        ratio = 0.6 + np.random.normal(0, 0.1)
        ratio = max(0.4, min(0.8, ratio))

        prompt = tpm * ratio
        completion = tpm * (1 - ratio)

        prompt_tokens.append(prompt)
        completion_tokens.append(completion)

    return prompt_tokens, completion_tokens


def _generate_cache_match_series(
    config: ScenarioConfig,
    timestamps: List[datetime],
) -> List[float]:
    """Synthesize a prompt-cache hit ratio (0-1) series.

    Stable, high-volume workloads typically have higher cache match rates
    (system prompts and retrieval contexts repeat). Bursty/low workloads see
    lower rates. We derive a baseline from throttling stability and TPM scale.
    """
    # Baseline: stable, high-volume workloads cache better.
    if config.tpm_mean >= 80_000 and config.throttling_rate <= 0.05:
        baseline = 0.45
    elif config.tpm_mean >= 30_000:
        baseline = 0.32
    else:
        baseline = 0.18

    series: List[float] = []
    for ts in timestamps:
        # Daily seasonality: business hours have higher cache reuse.
        hour_factor = 1.0 + 0.15 * np.sin((ts.hour - 6) / 24.0 * 2 * np.pi)
        noise = np.random.normal(0, 0.04)
        val = baseline * hour_factor + noise
        series.append(float(max(0.0, min(0.95, val))))
    return series


def display_scenario_info(config: ScenarioConfig) -> None:
    """Display scenario information to the user."""
    console.print()
    console.print(
        Panel(
            f"[bold]{config.name}[/bold]\n\n{config.description}",
            title="📋 Demo Scenario",
            border_style="blue",
        )
    )


def display_fetched_metrics(metrics: DeploymentMetrics, config: ScenarioConfig) -> None:
    """Display the 'fetched' metrics to the user in a detailed format."""
    console.print()
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print(
        "[bold cyan]                    FETCHED DEPLOYMENT DATA                     [/bold cyan]"
    )
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print()

    # Deployment Info
    info_table = Table(title="🔧 Deployment Information", show_header=False, box=None)
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Deployment Name", metrics.deployment_name)
    info_table.add_row("Model", metrics.model_name)
    info_table.add_row(
        "Analysis Period",
        f"{metrics.start_time.strftime('%b %d')} - {metrics.end_time.strftime('%b %d, %Y')}",
    )
    info_table.add_row("Data Points Collected", f"{len(metrics.timestamps):,} hourly samples")
    info_table.add_row("SKU Type", "Standard (PAYG)")

    console.print(info_table)
    console.print()

    # Request Metrics
    req_table = Table(title="📊 Request Metrics", box=None)
    req_table.add_column("Metric", style="cyan")
    req_table.add_column("Value", style="white", justify="right")
    req_table.add_column("", style="dim")

    total_requests = metrics.total_requests
    throttled_total = metrics.throttled_requests.total if metrics.throttled_requests else 0
    throttling_rate = metrics.throttling_rate

    req_table.add_row(
        "Total Requests Analyzed",
        f"{total_requests:,.0f}",
        f"over {len(metrics.timestamps) // 24} days",
    )
    req_table.add_row("Average Requests/Hour", f"{config.avg_requests_per_hour:,.0f}", "")
    req_table.add_row("Peak Requests/Hour", f"{metrics.requests_per_minute.max * 60:,.0f}", "")
    req_table.add_row(
        "Successful Requests",
        f"{metrics.successful_requests.total:,.0f}",
        f"({(1 - throttling_rate) * 100:.1f}%)",
    )
    req_table.add_row(
        "Throttled Requests (429s)",
        f"{throttled_total:,.0f}",
        f"[{'red' if throttling_rate > 0.03 else 'green'}]({throttling_rate * 100:.2f}%)[/]",
    )

    console.print(req_table)
    console.print()

    # Token Metrics
    token_table = Table(title="🔤 Token Metrics", box=None)
    token_table.add_column("Metric", style="cyan")
    token_table.add_column("Value", style="white", justify="right")
    token_table.add_column("", style="dim")

    tpm = metrics.tokens_per_minute
    token_table.add_row("Average TPM", f"{tpm.mean:,.0f}", "tokens per minute")
    token_table.add_row("Peak TPM", f"{tpm.max:,.0f}", "maximum observed")
    token_table.add_row("TPM Std Deviation", f"{tpm.std:,.0f}", f"(CV: {tpm.cv:.2f})")
    token_table.add_row("Total Tokens Processed", f"{tpm.total:,.0f}", "")
    token_table.add_row("Avg Tokens/Request", f"{metrics.avg_tokens_per_request:,.0f}", "")

    if metrics.prompt_tokens and metrics.completion_tokens:
        prompt_total = metrics.prompt_tokens.total
        completion_total = metrics.completion_tokens.total
        ratio = (
            prompt_total / (prompt_total + completion_total)
            if (prompt_total + completion_total) > 0
            else 0
        )
        token_table.add_row("Prompt/Completion Ratio", f"{ratio:.0%} / {1 - ratio:.0%}", "")

    console.print(token_table)
    console.print()

    # Latency Metrics
    lat_table = Table(title="⏱️ Latency Metrics (Time to First Byte)", box=None)
    lat_table.add_column("Percentile", style="cyan")
    lat_table.add_column("Avg (ms)", style="white", justify="right")
    lat_table.add_column("Min (ms)", style="dim", justify="right")
    lat_table.add_column("Max (ms)", style="dim", justify="right")
    lat_table.add_column("Assessment", style="white")

    p50 = metrics.time_to_first_byte_p50
    p95 = metrics.time_to_first_byte_p95
    p99 = metrics.time_to_first_byte_p99

    lat_table.add_row(
        "P50 (Median)",
        f"{p50.mean:,.0f}",
        f"{p50.min:,.0f}",
        f"{p50.max:,.0f}",
        "[green]Good[/]" if p50.mean < 500 else "[yellow]Moderate[/]",
    )
    lat_table.add_row(
        "P95",
        f"{p95.mean:,.0f}",
        f"{p95.min:,.0f}",
        f"{p95.max:,.0f}",
        "[green]Good[/]"
        if p95.mean < 2000
        else "[yellow]Elevated[/]"
        if p95.mean < 5000
        else "[red]High[/]",
    )
    lat_table.add_row(
        "P99",
        f"{p99.mean:,.0f}",
        f"{p99.min:,.0f}",
        f"{p99.max:,.0f}",
        "[green]Good[/]"
        if p99.mean < 3000
        else "[yellow]Elevated[/]"
        if p99.mean < 6000
        else "[red]High[/]",
    )

    variance_ratio = p99.mean / p50.mean if p50.mean > 0 else 0
    lat_table.add_row(
        "Variance (P99/P50)",
        f"{variance_ratio:.1f}x",
        "",
        "",
        "[green]Stable[/]"
        if variance_ratio < 3
        else "[yellow]Variable[/]"
        if variance_ratio < 5
        else "[red]Unstable[/]",
    )

    console.print(lat_table)
    console.print()

    # Usage Patterns
    pattern_table = Table(title="📈 Usage Patterns", box=None)
    pattern_table.add_column("Pattern", style="cyan")
    pattern_table.add_column("Observation", style="white")

    # Calculate active hours
    rpm = metrics.requests_per_minute
    active_pct = 1.0 - rpm.zero_percentage

    pattern_table.add_row("Active Time", f"{active_pct:.0%} of hours had traffic")
    pattern_table.add_row(
        "Peak Hours",
        "10 AM - 4 PM (business hours)" if active_pct > 0.5 else "Sporadic throughout day",
    )
    pattern_table.add_row(
        "Weekend Traffic", "~60% of weekday volume" if active_pct > 0.5 else "Minimal"
    )
    pattern_table.add_row(
        "Daily Pattern",
        f"{'Consistent' if config.daily_pattern_consistency > 0.7 else 'Variable' if config.daily_pattern_consistency > 0.4 else 'Unpredictable'} day-over-day",
    )

    console.print(pattern_table)
    console.print()

    # Capacity Utilization
    cap_table = Table(title="🎯 Capacity Indicators", box=None)
    cap_table.add_column("Indicator", style="cyan")
    cap_table.add_column("Status", style="white")
    cap_table.add_column("Implication", style="dim")

    cap_table.add_row(
        "Throttling Rate",
        f"[{'red' if throttling_rate > 0.05 else 'yellow' if throttling_rate > 0.01 else 'green'}]{throttling_rate:.1%}[/]",
        "PAYG capacity limit reached"
        if throttling_rate > 0.05
        else "Within capacity"
        if throttling_rate < 0.01
        else "Occasional limits",
    )
    cap_table.add_row(
        "Utilization Level",
        f"{config.utilization_pct:.0%}",
        "Near ceiling"
        if config.utilization_pct > 0.8
        else "Moderate"
        if config.utilization_pct > 0.5
        else "Low",
    )
    cap_table.add_row(
        "Burst Behavior",
        "Frequent spikes detected" if config.tpm_spikes else "Steady throughput",
        "May need headroom" if config.tpm_spikes else "Predictable capacity needs",
    )

    console.print(cap_table)
    console.print()

    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print()


def get_demo_deployment_info(scenario: DemoScenario) -> DeploymentInfo:
    """Get deployment info for a demo scenario."""
    config = SCENARIOS[scenario]
    return DeploymentInfo(
        name=config.deployment_name,
        model=config.model_name,
        sku_type="Standard",
        sku_capacity=None,
    )


def list_demo_scenarios() -> None:
    """Display available demo scenarios."""
    console.print()
    console.print("[bold]Available Demo Scenarios:[/bold]")
    console.print()

    for scenario_enum, config in SCENARIOS.items():
        emoji = {
            DemoScenario.PTU_RECOMMENDED: "✅",
            DemoScenario.PTU_NOT_RECOMMENDED: "❌",
            DemoScenario.BORDERLINE: "⚠️",
        }.get(scenario_enum, "")

        console.print(f"  {emoji} [cyan]{scenario_enum.value}[/cyan]")
        console.print(f"     {config.name}")
        console.print(f"     [dim]{config.description[:80]}...[/dim]")
        console.print()
