"""Chart generation for PTU Advisor reports."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionScore,
    TimeSeries,
)


# Microsoft-inspired color palette
COLORS = {
    "primary": "#0078D4",      # Microsoft Blue
    "secondary": "#50E6FF",    # Light Blue
    "success": "#107C10",      # Green
    "warning": "#FFB900",      # Yellow
    "danger": "#D13438",       # Red
    "neutral": "#737373",      # Gray
    "light": "#F3F2F1",        # Light Gray
    "dark": "#323130",         # Dark Gray
}

# Recommendation colors
REC_COLORS = {
    "positive": COLORS["success"],
    "neutral": COLORS["warning"],
    "negative": COLORS["danger"],
    "insufficient": COLORS["neutral"],
}


@dataclass
class Chart:
    """A generated chart."""
    
    name: str
    title: str
    image_base64: str
    description: str
    
    @property
    def html_img_tag(self) -> str:
        """Generate HTML img tag with embedded base64 image."""
        return f'<img src="data:image/png;base64,{self.image_base64}" alt="{self.title}" />'


class ChartGenerator:
    """Generates charts for PTU Advisor reports."""
    
    def __init__(self, config: AnalysisConfig) -> None:
        """Initialize the chart generator."""
        self.config = config
        
        # Set matplotlib style
        plt.style.use('seaborn-v0_8-whitegrid')
        plt.rcParams['figure.figsize'] = (10, 5)
        plt.rcParams['figure.dpi'] = 100
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.size'] = 10
    
    def generate(
        self,
        metrics: DeploymentMetrics,
        result: AnalysisResult,
    ) -> list[Chart]:
        """
        Generate all charts for the report.
        
        Args:
            metrics: Collected deployment metrics.
            result: Analysis result.
            
        Returns:
            List of generated charts.
        """
        charts = []
        
        # TPM/RPM over time
        if metrics.tokens_per_minute:
            charts.append(self._create_tpm_chart(metrics))
        
        # Request volume over time
        if metrics.requests_per_minute:
            charts.append(self._create_requests_chart(metrics))
        
        # Latency distribution
        if metrics.time_to_first_byte_p50:
            charts.append(self._create_latency_chart(metrics))
        
        # Throttling events
        if metrics.throttled_requests:
            charts.append(self._create_throttling_chart(metrics))

        if (metrics.cache_match_rate or metrics.active_tokens) and metrics.prompt_tokens:
            charts.append(self._create_prompt_cache_chart(metrics))
        
        # Dimension radar chart
        charts.append(self._create_dimension_radar(result))
        
        return charts
    
    def _create_tpm_chart(self, metrics: DeploymentMetrics) -> Chart:
        """Create tokens per minute over time chart."""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        ts = metrics.tokens_per_minute
        dates = ts.timestamps
        values = ts.values
        
        # Plot the line
        ax.plot(dates, values, color=COLORS["primary"], linewidth=1.5, alpha=0.8)
        ax.fill_between(dates, values, alpha=0.2, color=COLORS["primary"])
        
        # Add mean line
        mean_val = ts.mean
        ax.axhline(y=mean_val, color=COLORS["neutral"], linestyle='--', 
                   linewidth=1, label=f'Mean: {mean_val:,.0f} TPM')
        
        # Formatting
        ax.set_xlabel('Date')
        ax.set_ylabel('Tokens per Minute')
        ax.set_title('Token Throughput Over Time', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.xticks(rotation=45)
        
        # Add grid
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        return Chart(
            name="tpm_chart",
            title="Token Throughput Over Time",
            image_base64=self._fig_to_base64(fig),
            description="Shows the tokens per minute (TPM) over the analysis period. "
                        "Stable patterns are ideal for PTU.",
        )
    
    def _create_requests_chart(self, metrics: DeploymentMetrics) -> Chart:
        """Create requests per minute chart."""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        ts = metrics.requests_per_minute
        dates = ts.timestamps
        values = ts.values
        
        # Create bar chart for better visualization of discrete events
        ax.bar(dates, values, color=COLORS["secondary"], alpha=0.7, width=0.03)
        
        # Add mean line
        mean_val = ts.mean
        ax.axhline(y=mean_val, color=COLORS["primary"], linestyle='--',
                   linewidth=2, label=f'Mean: {mean_val:.1f} RPM')
        
        # Formatting
        ax.set_xlabel('Date')
        ax.set_ylabel('Requests per Minute')
        ax.set_title('Request Volume Over Time', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.xticks(rotation=45)
        
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        return Chart(
            name="requests_chart",
            title="Request Volume Over Time",
            image_base64=self._fig_to_base64(fig),
            description="Shows the number of requests per minute over time. "
                        "Consistent request patterns indicate predictable load.",
        )
    
    def _create_latency_chart(self, metrics: DeploymentMetrics) -> Chart:
        """Create latency distribution chart."""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        # Get latency data
        p50 = metrics.time_to_first_byte_p50
        p95 = metrics.time_to_first_byte_p95
        p99 = metrics.time_to_first_byte_p99
        
        dates = p50.timestamps if p50 else []
        
        # Plot percentile lines
        if p50:
            ax.plot(dates, p50.values, color=COLORS["success"], 
                    linewidth=2, label=f'P50: {p50.mean:.0f}ms', alpha=0.8)
        if p95:
            ax.plot(dates, p95.values, color=COLORS["warning"], 
                    linewidth=2, label=f'P95: {p95.mean:.0f}ms', alpha=0.8)
        if p99:
            ax.plot(dates, p99.values, color=COLORS["danger"], 
                    linewidth=2, label=f'P99: {p99.mean:.0f}ms', alpha=0.8)
        
        # Formatting
        ax.set_xlabel('Date')
        ax.set_ylabel('Latency (ms)')
        ax.set_title('Latency Percentiles Over Time', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.xticks(rotation=45)
        
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        return Chart(
            name="latency_chart",
            title="Latency Percentiles Over Time",
            image_base64=self._fig_to_base64(fig),
            description="Shows P50, P95, and P99 latency over time. "
                        "Large gaps between percentiles indicate inconsistent performance.",
        )
    
    def _create_throttling_chart(self, metrics: DeploymentMetrics) -> Chart:
        """Create throttling events chart."""
        fig, ax = plt.subplots(figsize=(12, 5))
        
        ts = metrics.throttled_requests
        dates = ts.timestamps
        values = ts.values
        
        # Bar chart for throttling events
        ax.bar(dates, values, color=COLORS["danger"], alpha=0.7, width=0.03)
        
        # Add total throttled annotation
        total_throttled = ts.total
        throttle_rate = metrics.throttling_rate
        
        ax.annotate(
            f'Total Throttled: {total_throttled:,.0f} ({throttle_rate:.1%})',
            xy=(0.02, 0.95), xycoords='axes fraction',
            fontsize=11, fontweight='bold',
            color=COLORS["danger"] if throttle_rate > 0.01 else COLORS["neutral"],
        )
        
        # Formatting
        ax.set_xlabel('Date')
        ax.set_ylabel('Throttled Requests (429s)')
        ax.set_title('Throttling Events Over Time', fontsize=14, fontweight='bold')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.xticks(rotation=45)
        
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        return Chart(
            name="throttling_chart",
            title="Throttling Events Over Time",
            image_base64=self._fig_to_base64(fig),
            description="Shows HTTP 429 (throttled) responses over time. "
                        "High throttling indicates capacity pressure.",
        )

    def _create_prompt_cache_chart(self, metrics: DeploymentMetrics) -> Chart:
        """Create prompt cache rate and active/cached token chart."""
        cache = metrics.cache_match_rate
        prompt = metrics.prompt_tokens
        fig, left = plt.subplots(figsize=(12, 5))
        dates = prompt.timestamps
        if cache:
            cache_lookup = dict(zip(cache.timestamps, cache.values))
            rates = [min(1.0, max(0.0, float(cache_lookup.get(ts, 0.0)))) for ts in dates]
        elif metrics.active_tokens and metrics.completion_tokens:
            active_lookup = dict(zip(metrics.active_tokens.timestamps, metrics.active_tokens.values))
            completion_lookup = dict(zip(metrics.completion_tokens.timestamps, metrics.completion_tokens.values))
            rates = []
            for ts, prompt_value in zip(dates, prompt.values):
                rate = infer_cache_match_rate(
                    prompt_value,
                    completion_lookup.get(ts, 0.0),
                    active_lookup.get(ts, prompt_value),
                )
                rates.append(rate if rate is not None else 0.0)
        else:
            rates = [0.0] * len(dates)
        cached = [value * rate for value, rate in zip(prompt.values, rates)]
        active = [value - cached_value for value, cached_value in zip(prompt.values, cached)]

        left.stackplot(
            dates,
            active,
            cached,
            labels=["Active Prompt Tokens", "Cached Prompt Tokens"],
            colors=[COLORS["primary"], COLORS["success"]],
            alpha=0.65,
        )
        left.set_ylabel("Prompt Tokens")
        left.set_xlabel("Date")
        left.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

        right = left.twinx()
        right.plot(dates, [rate * 100 for rate in rates], color=COLORS["warning"], linewidth=2)
        right.set_ylim(0, 100)
        right.set_ylabel("Cache Match Rate (%)")
        left.set_title("Prompt Cache Benefit", fontsize=14, fontweight="bold")
        left.legend(loc="upper left")
        left.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()

        return Chart(
            name="prompt_cache",
            title="Prompt Cache Benefit",
            image_base64=self._fig_to_base64(fig),
            description=(
                "Shows prompt tokens served from cache versus active prompt tokens. "
                "Cached prompt tokens reduce modeled PTU utilization."
            ),
        )
    
    def _create_dimension_radar(self, result: AnalysisResult) -> Chart:
        """Create radar chart showing dimension scores."""
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
        
        # Dimension data
        dimensions = result.dimensions.all_dimensions
        labels = [d.name for d in dimensions]
        
        # Convert scores to numeric values
        score_values = {
            DimensionScore.POSITIVE: 1.0,
            DimensionScore.NEUTRAL: 0.5,
            DimensionScore.NEGATIVE: 0.0,
            DimensionScore.INSUFFICIENT: 0.25,
        }
        
        values = [score_values.get(d.score, 0.5) for d in dimensions]
        
        # Close the polygon
        values += values[:1]
        
        # Compute angles
        num_dims = len(labels)
        angles = [n / float(num_dims) * 2 * np.pi for n in range(num_dims)]
        angles += angles[:1]
        
        # Plot
        ax.plot(angles, values, 'o-', linewidth=2, color=COLORS["primary"])
        ax.fill(angles, values, alpha=0.25, color=COLORS["primary"])
        
        # Add labels
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, size=11)
        
        # Set y-axis limits
        ax.set_ylim(0, 1)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(['❌', '⚖️', '', '✅'], size=12)
        
        # Title
        ax.set_title('Dimension Analysis Summary', fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        
        return Chart(
            name="dimension_radar",
            title="Dimension Analysis Summary",
            image_base64=self._fig_to_base64(fig),
            description="Radar chart showing how each dimension scored. "
                        "Outer ring (✅) = favorable for PTU, center (❌) = unfavorable.",
        )
    
    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 string."""
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', 
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
