"""HTML report generator for PTU Advisor."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import escape

from ptu_advisor.analysis.rule_explainer import Explainer
from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionScore,
    Recommendation,
    TimeSeries,
)
from ptu_advisor.visualization.charts import Chart


class ReportGenerator:
    """Generates HTML reports for PTU recommendations."""

    def __init__(self, config: AnalysisConfig) -> None:
        """Initialize the report generator."""
        self.config = config
        self.explainer = Explainer()

        # Set up Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add custom filters
        self.env.filters["format_number"] = self._format_number
        self.env.filters["format_percent"] = self._format_percent
        self.env.filters["format_duration"] = self._format_duration
        self.env.filters["markdown_to_html"] = self._markdown_to_html

    def generate(
        self,
        metrics: DeploymentMetrics,
        result: AnalysisResult,
        charts: list[Chart],
        output_path: Optional[Path] = None,
        llm_analysis: Optional[str] = None,
    ) -> Path:
        """
        Generate an HTML report.

        Args:
            metrics: Collected deployment metrics.
            result: Analysis result.
            charts: Generated charts.
            output_path: Optional output path. Defaults to ./outputs/

        Returns:
            Path to the generated report.
        """
        # Generate explanation sections
        explanation_sections = self.explainer.generate_full_explanation(result, metrics)

        # Prepare template context
        context = {
            # Metadata
            "report_date": datetime.now().strftime("%B %d, %Y at %H:%M"),
            "deployment_name": metrics.deployment_name,
            "model_name": metrics.model_name,
            "analysis_period": result.analysis_period,
            # Result
            "recommendation": result.recommendation,
            "recommendation_text": result.recommendation.value.replace("_", " ").upper(),
            "recommendation_class": self._get_recommendation_class(result.recommendation),
            "recommendation_emoji": result.recommendation_emoji,
            "confidence": result.confidence,
            "summary": result.summary,
            # Dimensions
            "dimensions": result.dimensions.all_dimensions,
            "dimension_score_class": self._dimension_score_class,
            # Explanations
            "explanation_sections": explanation_sections,
            # Charts
            "charts": charts,
            # Metrics summary
            "metrics_summary": self._get_metrics_summary(metrics),
            # LLM analysis (optional enrichment)
            "llm_analysis": llm_analysis,
            # Data quality
            "data_quality": result.data_quality,
            # What would change
            "what_would_change": result.what_would_change,
            # PTU cost estimates
            "ptu_estimates": self._calculate_ptu_estimates(metrics),
        }

        # Render template
        template = self.env.get_template("report.html")
        html_content = template.render(**context)

        # Determine output path
        if output_path is None:
            output_dir = Path.cwd() / "outputs"
            output_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"ptu-report-{metrics.deployment_name}-{timestamp}.html"

        # Write report
        output_path.write_text(html_content)

        return output_path

    def _get_recommendation_class(self, recommendation: Recommendation) -> str:
        """Get CSS class for recommendation."""
        return {
            Recommendation.PTU_RECOMMENDED: "success",
            Recommendation.BORDERLINE: "warning",
            Recommendation.PTU_NOT_RECOMMENDED: "danger",
        }.get(recommendation, "neutral")

    def _dimension_score_class(self, score: DimensionScore) -> str:
        """Get CSS class for dimension score."""
        return {
            DimensionScore.POSITIVE: "success",
            DimensionScore.NEUTRAL: "warning",
            DimensionScore.NEGATIVE: "danger",
            DimensionScore.INSUFFICIENT: "muted",
        }.get(score, "muted")

    def _get_metrics_summary(self, metrics: DeploymentMetrics) -> dict:
        """Get summary metrics for display."""
        # Calculate additional metrics
        successful = metrics.successful_requests.total if metrics.successful_requests else 0
        throttled = metrics.throttled_requests.total if metrics.throttled_requests else 0
        total_calls = successful + throttled
        success_rate = successful / total_calls if total_calls > 0 else 0

        # Token calculations
        prompt_tokens = metrics.prompt_tokens.total if metrics.prompt_tokens else 0
        completion_tokens = metrics.completion_tokens.total if metrics.completion_tokens else 0
        total_tokens = prompt_tokens + completion_tokens
        prompt_ratio = prompt_tokens / total_tokens if total_tokens > 0 else 0
        from ptu_advisor.config import get_model_config as _get_cache_model_config
        from ptu_advisor.cost.cache import build_cache_impact as _build_cache_impact

        cache_model = _get_cache_model_config(metrics.model_name)
        cache_impact = _build_cache_impact(
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            cache_match_rate=metrics.cache_match_rate,
            active_tokens=metrics.active_tokens,
            output_multiplier=cache_model.output_ratio if cache_model else 1,
            input_tpm_per_ptu=cache_model.input_tpm_per_ptu if cache_model else 1,
            min_ptu=1,
            ptu_increment=1,
            interval_minutes=self._metric_interval_minutes(metrics.prompt_tokens),
            coverage_pct_override=metrics.cache_coverage_pct,
        )
        cache_match_rate = cache_impact.avg_match_rate_pct / 100.0
        cached_prompt_tokens = cache_impact.total_cached_prompt_tokens
        active_prompt_tokens = cache_impact.total_active_prompt_tokens

        # TPM stats
        tpm_mean = metrics.tokens_per_minute.mean if metrics.tokens_per_minute else 0
        tpm_max = metrics.tokens_per_minute.max if metrics.tokens_per_minute else 0
        tpm_std = metrics.tokens_per_minute.std if metrics.tokens_per_minute else 0
        tpm_cv = tpm_std / tpm_mean if tpm_mean > 0 else 0

        # Request stats
        rpm_mean = metrics.requests_per_minute.mean if metrics.requests_per_minute else 0
        rpm_max = metrics.requests_per_minute.max if metrics.requests_per_minute else 0

        # Latency stats
        p50_avg = metrics.time_to_first_byte_p50.mean if metrics.time_to_first_byte_p50 else 0
        p50_min = metrics.time_to_first_byte_p50.min if metrics.time_to_first_byte_p50 else 0
        p50_max = metrics.time_to_first_byte_p50.max if metrics.time_to_first_byte_p50 else 0

        p95_avg = metrics.time_to_first_byte_p95.mean if metrics.time_to_first_byte_p95 else 0
        p95_min = metrics.time_to_first_byte_p95.min if metrics.time_to_first_byte_p95 else 0
        p95_max = metrics.time_to_first_byte_p95.max if metrics.time_to_first_byte_p95 else 0

        p99_avg = metrics.time_to_first_byte_p99.mean if metrics.time_to_first_byte_p99 else 0
        p99_min = metrics.time_to_first_byte_p99.min if metrics.time_to_first_byte_p99 else 0
        p99_max = metrics.time_to_first_byte_p99.max if metrics.time_to_first_byte_p99 else 0

        # Latency variance
        latency_variance = p99_avg / p50_avg if p50_avg > 0 else 0

        # Usage patterns
        data_points = len(metrics.timestamps)
        non_zero_hours = (
            metrics.requests_per_minute.non_zero_count if metrics.requests_per_minute else 0
        )
        active_percentage = non_zero_hours / data_points if data_points > 0 else 0

        # Utilization estimate — use actual TPM data against known PAYG quota
        utilization = 0.0
        if metrics.tokens_per_minute:
            from ptu_advisor.config import get_model_config as _get_model_config

            _mc = _get_model_config(metrics.model_name)
            if _mc and _mc.payg_tpm_quota > 0:
                utilization = min(1.0, metrics.tokens_per_minute.p95 / _mc.payg_tpm_quota)
            elif metrics.tokens_per_minute.max > 0:
                utilization = metrics.tokens_per_minute.mean / metrics.tokens_per_minute.max
        if utilization == 0.0:
            utilization = min(0.99, 0.5 + metrics.throttling_rate)

        return {
            # Basic metrics (existing)
            "total_requests": metrics.total_requests,
            "throttling_rate": metrics.throttling_rate,
            "avg_tokens_per_request": metrics.avg_tokens_per_request,
            "tpm_mean": tpm_mean,
            "tpm_max": tpm_max,
            "p50_latency": p50_avg,
            "p95_latency": p95_avg,
            "data_points": data_points,
            # Deployment info
            "sku_type": (
                metrics.deployment_info.sku_type if metrics.deployment_info else "Standard (PAYG)"
            ),
            # Request metrics
            "rpm_mean": rpm_mean,
            "rpm_max": rpm_max,
            "successful_requests": successful,
            "success_rate": success_rate,
            "throttled_requests": throttled,
            # Token metrics
            "tpm_std": tpm_std,
            "tpm_cv": tpm_cv,
            "total_tokens": total_tokens,
            "prompt_ratio": prompt_ratio,
            "completion_ratio": 1 - prompt_ratio,
            "cache_match_rate": cache_match_rate,
            "cached_prompt_tokens": cached_prompt_tokens,
            "active_prompt_tokens": active_prompt_tokens,
            "cache_source": cache_impact.source,
            "cache_quality": cache_impact.quality,
            "cache_coverage_pct": cache_impact.coverage_pct,
            "cache_validation_warnings": cache_impact.validation_warnings,
            # Latency metrics
            "p50_min": p50_min,
            "p50_max": p50_max,
            "p95_min": p95_min,
            "p95_max": p95_max,
            "p99_latency": p99_avg,
            "p99_min": p99_min,
            "p99_max": p99_max,
            "latency_variance": latency_variance,
            # Usage patterns
            "active_percentage": active_percentage,
            "non_zero_hours": non_zero_hours,
            # Capacity indicators
            "utilization": utilization,
        }

    @staticmethod
    def _format_number(value: float) -> str:
        """Format number with commas."""
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.1f}K"
        else:
            return f"{value:,.0f}"

    @staticmethod
    def _format_percent(value: float) -> str:
        """Format as percentage."""
        return f"{value:.1%}"

    @staticmethod
    def _format_duration(ms: float) -> str:
        """Format duration in milliseconds."""
        if ms >= 1000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms:.0f}ms"

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Convert simple markdown to HTML."""
        if not text:
            return text

        text = str(escape(text))

        # Convert **bold** to <strong>
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

        # Convert *italic* to <em>
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        # Convert newlines to <br> for paragraphs
        text = text.replace("\n\n", "</p><p>")
        text = text.replace("\n", "<br>")

        # Wrap in paragraph if not already
        if not text.startswith("<p>"):
            text = f"<p>{text}</p>"

        return text

    def _calculate_ptu_estimates(self, metrics: DeploymentMetrics) -> dict:
        """
        Calculate PTU estimates based on metrics and Azure PTU documentation.

        PTU minimums and TPM per PTU from:
        https://learn.microsoft.com/azure/ai-services/openai/how-to/provisioned-throughput-onboarding
        """
        # Get peak TPM (use P95 for safer estimate)
        if metrics.tokens_per_minute:
            peak_tpm = metrics.tokens_per_minute.p95
            avg_tpm = metrics.tokens_per_minute.mean
        else:
            return {"available": False}

        # Prompt/completion ratio affects PTU calculation
        # Output tokens count more toward utilization (e.g., 4x for GPT-4.1, 8x for GPT-5)
        prompt_tokens = metrics.prompt_tokens.total if metrics.prompt_tokens else 0
        completion_tokens = metrics.completion_tokens.total if metrics.completion_tokens else 0
        total_tokens = prompt_tokens + completion_tokens
        completion_ratio = completion_tokens / total_tokens if total_tokens > 0 else 0.4

        # Use centralized model configs from config.py (single source of truth)
        from ptu_advisor.config import MODEL_CAPACITY_CONFIGS
        from ptu_advisor.config import get_model_config as _get_model_config

        model_config = _get_model_config(metrics.model_name)

        # Default to gpt-4o if unknown
        if model_config is None:
            model_config = MODEL_CAPACITY_CONFIGS["gpt-4o"]
            model_key = "gpt-4o"
        else:
            # Determine matched key for PAYG rate lookup
            model_key = "gpt-4o"  # default
            model_lower = metrics.model_name.lower()
            for key in sorted(MODEL_CAPACITY_CONFIGS, key=len, reverse=True):
                if key in model_lower:
                    model_key = key
                    break

        config = {
            "input_tpm_per_ptu": model_config.input_tpm_per_ptu,
            "output_ratio": model_config.output_ratio,
            "global_min": model_config.global_min_ptu,
            "global_inc": model_config.global_increment,
            "regional_min": model_config.regional_min_ptu,
            "regional_inc": model_config.regional_increment,
        }

        from ptu_advisor.cost.cache import build_cache_impact

        cache_impact = build_cache_impact(
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            cache_match_rate=metrics.cache_match_rate,
            active_tokens=metrics.active_tokens,
            output_multiplier=config["output_ratio"],
            input_tpm_per_ptu=config["input_tpm_per_ptu"],
            min_ptu=config["global_min"],
            ptu_increment=config["global_inc"],
            interval_minutes=self._metric_interval_minutes(metrics.prompt_tokens),
            coverage_pct_override=metrics.cache_coverage_pct,
        )

        # Calculate effective TPM considering output token weight
        # Effective TPM = input_tokens + (output_tokens * output_ratio)
        prompt_ratio = 1 - completion_ratio
        effective_multiplier = prompt_ratio + (completion_ratio * config["output_ratio"])

        if cache_impact.adjusted_normalized_tpm:
            raw_ptu_needed = (
                float(np.percentile(cache_impact.adjusted_normalized_tpm, 95))
                / config["input_tpm_per_ptu"]
            )
            avg_ptu_needed = (
                cache_impact.cache_adjusted_normalized_avg_tpm
                / config["input_tpm_per_ptu"]
            )
        else:
            raw_ptu_needed = (peak_tpm * effective_multiplier) / config[
                "input_tpm_per_ptu"
            ]
            avg_ptu_needed = (avg_tpm * effective_multiplier) / config[
                "input_tpm_per_ptu"
            ]

        # Round to deployment increments
        def round_to_increment(value: float, minimum: int, increment: int) -> int:
            if value <= minimum:
                return minimum
            return max(minimum, int(((value - minimum) // increment + 1) * increment + minimum))

        global_ptu = cache_impact.cache_aware_recommended_ptu
        regional_ptu = round_to_increment(
            raw_ptu_needed, config["regional_min"], config["regional_inc"]
        )

        # Conservative estimate (for average load)
        global_ptu_conservative = round_to_increment(
            avg_ptu_needed, config["global_min"], config["global_inc"]
        )
        regional_ptu_conservative = round_to_increment(
            avg_ptu_needed, config["regional_min"], config["regional_inc"]
        )

        # PTU hourly rates and PAYG rates via PricingResolver
        # (replaces old hardcoded dicts — resolves live → cached → static fallback)
        from ptu_advisor.cost.price_resolver import get_pricing_resolver

        _resolver = get_pricing_resolver()
        pricing_model_name = metrics.model_name
        if metrics.deployment_info and metrics.deployment_info.model_version:
            pricing_model_name = f"{metrics.model_name}-{metrics.deployment_info.model_version}"

        # Resolve pricing for Global deployment (report default)
        _global_pricing = _resolver.resolve(
            model_name=pricing_model_name,
            region="eastus",
            deployment_type="global",
        )
        global_hourly_rate = _global_pricing.ptu_hourly_rate

        # Resolve pricing for Regional deployment
        _regional_pricing = _resolver.resolve(
            model_name=pricing_model_name,
            region="eastus",
            deployment_type="regional",
        )
        regional_hourly_rate = _regional_pricing.ptu_hourly_rate

        reservation_discount = 0.35  # ~65% discount

        # --- PAYG cost estimation (from resolver) ---
        payg_input_rate = _global_pricing.payg_input_rate
        payg_cached_input_rate = _global_pricing.payg_cached_input_rate
        payg_output_rate = _global_pricing.payg_output_rate

        monthly_tokens = avg_tpm * 43_200
        monthly_input_tokens = monthly_tokens * (1 - completion_ratio)
        monthly_output_tokens = monthly_tokens * completion_ratio
        cached_monthly_input = monthly_input_tokens * (
            cache_impact.avg_match_rate_pct / 100.0 if cache_impact.applied else 0.0
        )
        active_monthly_input = monthly_input_tokens - cached_monthly_input
        payg_monthly_cost = (
            active_monthly_input / 1_000_000 * payg_input_rate
            + cached_monthly_input / 1_000_000 * payg_cached_input_rate
            + (
            monthly_output_tokens / 1_000_000
            ) * payg_output_rate
        )

        ptu_monthly_global = global_ptu * global_hourly_rate * 720
        ptu_savings_pct = (
            (payg_monthly_cost - ptu_monthly_global) / payg_monthly_cost * 100
            if payg_monthly_cost > 0
            else 0.0
        )

        return {
            "available": True,
            "model_detected": model_key,
            "peak_tpm": peak_tpm,
            "avg_tpm": avg_tpm,
            "completion_ratio": completion_ratio,
            "effective_multiplier": effective_multiplier,
            "raw_ptu_needed": raw_ptu_needed,
            # Global/Data Zone Provisioned
            "global_min": config["global_min"],
            "global_inc": config["global_inc"],
            "global_ptu_recommended": global_ptu,
            "global_ptu_conservative": global_ptu_conservative,
            "global_hourly_cost": global_ptu * global_hourly_rate,
            "global_monthly_cost": global_ptu * global_hourly_rate * 720,
            "global_monthly_reserved": global_ptu * global_hourly_rate * 720 * reservation_discount,
            # Regional Provisioned
            "regional_min": config["regional_min"],
            "regional_inc": config["regional_inc"],
            "regional_ptu_recommended": regional_ptu,
            "regional_ptu_conservative": regional_ptu_conservative,
            "regional_hourly_cost": regional_ptu * regional_hourly_rate,
            "regional_monthly_cost": regional_ptu * regional_hourly_rate * 720,
            "regional_monthly_reserved": regional_ptu
            * regional_hourly_rate
            * 720
            * reservation_discount,
            # PAYG cost estimate
            "payg_input_rate_per_1m": payg_input_rate,
            "payg_output_rate_per_1m": payg_output_rate,
            "payg_monthly_estimate": payg_monthly_cost,
            "monthly_input_tokens": monthly_input_tokens,
            "monthly_output_tokens": monthly_output_tokens,
            # Cost comparison
            "ptu_savings_pct": ptu_savings_pct,
            "ptu_is_cheaper": ptu_savings_pct > 0,
            # PTU specs
            "input_tpm_per_ptu": config["input_tpm_per_ptu"],
            "output_ratio": config["output_ratio"],
            "cache_match_rate": cache_impact.avg_match_rate_pct / 100.0,
            "cache_source": cache_impact.source,
            "cache_quality": cache_impact.quality,
            "ptu_avoided": cache_impact.ptu_avoided,
            "no_cache_recommended_ptu": cache_impact.no_cache_recommended_ptu,
            "cache_aware_recommended_ptu": cache_impact.cache_aware_recommended_ptu,
            "no_cache_payg_estimate": (
                monthly_input_tokens / 1_000_000 * payg_input_rate
                + monthly_output_tokens / 1_000_000 * payg_output_rate
            ),
        }

    @staticmethod
    def _metric_interval_minutes(series: Optional[TimeSeries]) -> int:
        if series is None or len(series.timestamps) < 2:
            return 1
        deltas = [
            (current - previous).total_seconds() / 60.0
            for previous, current in zip(series.timestamps, series.timestamps[1:])
            if current > previous
        ]
        return max(1, int(round(float(np.median(deltas))))) if deltas else 1
