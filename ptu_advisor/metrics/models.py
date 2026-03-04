"""Data models for metrics and analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np


class MetricName(str, Enum):
    """Available metrics from Azure Monitor for Foundry deployments.

    Metric names sourced from Azure Monitor metric definitions API for
    Microsoft.CognitiveServices/accounts resources (verified Feb 2026).
    """

    # Request metrics
    REQUESTS = "AzureOpenAIRequests"
    SUCCESSFUL_REQUESTS = "SuccessfulCalls"
    THROTTLED_REQUESTS = "Ratelimit"  # ⚠️  Platform metric — reports rate-limit
    # *token* counts, NOT request counts.  Do NOT use directly for 429s.
    # Use AzureOpenAIRequests + StatusCode eq '429' instead (see collector).
    TOTAL_CALLS = "TotalCalls"        # All calls (success + error + throttled)

    # Token metrics
    PROMPT_TOKENS = "ProcessedPromptTokens"  # was "PromptTokens" (old name)
    COMPLETION_TOKENS = "GeneratedTokens"
    TOTAL_TOKENS = "TotalTokens"             # was "ProcessedTokens" (old name)
    TOKENS_PER_MINUTE = TOTAL_TOKENS          # backward-compatible alias
    INPUT_TOKENS = "InputTokens"             # model-level input tokens
    OUTPUT_TOKENS = "OutputTokens"           # model-level output tokens

    # Latency metrics
    TIME_TO_FIRST_BYTE = "AzureOpenAITimeToResponse"  # First token latency
    TIME_TO_LAST_BYTE = "AzureOpenAITTLTInMS"          # Full response latency (ms)

    # PTU-specific metrics
    PTU_UTILIZATION = "AzureOpenAIProvisionedManagedUtilizationV2"


class AggregationType(str, Enum):
    """Aggregation types for metrics."""
    
    TOTAL = "Total"
    AVERAGE = "Average"
    MINIMUM = "Minimum"
    MAXIMUM = "Maximum"
    COUNT = "Count"


@dataclass
class TimeSeries:
    """A time series of metric values."""
    
    timestamps: List[datetime]
    values: List[float]
    metric_name: str
    unit: str = ""
    
    def __len__(self) -> int:
        return len(self.values)
    
    @property
    def mean(self) -> float:
        """Calculate mean of values."""
        if not self.values:
            return 0.0
        return float(np.mean(self.values))
    
    @property
    def std(self) -> float:
        """Calculate standard deviation of values."""
        if not self.values:
            return 0.0
        return float(np.std(self.values))
    
    @property
    def cv(self) -> float:
        """Calculate coefficient of variation (std/mean)."""
        if self.mean == 0:
            return 0.0
        return self.std / self.mean
    
    @property
    def min(self) -> float:
        """Get minimum value."""
        if not self.values:
            return 0.0
        return float(np.min(self.values))
    
    @property
    def max(self) -> float:
        """Get maximum value."""
        if not self.values:
            return 0.0
        return float(np.max(self.values))
    
    def percentile(self, p: float) -> float:
        """Calculate percentile of values."""
        if not self.values:
            return 0.0
        return float(np.percentile(self.values, p))
    
    @property
    def p50(self) -> float:
        """Get 50th percentile (median)."""
        return self.percentile(50)
    
    @property
    def p95(self) -> float:
        """Get 95th percentile."""
        return self.percentile(95)
    
    @property
    def p99(self) -> float:
        """Get 99th percentile."""
        return self.percentile(99)
    
    @property
    def total(self) -> float:
        """Get sum of all values."""
        return float(np.sum(self.values))
    
    @property
    def non_zero_count(self) -> int:
        """Count of non-zero values."""
        return int(np.count_nonzero(self.values))
    
    @property
    def zero_percentage(self) -> float:
        """Percentage of zero values (idle periods)."""
        if not self.values:
            return 0.0
        return (len(self.values) - self.non_zero_count) / len(self.values)
    
    # =========================================================================
    # Utilization Pattern Metrics (for PTU sizing)
    # =========================================================================
    
    def hourly_distribution(self) -> Dict[int, float]:
        """
        Get average utilization by hour of day (0-23).
        
        This shows which hours have high vs low usage, critical for PTU sizing
        since PTU is cost-effective when utilization is consistent across hours.
        
        Returns:
            Dict mapping hour (0-23) to average value for that hour.
        """
        hourly: Dict[int, List[float]] = {h: [] for h in range(24)}
        
        for ts, val in zip(self.timestamps, self.values):
            hourly[ts.hour].append(val)
        
        return {
            hour: float(np.mean(values)) if values else 0.0
            for hour, values in hourly.items()
        }
    
    def weekly_distribution(self) -> Dict[int, float]:
        """
        Get average utilization by day of week (0=Monday, 6=Sunday).
        
        This shows which days have high vs low usage, important for understanding
        whether weekend usage justifies always-on PTU capacity.
        
        Returns:
            Dict mapping weekday (0-6) to average value for that day.
        """
        daily: Dict[int, List[float]] = {d: [] for d in range(7)}
        
        for ts, val in zip(self.timestamps, self.values):
            daily[ts.weekday()].append(val)
        
        return {
            day: float(np.mean(values)) if values else 0.0
            for day, values in daily.items()
        }
    
    @property
    def peak_to_average_ratio(self) -> float:
        """
        Calculate peak-to-average ratio (PAR).
        
        Formula: PAR = P95 / Mean
        
        A ratio > 2.0 indicates spiky workloads that may not benefit from PTU.
        A ratio < 1.5 indicates stable workloads ideal for PTU.
        
        Returns:
            Peak-to-average ratio. Values closer to 1.0 indicate more stable workloads.
        """
        if self.mean == 0:
            return 0.0
        return self.p95 / self.mean
    
    def sustained_utilization_rate(self, threshold_pct: float = 0.3) -> float:
        """
        Calculate percentage of time utilization is above a threshold.
        
        Formula: Sustained Rate = (Hours above threshold) / (Total Hours) × 100
        
        A threshold of 30% of peak is commonly used. If sustained rate > 60%,
        PTU is typically cost-effective.
        
        Args:
            threshold_pct: The threshold as a fraction of the max value (default 0.3 = 30%)
            
        Returns:
            Percentage of time (0-100) that utilization exceeded the threshold.
        """
        if not self.values:
            return 0.0

        if self.max == 0:
            return 0.0
        
        threshold = self.max * threshold_pct
        above_threshold = sum(1 for v in self.values if v >= threshold)
        
        return (above_threshold / len(self.values)) * 100
    
    @property
    def active_hours_percentage(self) -> float:
        """
        Calculate percentage of hours with meaningful activity.
        
        "Meaningful activity" is defined as > 10% of the average.
        
        Formula: Active % = (Hours with activity > 10% of mean) / (Total Hours) × 100
        
        High active hours % (> 70%) indicates consistent usage suitable for PTU.
        Low active hours % (< 40%) indicates sparse usage better for PAYG.
        
        Returns:
            Percentage of hours with meaningful activity (0-100).
        """
        if not self.values or self.mean == 0:
            return 0.0
        
        threshold = self.mean * 0.1  # 10% of mean
        active = sum(1 for v in self.values if v > threshold)
        
        return (active / len(self.values)) * 100
    
    @property
    def business_hours_concentration(self) -> float:
        """
        Calculate what percentage of total usage occurs during business hours (9-18).
        
        Formula: Concentration = (Sum during 9-18) / (Total Sum) × 100
        
        High concentration (> 70%) indicates usage is heavily weighted to business hours.
        Low concentration (< 50%) indicates usage is spread across 24 hours.
        
        Returns:
            Percentage of total usage during business hours (0-100).
        """
        if not self.values:
            return 0.0
        
        business_hours_sum = sum(
            val for ts, val in zip(self.timestamps, self.values)
            if 9 <= ts.hour <= 18
        )
        total_sum = sum(self.values)
        
        if total_sum == 0:
            return 0.0
        
        return (business_hours_sum / total_sum) * 100
    
    @property
    def weekend_vs_weekday_ratio(self) -> float:
        """
        Calculate the ratio of weekend to weekday average usage.
        
        Formula: Ratio = (Weekend Avg) / (Weekday Avg)
        
        A ratio close to 1.0 indicates consistent usage throughout the week.
        A ratio < 0.3 indicates weekends are much quieter than weekdays.
        
        Returns:
            Ratio of weekend to weekday average usage.
        """
        weekend_values = []
        weekday_values = []
        
        for ts, val in zip(self.timestamps, self.values):
            if ts.weekday() >= 5:  # Saturday = 5, Sunday = 6
                weekend_values.append(val)
            else:
                weekday_values.append(val)
        
        weekend_avg = float(np.mean(weekend_values)) if weekend_values else 0.0
        weekday_avg = float(np.mean(weekday_values)) if weekday_values else 0.0
        
        if weekday_avg == 0:
            return 0.0
        
        return weekend_avg / weekday_avg


@dataclass
class DeploymentMetrics:
    """All collected metrics for a deployment."""
    
    # Metadata
    deployment_name: str
    model_name: str
    start_time: datetime
    end_time: datetime
    
    # Time axis
    timestamps: List[datetime] = field(default_factory=list)
    
    # Request metrics
    requests_per_minute: Optional[TimeSeries] = None
    successful_requests: Optional[TimeSeries] = None
    throttled_requests: Optional[TimeSeries] = None
    
    # Token metrics
    prompt_tokens: Optional[TimeSeries] = None
    completion_tokens: Optional[TimeSeries] = None
    tokens_per_minute: Optional[TimeSeries] = None
    
    # Latency metrics (in milliseconds)
    time_to_first_byte_p50: Optional[TimeSeries] = None
    time_to_first_byte_p95: Optional[TimeSeries] = None
    time_to_first_byte_p99: Optional[TimeSeries] = None
    
    # PTU metrics
    ptu_utilization: Optional[TimeSeries] = None

    # Deployment metadata (populated by collector or demo)
    deployment_info: Optional["DeploymentInfo"] = None

    def filter_business_hours(
        self,
        start_hour: int = 9,
        end_hour: int = 18,
        weekdays_only: bool = True,
    ) -> "DeploymentMetrics":
        """Return a new DeploymentMetrics filtered to business hours only."""
        indices = []
        for i, ts in enumerate(self.timestamps):
            if weekdays_only and ts.weekday() >= 5:
                continue
            if start_hour <= ts.hour < end_hour:
                indices.append(i)

        if not indices:
            import warnings
            warnings.warn(
                "No data points matched business hours filter. "
                "Returning unfiltered data.",
                stacklevel=2,
            )
            return self

        def _filter_ts(ts: Optional[TimeSeries]) -> Optional[TimeSeries]:
            if ts is None:
                return None
            return TimeSeries(
                timestamps=[ts.timestamps[i] for i in indices],
                values=[ts.values[i] for i in indices],
                metric_name=ts.metric_name,
                unit=ts.unit,
            )

        return DeploymentMetrics(
            deployment_name=self.deployment_name,
            model_name=self.model_name,
            start_time=self.start_time,
            end_time=self.end_time,
            timestamps=[self.timestamps[i] for i in indices],
            requests_per_minute=_filter_ts(self.requests_per_minute),
            successful_requests=_filter_ts(self.successful_requests),
            throttled_requests=_filter_ts(self.throttled_requests),
            prompt_tokens=_filter_ts(self.prompt_tokens),
            completion_tokens=_filter_ts(self.completion_tokens),
            tokens_per_minute=_filter_ts(self.tokens_per_minute),
            time_to_first_byte_p50=_filter_ts(self.time_to_first_byte_p50),
            time_to_first_byte_p95=_filter_ts(self.time_to_first_byte_p95),
            time_to_first_byte_p99=_filter_ts(self.time_to_first_byte_p99),
            ptu_utilization=_filter_ts(self.ptu_utilization),
            deployment_info=self.deployment_info,
        )

    @property
    def total_requests(self) -> int:
        """Total number of requests in the analysis period."""
        successful = int(self.successful_requests.total) if self.successful_requests else 0
        throttled = int(self.throttled_requests.total) if self.throttled_requests else 0
        total = successful + throttled
        # Fall back to sum of RPM if explicit counts are unavailable
        if total == 0 and self.requests_per_minute:
            return int(self.requests_per_minute.total)
        return total
    
    @property
    def throttling_rate(self) -> float:
        """Percentage of requests that were throttled."""
        if not self.throttled_requests or not self.successful_requests:
            return 0.0
        
        throttled = self.throttled_requests.total
        successful = self.successful_requests.total
        total = throttled + successful
        
        if total == 0:
            return 0.0
        
        return throttled / total
    
    @property
    def avg_tokens_per_request(self) -> float:
        """Average tokens per request."""
        if not self.tokens_per_minute or not self.requests_per_minute:
            return 0.0
        
        total_tokens = self.tokens_per_minute.total
        total_requests = self.requests_per_minute.total
        
        if total_requests == 0:
            return 0.0
        
        return total_tokens / total_requests


@dataclass
class DeploymentInfo:
    """Basic information about a Foundry deployment."""
    
    name: str
    model: str
    sku_type: str  # "Standard" or "ProvisionedManaged"
    sku_capacity: Optional[int] = None
    created_date: Optional[datetime] = None


class DimensionScore(str, Enum):
    """Score for a single analysis dimension."""
    
    POSITIVE = "positive"       # Favors PTU
    NEUTRAL = "neutral"         # Neither favors nor disfavors
    NEGATIVE = "negative"       # Disfavors PTU
    INSUFFICIENT = "insufficient"  # Not enough data


@dataclass
class DimensionResult:
    """Result of analyzing a single dimension."""
    
    name: str
    score: DimensionScore
    confidence: float  # 0.0 to 1.0
    summary: str       # One-line summary
    explanation: str   # Detailed explanation
    key_metrics: Dict[str, float] = field(default_factory=dict)
    
    @property
    def is_positive(self) -> bool:
        """Check if this dimension favors PTU."""
        return self.score == DimensionScore.POSITIVE


@dataclass
class DimensionScores:
    """Scores for all four analysis dimensions."""
    
    workload_shape: DimensionResult
    capacity_pressure: DimensionResult
    latency_sensitivity: DimensionResult
    load_predictability: DimensionResult
    
    @property
    def all_dimensions(self) -> List[DimensionResult]:
        """Get all dimension results as a list."""
        return [
            self.workload_shape,
            self.capacity_pressure,
            self.latency_sensitivity,
            self.load_predictability,
        ]
    
    @property
    def positive_count(self) -> int:
        """Count of positive dimensions."""
        return sum(1 for d in self.all_dimensions if d.is_positive)
    
    @property
    def average_confidence(self) -> float:
        """Average confidence across all dimensions."""
        if not self.all_dimensions:
            return 0.0
        return sum(d.confidence for d in self.all_dimensions) / len(self.all_dimensions)


class Recommendation(str, Enum):
    """Final PTU recommendation."""
    
    PTU_RECOMMENDED = "ptu_recommended"
    BORDERLINE = "borderline"
    PTU_NOT_RECOMMENDED = "ptu_not_recommended"


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    
    # The recommendation
    recommendation: Recommendation
    
    # Dimension scores
    dimensions: DimensionScores
    
    # Confidence level (0.0 to 1.0)
    confidence: float
    
    # Human-readable summaries
    summary: str           # One-sentence verdict
    explanation: str       # Detailed explanation
    what_would_change: str # What would change the recommendation
    
    # Raw data for transparency
    data_quality: str      # Description of data quality
    analysis_period: str   # e.g., "14 days (Jan 10 - Jan 24, 2026)"

    # Optional cost estimate (populated by engine/report)
    cost_estimate: Optional[Dict[str, Any]] = None

    @property
    def recommendation_emoji(self) -> str:
        """Get emoji for the recommendation."""
        return {
            Recommendation.PTU_RECOMMENDED: "✅",
            Recommendation.BORDERLINE: "⚠️",
            Recommendation.PTU_NOT_RECOMMENDED: "❌",
        }.get(self.recommendation, "")
