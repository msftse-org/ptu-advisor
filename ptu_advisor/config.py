"""Configuration and threshold settings for PTU Advisor."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
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
    tpm_cv_spiky_threshold: float = 0.7  # Above this = spiky

    # Prompt/completion ratio consistency
    token_ratio_variance_threshold: float = 0.25

    # Capacity Pressure thresholds
    # Throttling rate (429s / total requests)
    throttling_rate_low: float = 0.01  # <1% = low pressure
    throttling_rate_high: float = 0.05  # >5% = high pressure

    # TPM utilization (actual vs theoretical max)
    tpm_utilization_ceiling: float = 0.85  # >85% = hitting ceiling

    # Latency Sensitivity thresholds (in milliseconds)
    p95_latency_good: float = 2000.0  # <2s = good
    p95_latency_poor: float = 5000.0  # >5s = poor

    # Latency variance (P99/P50 ratio)
    latency_variance_stable: float = 2.0  # P99 < 2x P50 = stable
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


# Model capacity configurations from Microsoft Foundry provisioned-throughput
# sizing documentation (verified July 2026).
MODEL_CAPACITY_CONFIGS: Dict[str, ModelCapacityConfig] = {
    "gpt-5.5": ModelCapacityConfig(450_000, 1200, 6, 15, 5, 50, 50),
    "gpt-5.4-mini": ModelCapacityConfig(450_000, 7900, 6, 15, 5, 25, 25),
    "gpt-5.4": ModelCapacityConfig(450_000, 2400, 6, 15, 5, 50, 50),
    "gpt-5.3-codex": ModelCapacityConfig(450_000, 3400, 8, 15, 5, 50, 50),
    "gpt-5.2-codex": ModelCapacityConfig(450_000, 3400, 8, 15, 5, 50, 50),
    "gpt-5.2": ModelCapacityConfig(450_000, 3400, 8, 15, 5, 50, 50),
    "gpt-5.1-codex": ModelCapacityConfig(450_000, 4750, 8, 15, 5, 50, 50),
    "gpt-5.1": ModelCapacityConfig(450_000, 4750, 8, 15, 5, 50, 50),
    "gpt-5-mini": ModelCapacityConfig(450_000, 23750, 8, 15, 5, 25, 25),
    "gpt-5": ModelCapacityConfig(450_000, 4750, 8, 15, 5, 50, 50),
    "gpt-4.1": ModelCapacityConfig(720_000, 3000, 4, 15, 5, 50, 50),
    "gpt-4.1-mini": ModelCapacityConfig(2_000_000, 14900, 4, 15, 5, 25, 25),
    "gpt-4.1-nano": ModelCapacityConfig(4_000_000, 59400, 4, 15, 5, 25, 25),
    "gpt-4o": ModelCapacityConfig(450_000, 2500, 4, 15, 5, 50, 50),
    "gpt-4o-mini": ModelCapacityConfig(2_000_000, 37000, 4, 15, 5, 25, 25),
    "o1": ModelCapacityConfig(450_000, 230, 4, 15, 5, 25, 50),
    "o3-mini": ModelCapacityConfig(2_000_000, 2500, 4, 15, 5, 25, 25),
    "o4-mini": ModelCapacityConfig(2_000_000, 5400, 4, 15, 5, 25, 25),
}


def get_model_config(model_name: str) -> Optional[ModelCapacityConfig]:
    """Look up model capacity config by model name (longest match first).

    Keys are sorted longest-first so that e.g. 'gpt-4o-mini' is matched
    before 'gpt-4o', and 'gpt-4.1-nano' before 'gpt-4.1'.
    """
    model_lower = model_name.lower()
    for key in sorted(MODEL_CAPACITY_CONFIGS, key=len, reverse=True):
        if key == "gpt-5" and re.search(r"gpt-5\.\d", model_lower):
            continue
        if key in model_lower:
            return MODEL_CAPACITY_CONFIGS[key]
    return None


# ---------------------------------------------------------------------------
# Model family classification (Phase 2 — PTU eligibility UX)
# ---------------------------------------------------------------------------

# Maps model name substrings to human-readable family labels.
# Sorted longest-first at lookup time so "gpt-4o-mini" matches before "gpt-4o".
MODEL_FAMILIES: Dict[str, str] = {
    "gpt-5": "GPT-5",
    "gpt-4.1-nano": "GPT-4.1 Nano",
    "gpt-4.1-mini": "GPT-4.1 Mini",
    "gpt-4.1": "GPT-4.1",
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4o": "GPT-4o",
    "o4-mini": "o4-mini",
    "o3-mini": "o3-mini",
    "o1": "o1",
    "text-embedding": "Embedding",
    "dall-e": "DALL-E",
    "whisper": "Whisper",
    "tts": "TTS",
    "gpt-3.5": "GPT-3.5 (Legacy)",
}


# Model-specific reasons for PTU ineligibility.
INELIGIBILITY_REASONS: Dict[str, str] = {
    "Embedding": (
        "Embedding models use a fixed per-token pricing model and don't have "
        "PTU provisioned capacity."
    ),
    "DALL-E": (
        "Image generation models bill per image and don't support "
        "token-based provisioned throughput."
    ),
    "Whisper": (
        "Audio models bill per minute of audio and don't support "
        "token-based provisioned throughput."
    ),
    "TTS": (
        "Audio models bill per character of input and don't support "
        "token-based provisioned throughput."
    ),
    "GPT-3.5 (Legacy)": (
        "GPT-3.5 Turbo has been retired from PTU provisioning. Consider "
        "upgrading to GPT-4o-mini for similar performance with PTU support."
    ),
}

DEFAULT_INELIGIBILITY_REASON: str = (
    "This model does not support Provisioned Throughput Units. "
    "PTU is available for select Azure OpenAI chat and reasoning models."
)


def get_model_family(model_name: str) -> str:
    """Classify a model name into a human-readable family label.

    Uses the same longest-match-first approach as get_model_config().
    Returns "Other" for unrecognized models.
    """
    model_lower = model_name.lower()
    for key in sorted(MODEL_FAMILIES, key=len, reverse=True):
        if key in model_lower:
            return MODEL_FAMILIES[key]
    return "Other"


def get_ineligibility_reason(model_family: str) -> str:
    """Return a human-readable explanation of why a model family is not PTU-eligible."""
    return INELIGIBILITY_REASONS.get(model_family, DEFAULT_INELIGIBILITY_REASON)


@dataclass
class BusinessHoursConfig:
    """Configuration for business hours analysis."""

    start_hour: int = 9  # 9 AM
    end_hour: int = 18  # 6 PM
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
    aggregation_interval_minutes: int = 5  # 5-minute buckets

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
        if self.aggregation_interval_minutes not in [1, 5, 15, 30, 60]:
            raise ValueError("aggregation_interval_minutes must be 1, 5, 15, 30, or 60")


# Default configuration instance
DEFAULT_CONFIG = AnalysisConfig(
    resource_group="",
    workspace="",
    deployment="",
)
