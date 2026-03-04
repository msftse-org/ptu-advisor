"""Configuration and threshold settings for PTU Advisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ThresholdConfig:
    """Configurable thresholds for the decision engine.
    
    These thresholds are based on Microsoft's PTU guidance and
    real-world CSA experience. They can be tuned per-organization.
    """

    # Workload Shape thresholds
    # Coefficient of variation (std/mean) for TPM/RPM
    tpm_cv_stable_threshold: float = 0.3  # Below this = stable
    tpm_cv_spiky_threshold: float = 0.7   # Above this = spiky
    
    # Prompt/completion ratio consistency
    token_ratio_variance_threshold: float = 0.25

    # Capacity Pressure thresholds
    # Throttling rate (429s / total requests)
    throttling_rate_low: float = 0.01     # <1% = low pressure
    throttling_rate_high: float = 0.05    # >5% = high pressure
    
    # TPM utilization (actual vs theoretical max)
    tpm_utilization_ceiling: float = 0.85  # >85% = hitting ceiling

    # Latency Sensitivity thresholds (in milliseconds)
    p95_latency_good: float = 2000.0      # <2s = good
    p95_latency_poor: float = 5000.0      # >5s = poor
    
    # Latency variance (P99/P50 ratio)
    latency_variance_stable: float = 2.0   # P99 < 2x P50 = stable
    latency_variance_unstable: float = 4.0  # P99 > 4x P50 = unstable

    # Load Predictability thresholds
    # Percentage of business hours with sustained traffic
    sustained_traffic_threshold: float = 0.6  # >60% = sustained
    
    # Day-over-day similarity (correlation coefficient)
    day_similarity_threshold: float = 0.7  # >0.7 = predictable

    # Decision thresholds
    # Minimum positive dimensions for PTU recommendation
    min_positive_for_ptu: int = 3
    min_positive_for_borderline: int = 2
    
    # Minimum data points required for confident recommendation
    min_data_points: int = 100
    min_days_for_confidence: int = 3


@dataclass
class ModelCapacityConfig:
    """Known PAYG TPM quotas and PTU specs per model."""

    payg_tpm_quota: int
    input_tpm_per_ptu: int
    output_ratio: int
    global_min_ptu: int
    global_increment: int
    regional_min_ptu: int
    regional_increment: int


# Known model capacity configurations (as of January 2026)
# Source: https://learn.microsoft.com/azure/ai-services/openai/quotas-limits
MODEL_CAPACITY_CONFIGS: Dict[str, ModelCapacityConfig] = {
    "gpt-5": ModelCapacityConfig(450_000, 3400, 8, 15, 5, 50, 50),
    "gpt-4.1": ModelCapacityConfig(720_000, 4750, 4, 15, 5, 50, 50),
    "gpt-4.1-mini": ModelCapacityConfig(2_000_000, 23750, 4, 15, 5, 25, 25),
    "gpt-4.1-nano": ModelCapacityConfig(4_000_000, 59400, 4, 15, 5, 25, 25),
    "gpt-4o": ModelCapacityConfig(450_000, 2500, 3, 15, 5, 50, 50),
    "gpt-4o-mini": ModelCapacityConfig(2_000_000, 37000, 3, 15, 5, 25, 25),
    "o1": ModelCapacityConfig(450_000, 3000, 4, 15, 5, 50, 50),
    "o3-mini": ModelCapacityConfig(2_000_000, 14900, 4, 15, 5, 25, 25),
    "o4-mini": ModelCapacityConfig(2_000_000, 5400, 4, 15, 5, 25, 25),
}


def get_model_config(model_name: str) -> Optional[ModelCapacityConfig]:
    """Look up model capacity config by model name (longest match first).

    Keys are sorted longest-first so that e.g. 'gpt-4o-mini' is matched
    before 'gpt-4o', and 'gpt-4.1-nano' before 'gpt-4.1'.
    """
    model_lower = model_name.lower()
    for key in sorted(MODEL_CAPACITY_CONFIGS, key=len, reverse=True):
        if key in model_lower:
            return MODEL_CAPACITY_CONFIGS[key]
    return None


@dataclass
class BusinessHoursConfig:
    """Configuration for business hours analysis."""
    
    start_hour: int = 9   # 9 AM
    end_hour: int = 18    # 6 PM
    timezone: str = "UTC"
    weekdays_only: bool = True  # Monday-Friday only


@dataclass
class AnalysisConfig:
    """Main configuration for analysis runs."""
    
    # Required Azure resource identifiers
    resource_group: str
    workspace: str
    deployment: str = ""  # Empty = aggregate all deployments in account
    
    # Optional Azure settings
    subscription_id: Optional[str] = None
    
    # Analysis parameters
    lookback_days: int = 14
    business_hours_only: bool = False
    
    # Granularity for metric aggregation
    aggregation_interval_minutes: int = 60  # Hourly buckets
    
    # Output settings
    verbose: bool = False
    
    # LLM enrichment
    enable_llm: bool = False
    llm_provider: str = "mock"  # "azure", "openai", "mock"

    # Nested configs
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    business_hours: BusinessHoursConfig = field(default_factory=BusinessHoursConfig)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be at least 1")
        if self.lookback_days > 90:
            raise ValueError("lookback_days cannot exceed 90")
        if self.aggregation_interval_minutes not in [5, 15, 30, 60]:
            raise ValueError("aggregation_interval_minutes must be 5, 15, 30, or 60")


# Default configuration instance
DEFAULT_CONFIG = AnalysisConfig(
    resource_group="",
    workspace="",
    deployment="",
)
