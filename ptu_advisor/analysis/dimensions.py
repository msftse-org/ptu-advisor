"""Analysis dimension implementations for PTU recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ptu_advisor.config import AnalysisConfig, ThresholdConfig, get_model_config
from ptu_advisor.metrics.models import (
    DeploymentMetrics,
    DimensionResult,
    DimensionScore,
    TimeSeries,
)


class DimensionAnalyzer:
    """Base class for dimension analyzers."""
    
    def __init__(self, config: AnalysisConfig) -> None:
        self.config = config
        self.thresholds = config.thresholds
    
    def analyze(self, metrics: DeploymentMetrics) -> DimensionResult:
        """Analyze the dimension and return a result."""
        raise NotImplementedError


class WorkloadShapeAnalyzer(DimensionAnalyzer):
    """
    Analyzes workload shape for PTU suitability.
    
    Evaluates:
    - Variance in TPM/RPM (stability)
    - Prompt/completion token ratio consistency
    - Request size patterns
    
    PTU works best with predictable, consistent workloads.
    """
    
    DIMENSION_NAME = "Workload Shape"
    
    def analyze(self, metrics: DeploymentMetrics) -> DimensionResult:
        """Analyze workload shape patterns."""
        
        # Check if we have sufficient data
        if not metrics.tokens_per_minute or len(metrics.tokens_per_minute) < self.thresholds.min_data_points:
            return DimensionResult(
                name=self.DIMENSION_NAME,
                score=DimensionScore.INSUFFICIENT,
                confidence=0.0,
                summary="Insufficient data to analyze workload shape.",
                explanation="Need more data points to determine workload patterns.",
                key_metrics={},
            )
        
        # Calculate coefficient of variation for TPM
        tpm_cv = metrics.tokens_per_minute.cv
        
        # Calculate prompt/completion ratio variance if available
        token_ratio_cv = 0.0
        if metrics.prompt_tokens and metrics.completion_tokens:
            prompt_vals = np.array(metrics.prompt_tokens.values)
            completion_vals = np.array(metrics.completion_tokens.values)
            
            # Avoid division by zero
            with np.errstate(divide='ignore', invalid='ignore'):
                ratios = np.where(
                    completion_vals > 0,
                    prompt_vals / completion_vals,
                    0
                )
                ratios = ratios[~np.isnan(ratios) & ~np.isinf(ratios)]
                
            if len(ratios) > 0:
                token_ratio_cv = float(np.std(ratios) / np.mean(ratios)) if np.mean(ratios) > 0 else 0
        
        # Determine score
        if tpm_cv < self.thresholds.tpm_cv_stable_threshold:
            score = DimensionScore.POSITIVE
            summary = "Workload is stable and consistent."
            explanation = (
                f"Your token throughput shows low variability (CV={tpm_cv:.2f}), "
                f"indicating a consistent workload pattern. This is ideal for PTU, "
                f"which performs best with predictable usage. "
                f"Stable workloads avoid the waste of unused reserved capacity."
            )
        elif tpm_cv > self.thresholds.tpm_cv_spiky_threshold:
            score = DimensionScore.NEGATIVE
            summary = "Workload is highly variable/spiky."
            explanation = (
                f"Your token throughput shows high variability (CV={tpm_cv:.2f}), "
                f"indicating a spiky or unpredictable workload. PTU requires "
                f"consistent usage to be cost-effective. With high variance, "
                f"you'd either over-provision (wasting capacity) or under-provision "
                f"(still needing PAYG for spikes)."
            )
        else:
            score = DimensionScore.NEUTRAL
            summary = "Workload has moderate variability."
            explanation = (
                f"Your token throughput shows moderate variability (CV={tpm_cv:.2f}). "
                f"This falls between stable and spiky patterns. Consider whether "
                f"the variance is due to known business cycles (good for PTU) "
                f"or unpredictable bursts (less ideal for PTU)."
            )
        
        # Calculate confidence based on data quality
        confidence = min(1.0, len(metrics.tokens_per_minute) / 500)
        
        return DimensionResult(
            name=self.DIMENSION_NAME,
            score=score,
            confidence=confidence,
            summary=summary,
            explanation=explanation,
            key_metrics={
                "tpm_coefficient_of_variation": tpm_cv,
                "tpm_mean": metrics.tokens_per_minute.mean,
                "tpm_std": metrics.tokens_per_minute.std,
                "token_ratio_cv": token_ratio_cv,
            },
        )


class CapacityPressureAnalyzer(DimensionAnalyzer):
    """
    Analyzes capacity pressure indicators.
    
    Evaluates:
    - Throttling rate (429 errors)
    - TPM ceiling/utilization
    - Queue behavior indicators
    
    High pressure on PAYG capacity suggests PTU would help.
    """
    
    DIMENSION_NAME = "Capacity Pressure"
    
    def analyze(self, metrics: DeploymentMetrics) -> DimensionResult:
        """Analyze capacity pressure indicators."""
        
        # Calculate throttling rate
        throttling_rate = metrics.throttling_rate
        
        # Calculate TPM utilization against known PAYG limits where possible
        tpm_utilization = 0.0
        absolute_utilization = 0.0
        quota_source = "observed peak"
        model_config = get_model_config(metrics.model_name)

        if metrics.tokens_per_minute:
            avg_tpm = metrics.tokens_per_minute.mean
            p95_tpm = metrics.tokens_per_minute.p95

            if model_config and model_config.payg_tpm_quota > 0:
                # Use absolute quota from Azure documentation
                absolute_utilization = p95_tpm / model_config.payg_tpm_quota
                tpm_utilization = absolute_utilization
                quota_source = f"PAYG quota ({model_config.payg_tpm_quota:,} TPM)"
            else:
                # Fallback to relative utilization (observed peak as ceiling)
                max_tpm = metrics.tokens_per_minute.max
                if max_tpm > 0:
                    tpm_utilization = avg_tpm / max_tpm

        # Determine score using throttling rate and absolute utilization
        has_high_throttling = throttling_rate > self.thresholds.throttling_rate_high
        has_high_utilization = tpm_utilization > self.thresholds.tpm_utilization_ceiling
        has_low_throttling = throttling_rate < self.thresholds.throttling_rate_low

        if has_high_throttling or has_high_utilization:
            score = DimensionScore.POSITIVE
            summary = "High capacity pressure detected — hitting PAYG limits."
            explanation = (
                f"Your deployment shows signs of capacity pressure:\n"
                f"• Throttling rate: {throttling_rate:.1%} of requests\n"
                f"• Utilization: {tpm_utilization:.1%} of {quota_source}\n\n"
                f"This indicates you're hitting PAYG capacity limits. PTU would "
                f"provide dedicated capacity with guaranteed throughput, eliminating "
                f"throttling and ensuring consistent performance under load."
            )
        elif has_low_throttling and tpm_utilization < 0.5:
            score = DimensionScore.NEGATIVE
            summary = "Low capacity pressure — PAYG is handling demand well."
            explanation = (
                f"Your deployment shows low capacity pressure:\n"
                f"• Throttling rate: {throttling_rate:.1%} (minimal)\n"
                f"• Utilization: {tpm_utilization:.1%} of {quota_source}\n\n"
                f"PAYG is meeting your needs without significant throttling. "
                f"PTU is designed for workloads that need more capacity than "
                f"PAYG can reliably provide. Your current usage doesn't indicate "
                f"this need."
            )
        else:
            score = DimensionScore.NEUTRAL
            summary = "Moderate capacity pressure detected."
            explanation = (
                f"Your deployment shows moderate capacity indicators:\n"
                f"• Throttling rate: {throttling_rate:.1%}\n"
                f"• Utilization: {tpm_utilization:.1%} of {quota_source}\n\n"
                f"You're experiencing some throttling but not severe. Consider "
                f"whether peak-time throttling is acceptable or if guaranteed "
                f"capacity would provide business value."
            )
        
        # Calculate confidence
        total_requests = metrics.total_requests
        confidence = min(1.0, total_requests / 10000)
        
        return DimensionResult(
            name=self.DIMENSION_NAME,
            score=score,
            confidence=confidence,
            summary=summary,
            explanation=explanation,
            key_metrics={
                "throttling_rate": throttling_rate,
                "tpm_utilization": tpm_utilization,
                "absolute_utilization": absolute_utilization,
                "total_requests": float(total_requests),
                "throttled_requests": float(metrics.throttled_requests.total if metrics.throttled_requests else 0),
            },
        )


class LatencySensitivityAnalyzer(DimensionAnalyzer):
    """
    Analyzes latency patterns and sensitivity.
    
    Evaluates:
    - P95/P99 latency values
    - Latency variance under load
    - Latency degradation patterns
    
    Latency-sensitive workloads benefit from PTU's dedicated capacity.
    """
    
    DIMENSION_NAME = "Latency Sensitivity"
    
    def analyze(self, metrics: DeploymentMetrics) -> DimensionResult:
        """Analyze latency patterns."""
        
        # Check if we have latency data
        if not metrics.time_to_first_byte_p50:
            return DimensionResult(
                name=self.DIMENSION_NAME,
                score=DimensionScore.INSUFFICIENT,
                confidence=0.0,
                summary="Insufficient latency data.",
                explanation="Latency metrics are not available for this deployment.",
                key_metrics={},
            )
        
        # Get latency statistics
        p50_latency = metrics.time_to_first_byte_p50.mean if metrics.time_to_first_byte_p50 else 0
        p95_latency = metrics.time_to_first_byte_p95.mean if metrics.time_to_first_byte_p95 else 0
        p99_latency = metrics.time_to_first_byte_p99.mean if metrics.time_to_first_byte_p99 else 0
        
        # Calculate latency variance ratio (P99/P50)
        latency_variance_ratio = p99_latency / p50_latency if p50_latency > 0 else 0
        
        # Determine if latency is concerning
        has_high_p95 = p95_latency > self.thresholds.p95_latency_poor
        has_high_variance = latency_variance_ratio > self.thresholds.latency_variance_unstable
        has_stable_latency = latency_variance_ratio < self.thresholds.latency_variance_stable
        
        # Determine score
        if has_high_p95 or has_high_variance:
            score = DimensionScore.POSITIVE
            summary = "Latency issues detected - PTU could improve consistency."
            explanation = (
                f"Your deployment shows latency concerns:\n"
                f"• P50 latency: {p50_latency:.0f}ms\n"
                f"• P95 latency: {p95_latency:.0f}ms\n"
                f"• P99 latency: {p99_latency:.0f}ms\n"
                f"• Variance ratio (P99/P50): {latency_variance_ratio:.1f}x\n\n"
                f"{'High P95 latency indicates requests are slow under normal conditions. ' if has_high_p95 else ''}"
                f"{'High variance suggests inconsistent performance. ' if has_high_variance else ''}"
                f"PTU provides dedicated capacity that typically delivers more "
                f"consistent, lower latency compared to shared PAYG infrastructure."
            )
        elif has_stable_latency and p95_latency < self.thresholds.p95_latency_good:
            score = DimensionScore.NEGATIVE
            summary = "Latency is stable and acceptable."
            explanation = (
                f"Your deployment shows healthy latency patterns:\n"
                f"• P50 latency: {p50_latency:.0f}ms\n"
                f"• P95 latency: {p95_latency:.0f}ms\n"
                f"• P99 latency: {p99_latency:.0f}ms\n"
                f"• Variance ratio (P99/P50): {latency_variance_ratio:.1f}x\n\n"
                f"Latency is consistent and within acceptable bounds. If your "
                f"application tolerates current latency levels, this dimension "
                f"doesn't strongly favor PTU."
            )
        else:
            score = DimensionScore.NEUTRAL
            summary = "Latency is moderate with some variability."
            explanation = (
                f"Your deployment shows moderate latency patterns:\n"
                f"• P50 latency: {p50_latency:.0f}ms\n"
                f"• P95 latency: {p95_latency:.0f}ms\n"
                f"• P99 latency: {p99_latency:.0f}ms\n"
                f"• Variance ratio (P99/P50): {latency_variance_ratio:.1f}x\n\n"
                f"Consider whether your application's latency requirements "
                f"justify the guaranteed performance of PTU."
            )
        
        confidence = 0.8 if metrics.time_to_first_byte_p95 else 0.5
        
        return DimensionResult(
            name=self.DIMENSION_NAME,
            score=score,
            confidence=confidence,
            summary=summary,
            explanation=explanation,
            key_metrics={
                "p50_latency_ms": p50_latency,
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
                "latency_variance_ratio": latency_variance_ratio,
            },
        )


class LoadPredictabilityAnalyzer(DimensionAnalyzer):
    """
    Analyzes load predictability patterns.
    
    Evaluates:
    - Sustained traffic percentage
    - Day-over-day similarity
    - Business hours concentration
    
    Predictable loads are ideal for PTU's reserved capacity model.
    """
    
    DIMENSION_NAME = "Load Predictability"
    
    def analyze(self, metrics: DeploymentMetrics) -> DimensionResult:
        """Analyze load predictability."""
        
        if not metrics.requests_per_minute or len(metrics.requests_per_minute) < self.thresholds.min_data_points:
            return DimensionResult(
                name=self.DIMENSION_NAME,
                score=DimensionScore.INSUFFICIENT,
                confidence=0.0,
                summary="Insufficient data to analyze load predictability.",
                explanation="Need more data points to determine load patterns.",
                key_metrics={},
            )
        
        # Calculate sustained traffic percentage using threshold-based metric
        # instead of simple non-zero count, to avoid treating 1 RPM as "sustained"
        rpm_values = np.array(metrics.requests_per_minute.values)
        sustained_rate = metrics.requests_per_minute.sustained_utilization_rate(
            threshold_pct=0.3
        ) / 100.0  # Convert from percentage to fraction
        
        # Calculate day-over-day similarity using autocorrelation
        similarity_score = self._calculate_daily_similarity(metrics.requests_per_minute)
        
        # Determine score
        is_sustained = sustained_rate >= self.thresholds.sustained_traffic_threshold
        is_predictable = similarity_score >= self.thresholds.day_similarity_threshold
        
        if is_sustained and is_predictable:
            score = DimensionScore.POSITIVE
            summary = "Load is sustained and predictable."
            explanation = (
                f"Your deployment shows predictable load patterns:\n"
                f"• Sustained utilization: {sustained_rate:.0%} of analyzed period\n"
                f"• Day-over-day similarity: {similarity_score:.0%}\n\n"
                f"This is ideal for PTU. Reserved capacity works best when you "
                f"can predict usage and avoid paying for idle time. Your consistent "
                f"daily patterns mean PTU capacity would be well-utilized."
            )
        elif sustained_rate < 0.3:
            score = DimensionScore.NEGATIVE
            summary = "Load is sparse with significant idle time."
            explanation = (
                f"Your deployment shows sparse usage patterns:\n"
                f"• Sustained utilization: {sustained_rate:.0%} of analyzed period\n"
                f"• Day-over-day similarity: {similarity_score:.0%}\n\n"
                f"With only {sustained_rate:.0%} sustained usage, PTU would result in "
                f"significant unused capacity. PAYG is more cost-effective for "
                f"workloads that are idle most of the time."
            )
        else:
            score = DimensionScore.NEUTRAL
            summary = "Load patterns are moderately predictable."
            explanation = (
                f"Your deployment shows moderate predictability:\n"
                f"• Sustained utilization: {sustained_rate:.0%} of analyzed period\n"
                f"• Day-over-day similarity: {similarity_score:.0%}\n\n"
                f"Consider whether your usage patterns are driven by known "
                f"business cycles (weekly/monthly) that would still benefit "
                f"from reserved capacity."
            )
        
        confidence = min(1.0, len(metrics.requests_per_minute) / 300)
        
        return DimensionResult(
            name=self.DIMENSION_NAME,
            score=score,
            confidence=confidence,
            summary=summary,
            explanation=explanation,
            key_metrics={
                "sustained_traffic_pct": sustained_rate,
                "day_over_day_similarity": similarity_score,
                "total_data_points": float(len(rpm_values)),
            },
        )
    
    def _calculate_daily_similarity(self, time_series: TimeSeries) -> float:
        """Calculate day-over-day and week-over-week similarity score.

        Uses autocorrelation at both 24-hour (daily) and 168-hour (weekly) lags
        to capture both intra-day patterns and weekly cycles (e.g. weekday vs
        weekend).  Returns the higher of the two, since weekly regularity is
        just as valid for PTU capacity planning as daily regularity.
        """
        if len(time_series.values) < 48:  # Need at least 2 days of hourly data
            return 0.5

        values = np.array(time_series.values)

        def _autocorrelation(data: np.ndarray, lag: int) -> float:
            if len(data) < lag * 2:
                return 0.5
            shifted = data[lag:]
            original = data[:-lag]
            if np.std(original) > 0 and np.std(shifted) > 0:
                corr = np.corrcoef(original, shifted)[0, 1]
                if np.isnan(corr):
                    return 0.5
                return max(0.0, float(corr))
            return 0.5

        daily_corr = _autocorrelation(values, lag=24)
        weekly_corr = _autocorrelation(values, lag=168)

        # Use the best of daily or weekly — weekly patterns are equally valid
        return max(daily_corr, weekly_corr)
