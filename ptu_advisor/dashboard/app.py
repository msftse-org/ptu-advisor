"""
PTU Advisor - Interactive Streamlit Dashboard

A responsive, interactive dashboard for analyzing Foundry deployments
and providing PTU (Provisioned Throughput Units) recommendations.
"""

from __future__ import annotations

import json
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from ptu_advisor.cost.calculator import (
    calculate_break_even,
    calculate_ptu_costs,
    calculate_spillover_cost,
    generate_cost_curves,
)
from ptu_advisor.demo import generate_demo_metrics, DemoScenario, SCENARIOS, FOCUS_TOPICS
from ptu_advisor.analysis.engine import DecisionEngine
from ptu_advisor.config import ThresholdConfig, AnalysisConfig
from ptu_advisor.llm.explainer import PTUExplainer
from ptu_advisor.llm.provider import LLMConfig

# Live Azure connection imports (lazy-loaded to avoid import errors
# when azure SDK packages are not installed)
def _import_azure_deps():
    """Lazily import Azure SDK dependencies for live connection."""
    from ptu_advisor.auth import get_azure_credential, validate_access
    from ptu_advisor.metrics.collector import MetricsCollector, list_workspace_deployments
    return get_azure_credential, validate_access, MetricsCollector, list_workspace_deployments

def _import_discovery():
    """Lazily import the discovery module."""
    from ptu_advisor import discovery
    return discovery

# =============================================================================
# Page Configuration
# =============================================================================

st.set_page_config(
    page_title="PTU Advisor",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "PTU Advisor - Foundry PTU Recommendation Tool"
    }
)

# =============================================================================
# Custom CSS - loaded from external file for performance + maintainability
# =============================================================================

@st.cache_resource
def load_css() -> str:
    """Load CSS from external file (cached across reruns)."""
    css_path = Path(__file__).parent / "style.css"
    return css_path.read_text()

st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)

# =============================================================================
# Helper Functions
# =============================================================================

def format_number(value: float) -> str:
    """Format large numbers with K/M suffix."""
    if value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value/1_000:.1f}K"
    else:
        return f"{value:.0f}"


def render_section_header(title: str, subtitle: str, sticky: bool = True) -> None:
    """Render a styled section header, optionally sticky (#3 + #9)."""
    cls = "section-header-sticky" if sticky else ""
    st.markdown(f"""
    <div class="{cls}" style="background: linear-gradient(180deg, rgba(18,27,47,0.92), rgba(15,23,40,0.88));
                padding: 22px; border-radius: 14px; margin-bottom: 16px;
                border: 1px solid #253153; box-shadow: 0 16px 40px rgba(2,6,23,0.32);">
        <h3 style="margin:0 0 8px 0; color:#f2f6ff; font-family:'DM Sans',sans-serif; font-weight:600; letter-spacing:-0.01em;">{title}</h3>
        <p style="margin:0; color:#8e97b3; font-size:14px;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


def render_section_divider(label: str) -> None:
    """Render a styled section divider with a label (#9)."""
    st.markdown(f"""
    <div class="section-divider">
        <div class="divider-line"></div>
        <div class="divider-label">{label}</div>
        <div class="divider-line"></div>
    </div>
    """, unsafe_allow_html=True)


def build_export_payload(
    metrics: Any,
    analysis: Any,
    spillover: Dict[str, Any],
    payg_total: float,
    hybrid_total: float,
    reservation_type: str,
) -> Dict[str, Any]:
    """Build a JSON-serializable dict for the export/download button (#11)."""
    return {
        "generated_at": datetime.now().isoformat(),
        "tool": "PTU Advisor v1.0",
        "deployment": metrics.deployment_name,
        "model": metrics.model_name,
        "analysis_period_days": (metrics.end_time - metrics.start_time).days,
        "recommendation": analysis.recommendation.value,
        "confidence": round(analysis.confidence, 3),
        "summary": analysis.summary,
        "dimensions": {
            dim.name: {
                "score": dim.score.value,
                "confidence": round(dim.confidence, 3),
                "summary": dim.summary,
                "key_metrics": dim.key_metrics,
            }
            for dim in analysis.dimensions.all_dimensions
        },
        "cost_comparison": {
            "payg_monthly_usd": round(payg_total, 2),
            "hybrid_monthly_usd": round(hybrid_total, 2),
            "reservation_type": reservation_type,
            "baseline_ptu": spillover.get("baseline_ptu", 0),
            "spillover_pct": round(spillover.get("spillover_pct", 0), 1),
        },
        "metrics_snapshot": {
            "avg_tpm": round(metrics.tokens_per_minute.mean, 1) if metrics.tokens_per_minute else 0,
            "peak_tpm_p95": round(metrics.tokens_per_minute.p95, 1) if metrics.tokens_per_minute else 0,
            "throttling_rate_pct": round(metrics.throttling_rate * 100, 2),
            "total_requests": metrics.total_requests,
        },
    }


def get_recommendation_class(recommendation: str) -> str:
    """Get CSS class based on recommendation."""
    if recommendation == "PTU_RECOMMENDED":
        return "recommendation-ptu"
    elif recommendation == "PTU_NOT_RECOMMENDED":
        return "recommendation-payg"
    else:
        return "recommendation-borderline"


def _foundry_layout(title: str, yaxis_title: str, height: int = 280) -> dict:
    """Return common Plotly layout config for Foundry-style charts."""
    return dict(
        title=dict(text=title, font=dict(size=14, color='#ffffff')),
        xaxis_title="",
        yaxis_title=yaxis_title,
        height=height,
        margin=dict(l=50, r=20, t=60, b=40),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=11, color="#c8c8c8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(26, 26, 36, 0.95)',
        font=dict(family="Segoe UI, sans-serif", size=11, color="#c8c8c8"),
        xaxis=dict(gridcolor='rgba(60, 60, 80, 0.3)', showgrid=True, tickformat='%m/%d %H:%M'),
        yaxis=dict(gridcolor='rgba(60, 60, 80, 0.3)', showgrid=True, separatethousands=True, tickfont=dict(size=10)),
        hovermode='x unified',
    )


# =============================================================================
# AZURE AI FOUNDRY STYLE CHARTS
# These charts mimic the monitoring graphs in Azure AI Foundry portal
# =============================================================================

def create_foundry_processed_tokens_chart(metrics: Any) -> go.Figure:
    """
    Create a 'Processed Inference Tokens' chart in Azure AI Foundry style.
    Shows prompt tokens vs completion tokens over time.
    Uses real metric data when available, synthetic otherwise.
    """
    # Need at least one of: prompt_tokens, completion_tokens, or tokens_per_minute
    has_real_prompt = metrics.prompt_tokens and metrics.prompt_tokens.timestamps
    has_real_completion = metrics.completion_tokens and metrics.completion_tokens.timestamps
    has_tpm = metrics.tokens_per_minute and metrics.tokens_per_minute.timestamps

    if not has_real_prompt and not has_real_completion and not has_tpm:
        # Fallback: check if aggregate stats exist for synthetic generation
        if not metrics.tokens_per_minute:
            return None

    fig = go.Figure()

    if has_real_prompt or has_real_completion:
        # ── Real data path ──
        if has_real_prompt:
            fig.add_trace(go.Scatter(
                x=metrics.prompt_tokens.timestamps,
                y=metrics.prompt_tokens.values,
                name='Prompt Tokens',
                line=dict(color='#0078D4', width=1.5),
                fill='tozeroy',
                fillcolor='rgba(0, 120, 212, 0.1)',
                hovertemplate='<b>Prompt Tokens</b><br>%{x}<br>%{y:,.0f} tokens<extra></extra>',
            ))
        if has_real_completion:
            fig.add_trace(go.Scatter(
                x=metrics.completion_tokens.timestamps,
                y=metrics.completion_tokens.values,
                name='Completion Tokens',
                line=dict(color='#8764B8', width=1.5),
                fill='tozeroy',
                fillcolor='rgba(135, 100, 184, 0.1)',
                hovertemplate='<b>Completion Tokens</b><br>%{x}<br>%{y:,.0f} tokens<extra></extra>',
            ))
    elif has_tpm:
        # Only TPM available — show it as total tokens
        fig.add_trace(go.Scatter(
            x=metrics.tokens_per_minute.timestamps,
            y=metrics.tokens_per_minute.values,
            name='Total Tokens/Min',
            line=dict(color='#0078D4', width=1.5),
            fill='tozeroy',
            fillcolor='rgba(0, 120, 212, 0.1)',
            hovertemplate='<b>Tokens/Min</b><br>%{x}<br>%{y:,.0f}<extra></extra>',
        ))
    else:
        # ── Synthetic fallback (demo) ──
        import numpy as np
        np.random.seed(42)
        tpm = metrics.tokens_per_minute
        hours = 24 * 14
        time_points = pd.date_range(end=datetime.now(), periods=hours, freq='h')
        prompt_tokens, completion_tokens = [], []
        for t in time_points:
            hour = t.hour
            multiplier = 1.2 if 9 <= hour <= 17 else (0.9 if 6 <= hour <= 21 else 0.5)
            if t.weekday() >= 5:
                multiplier *= 0.6
            base_tokens = tpm.mean * multiplier * 60
            prompt_tokens.append(max(0, base_tokens * 0.6 + np.random.normal(0, base_tokens * 0.1)))
            completion_tokens.append(max(0, base_tokens * 0.4 + np.random.normal(0, base_tokens * 0.08)))
        fig.add_trace(go.Scatter(x=time_points, y=prompt_tokens, name='Prompt Tokens',
            line=dict(color='#0078D4', width=1.5), fill='tozeroy', fillcolor='rgba(0,120,212,0.1)',
            hovertemplate='<b>Prompt Tokens</b><br>%{x}<br>%{y:,.0f} tokens<extra></extra>'))
        fig.add_trace(go.Scatter(x=time_points, y=completion_tokens, name='Completion Tokens',
            line=dict(color='#8764B8', width=1.5), fill='tozeroy', fillcolor='rgba(135,100,184,0.1)',
            hovertemplate='<b>Completion Tokens</b><br>%{x}<br>%{y:,.0f} tokens<extra></extra>'))

    fig.update_layout(**_foundry_layout("Processed Inference Tokens", "Token Count"))
    return fig


def create_foundry_requests_chart(metrics: Any) -> go.Figure:
    """
    Create a 'Requests' chart in Azure AI Foundry style.
    Shows successful vs failed requests over time.
    Uses real metric data when available, synthetic otherwise.
    """
    has_real_success = metrics.successful_requests and metrics.successful_requests.timestamps
    has_real_throttled = metrics.throttled_requests and metrics.throttled_requests.timestamps
    has_real_rpm = metrics.requests_per_minute and metrics.requests_per_minute.timestamps

    if not has_real_success and not has_real_throttled and not has_real_rpm:
        if not metrics.tokens_per_minute:
            return None

    fig = go.Figure()

    if has_real_success or has_real_throttled:
        # ── Real data path ──
        if has_real_success:
            fig.add_trace(go.Scatter(
                x=metrics.successful_requests.timestamps,
                y=metrics.successful_requests.values,
                name='Successful (2xx)',
                line=dict(color='#107C10', width=1.5),
                fill='tozeroy',
                fillcolor='rgba(16, 124, 16, 0.15)',
                hovertemplate='<b>Successful</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>',
            ))
        if has_real_throttled:
            fig.add_trace(go.Scatter(
                x=metrics.throttled_requests.timestamps,
                y=metrics.throttled_requests.values,
                name='Failed (429)',
                line=dict(color='#D13438', width=1.5),
                fill='tozeroy',
                fillcolor='rgba(209, 52, 56, 0.15)',
                hovertemplate='<b>Throttled</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>',
            ))
    elif has_real_rpm:
        fig.add_trace(go.Scatter(
            x=metrics.requests_per_minute.timestamps,
            y=metrics.requests_per_minute.values,
            name='Total Requests',
            line=dict(color='#107C10', width=1.5),
            fill='tozeroy',
            fillcolor='rgba(16, 124, 16, 0.15)',
            hovertemplate='<b>Requests</b><br>%{x}<br>%{y:,.0f}<extra></extra>',
        ))
    else:
        # ── Synthetic fallback (demo) ──
        import numpy as np
        np.random.seed(43)
        hours = 24 * 14
        time_points = pd.date_range(end=datetime.now(), periods=hours, freq='h')
        throttle_rate = metrics.throttling_rate
        base_requests = metrics.total_requests / hours if metrics.total_requests else 100
        successful, failed = [], []
        for t in time_points:
            hour = t.hour
            multiplier = 1.3 if 9 <= hour <= 17 else (0.85 if 6 <= hour <= 21 else 0.4)
            if t.weekday() >= 5:
                multiplier *= 0.5
            total = max(1, base_requests * multiplier + np.random.normal(0, base_requests * 0.15))
            fail_count = total * throttle_rate * (1 + np.random.random() * 0.5)
            successful.append(max(0, total - fail_count))
            failed.append(max(0, fail_count))
        fig.add_trace(go.Scatter(x=time_points, y=successful, name='Successful (2xx)',
            line=dict(color='#107C10', width=1.5), fill='tozeroy', fillcolor='rgba(16,124,16,0.15)',
            hovertemplate='<b>Successful</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>'))
        fig.add_trace(go.Scatter(x=time_points, y=failed, name='Failed (4xx/5xx)',
            line=dict(color='#D13438', width=1.5), fill='tozeroy', fillcolor='rgba(209,52,56,0.15)',
            hovertemplate='<b>Failed</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>'))

    fig.update_layout(**_foundry_layout("Requests", "Request Count"))
    return fig


def create_foundry_latency_chart(metrics: Any) -> go.Figure:
    """
    Create a 'Latency' chart in Azure AI Foundry style.
    Shows Time to First Token (TTFT) percentiles.
    Uses real metric data when available, synthetic otherwise.
    """
    has_p50 = metrics.time_to_first_byte_p50 and metrics.time_to_first_byte_p50.timestamps
    has_p95 = metrics.time_to_first_byte_p95 and metrics.time_to_first_byte_p95.timestamps
    has_p99 = metrics.time_to_first_byte_p99 and metrics.time_to_first_byte_p99.timestamps

    if not has_p50 and not has_p95 and not has_p99:
        if not metrics.time_to_first_byte_p50:
            return None

    fig = go.Figure()

    if has_p50 or has_p95 or has_p99:
        # ── Real data path ──
        if has_p50:
            fig.add_trace(go.Scatter(
                x=metrics.time_to_first_byte_p50.timestamps,
                y=metrics.time_to_first_byte_p50.values,
                name='TTFT P50',
                line=dict(color='#0078D4', width=1.5),
                hovertemplate='<b>TTFT P50</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>',
            ))
        if has_p95:
            fig.add_trace(go.Scatter(
                x=metrics.time_to_first_byte_p95.timestamps,
                y=metrics.time_to_first_byte_p95.values,
                name='TTFT P95',
                line=dict(color='#C239B3', width=1.5),
                hovertemplate='<b>TTFT P95</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>',
            ))
        if has_p99:
            fig.add_trace(go.Scatter(
                x=metrics.time_to_first_byte_p99.timestamps,
                y=metrics.time_to_first_byte_p99.values,
                name='TTFT P99',
                line=dict(color='#FF8C00', width=1.5),
                hovertemplate='<b>TTFT P99</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>',
            ))
    else:
        # ── Synthetic fallback (demo) ──
        import numpy as np
        np.random.seed(44)
        hours = 24 * 14
        time_points = pd.date_range(end=datetime.now(), periods=hours, freq='h')
        base_ttft = metrics.time_to_first_byte_p50.mean
        base_tbt = base_ttft * 0.15
        ttft_p50, ttft_p95, tbt_p50 = [], [], []
        for t in time_points:
            multiplier = 1.15 if 9 <= t.hour <= 17 else 0.9
            ttft = base_ttft * multiplier + np.random.normal(0, base_ttft * 0.1)
            ttft_p50.append(max(50, ttft))
            ttft_p95.append(max(100, ttft * 1.8 + np.random.normal(0, ttft * 0.15)))
            tbt_p50.append(max(5, base_tbt * multiplier + np.random.normal(0, base_tbt * 0.2)))
        fig.add_trace(go.Scatter(x=time_points, y=ttft_p50, name='TTFT P50',
            line=dict(color='#0078D4', width=1.5),
            hovertemplate='<b>TTFT P50</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>'))
        fig.add_trace(go.Scatter(x=time_points, y=ttft_p95, name='TTFT P95',
            line=dict(color='#C239B3', width=1.5),
            hovertemplate='<b>TTFT P95</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>'))
        fig.add_trace(go.Scatter(x=time_points, y=tbt_p50, name='TBT P50',
            line=dict(color='#00B294', width=1.5, dash='dot'),
            hovertemplate='<b>TBT P50</b><br>%{x}<br>%{y:,.0f} ms<extra></extra>'))

    fig.update_layout(**_foundry_layout("Latency (Time to First Token / Time Between Tokens)", "Latency (ms)"))
    return fig


def create_foundry_throttled_requests_chart(metrics: Any) -> go.Figure:
    """
    Create a 'HTTP 429 Responses' chart in Azure AI Foundry style.
    Shows throttled/rate-limited requests over time.
    Uses real metric data when available, synthetic otherwise.
    """
    has_real = metrics.throttled_requests and metrics.throttled_requests.timestamps

    if not has_real and not metrics.throttled_requests:
        return None

    fig = go.Figure()

    if has_real:
        # ── Real data path ──
        fig.add_trace(go.Scatter(
            x=metrics.throttled_requests.timestamps,
            y=metrics.throttled_requests.values,
            name='429 Rate Limited',
            line=dict(color='#FF8C00', width=1.5),
            fill='tozeroy',
            fillcolor='rgba(255, 140, 0, 0.2)',
            hovertemplate='<b>HTTP 429</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>',
        ))
    else:
        # ── Synthetic fallback (demo) ──
        import numpy as np
        np.random.seed(45)
        hours = 24 * 14
        time_points = pd.date_range(end=datetime.now(), periods=hours, freq='h')
        throttle_rate = metrics.throttling_rate
        base_requests = metrics.total_requests / hours if metrics.total_requests else 100
        throttled = []
        for t in time_points:
            multiplier = 2.0 if 9 <= t.hour <= 17 else (1.0 if 6 <= t.hour <= 21 else 0.2)
            if t.weekday() >= 5:
                multiplier *= 0.3
            throttled.append(max(0, base_requests * throttle_rate * multiplier * (0.5 + np.random.random())))
        fig.add_trace(go.Scatter(x=time_points, y=throttled, name='429 Rate Limited',
            line=dict(color='#FF8C00', width=1.5), fill='tozeroy', fillcolor='rgba(255,140,0,0.2)',
            hovertemplate='<b>HTTP 429</b><br>%{x}<br>%{y:,.0f} requests<extra></extra>'))
        threshold = base_requests * 0.01
        fig.add_trace(go.Scatter(x=[time_points[0], time_points[-1]], y=[threshold, threshold],
            name='1% Threshold', line=dict(color='#D13438', width=1.5, dash='dash'),
            hovertemplate='<b>1% Threshold</b><br>%{y:,.0f} requests<extra></extra>'))

    fig.update_layout(**_foundry_layout("HTTP 429 Responses (Rate Limited)", "Count"))
    return fig


def create_foundry_tokens_per_minute_chart(metrics: Any) -> go.Figure:
    """
    Create a 'Tokens Per Minute' chart in Azure AI Foundry style.
    Shows TPM with capacity line for PTU scenarios.
    Uses real metric data when available, synthetic otherwise.
    """
    if not metrics.tokens_per_minute:
        return None

    tpm = metrics.tokens_per_minute
    has_real = tpm.timestamps and len(tpm.timestamps) > 0

    fig = go.Figure()

    if has_real:
        # ── Real data path ──
        time_points = tpm.timestamps
        tpm_vals = tpm.values

        fig.add_trace(go.Scatter(
            x=time_points,
            y=tpm_vals,
            name='Tokens/Min',
            line=dict(color='#0078D4', width=1.5),
            fill='tozeroy',
            fillcolor='rgba(0, 120, 212, 0.15)',
            hovertemplate='<b>TPM</b><br>%{x}<br>%{y:,.0f}<extra></extra>',
        ))

        # P95 reference line
        fig.add_trace(go.Scatter(
            x=[time_points[0], time_points[-1]],
            y=[tpm.p95, tpm.p95],
            name=f'P95: {tpm.p95:,.0f}',
            line=dict(color='#FFB900', width=1.5, dash='dash'),
            hovertemplate='<b>P95</b><br>%{y:,.0f} TPM<extra></extra>',
        ))

        # Mean reference line
        fig.add_trace(go.Scatter(
            x=[time_points[0], time_points[-1]],
            y=[tpm.mean, tpm.mean],
            name=f'Avg: {tpm.mean:,.0f}',
            line=dict(color='#00B294', width=1.5, dash='dot'),
            hovertemplate='<b>Avg</b><br>%{y:,.0f} TPM<extra></extra>',
        ))
    else:
        # ── Synthetic fallback (demo) ──
        import numpy as np
        np.random.seed(46)
        hours = 24 * 14
        time_points = pd.date_range(end=datetime.now(), periods=hours, freq='h')
        tpm_vals = []
        for t in time_points:
            multiplier = 1.2 if 9 <= t.hour <= 17 else (0.9 if 6 <= t.hour <= 21 else 0.5)
            if t.weekday() >= 5:
                multiplier *= 0.6
            tpm_vals.append(max(0, tpm.mean * multiplier + np.random.normal(0, tpm.std * 0.3)))
        fig.add_trace(go.Scatter(x=time_points, y=tpm_vals, name='Tokens/Min',
            line=dict(color='#0078D4', width=1.5), fill='tozeroy', fillcolor='rgba(0,120,212,0.15)',
            hovertemplate='<b>TPM</b><br>%{x}<br>%{y:,.0f}<extra></extra>'))
        fig.add_trace(go.Scatter(x=[time_points[0], time_points[-1]], y=[tpm.p95, tpm.p95],
            name=f'P95: {tpm.p95:,.0f}', line=dict(color='#FFB900', width=1.5, dash='dash'),
            hovertemplate='<b>P95</b><br>%{y:,.0f} TPM<extra></extra>'))
        fig.add_trace(go.Scatter(x=[time_points[0], time_points[-1]], y=[tpm.mean, tpm.mean],
            name=f'Avg: {tpm.mean:,.0f}', line=dict(color='#00B294', width=1.5, dash='dot'),
            hovertemplate='<b>Avg</b><br>%{y:,.0f} TPM<extra></extra>'))

    fig.update_layout(**_foundry_layout("Tokens Per Minute", "TPM"))
    return fig



# Cost functions are now in ptu_advisor.cost.calculator — imported at top of file.


def create_breakeven_chart(
    cost_curves: pd.DataFrame,
    break_even_tpm: Optional[float],
    user_avg_tpm: float,
    slider_baseline_tpm: float,
    payg_at_slider: float,
    hybrid_at_slider: float,
    payg_blended_rate: float,
) -> go.Figure:
    """Create the interactive break-even visualization with dark theme."""
    fig = go.Figure()
    
    minutes_per_month = 60 * 24 * 30
    
    # Savings fill: green where PTU+Spill < PAYG
    fig.add_trace(go.Scatter(
        x=list(cost_curves["baseline_tpm"]) + list(cost_curves["baseline_tpm"][::-1]),
        y=list(cost_curves["ptu_spill_monthly"]) + list(cost_curves["payg_monthly"][::-1]),
        fill="toself",
        fillcolor="rgba(0, 212, 170, 0.06)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    
    # PAYG line
    fig.add_trace(go.Scatter(
        x=cost_curves["baseline_tpm"],
        y=cost_curves["payg_monthly"],
        name="PAYG",
        line=dict(color="#0078D4", width=2.5, dash="dash"),
        hovertemplate="<b>PAYG</b><br>%{x:,.0f} TPM<br>$%{y:,.0f}/mo<extra></extra>",
    ))
    
    # PTU + Spillover line
    fig.add_trace(go.Scatter(
        x=cost_curves["baseline_tpm"],
        y=cost_curves["ptu_spill_monthly"],
        name="PTU + Spillover",
        line=dict(color="#00d4aa", width=2.5),
        hovertemplate="<b>PTU + Spillover</b><br>%{x:,.0f} TPM<br>$%{y:,.0f}/mo<extra></extra>",
    ))
    
    y_max = max(cost_curves["payg_monthly"].max(), cost_curves["ptu_spill_monthly"].max()) * 1.1
    
    # Break-even marker
    if break_even_tpm is not None and break_even_tpm > 0:
        be_cost = break_even_tpm * minutes_per_month / 1_000_000 * payg_blended_rate
        fig.add_vline(x=break_even_tpm, line_dash="dot", line_color="#FFB900", line_width=2, opacity=0.8)
        fig.add_annotation(
            x=break_even_tpm, y=be_cost,
            text=f"<b>Break-even</b><br>{break_even_tpm:,.0f} TPM<br>${be_cost:,.0f}/mo",
            showarrow=True, arrowhead=2, arrowcolor="#FFB900", arrowwidth=1.5,
            font=dict(color="#FFB900", size=11, family="DM Sans"),
            bgcolor="rgba(26,26,36,0.95)", bordercolor="#FFB900", borderwidth=1, borderpad=6,
            ax=40, ay=-50,
        )
    
    # "Your avg usage" marker
    fig.add_vline(x=user_avg_tpm, line_dash="solid", line_color="rgba(255,255,255,0.3)", line_width=1)
    fig.add_annotation(
        x=user_avg_tpm, y=y_max * 0.92,
        text=f"Your avg<br>{user_avg_tpm:,.0f} TPM",
        showarrow=False,
        font=dict(color="#b8b8c8", size=10, family="DM Sans"),
        bgcolor="rgba(26,26,36,0.8)", bordercolor="rgba(255,255,255,0.2)", borderwidth=1, borderpad=4,
    )
    
    # Slider position marker (current baseline)
    fig.add_vline(x=slider_baseline_tpm, line_dash="solid", line_color="#00d4aa", line_width=2, opacity=0.6)
    
    # Points at slider position
    fig.add_trace(go.Scatter(
        x=[slider_baseline_tpm, slider_baseline_tpm],
        y=[payg_at_slider, hybrid_at_slider],
        mode="markers",
        marker=dict(size=[10, 12], color=["#0078D4", "#00d4aa"], line=dict(width=2, color="#1a1a24")),
        showlegend=False,
        hovertemplate=["PAYG: $%{y:,.0f}/mo<extra></extra>", "PTU+Spill: $%{y:,.0f}/mo<extra></extra>"],
    ))
    
    # What-if annotation at slider position (#7)
    diff = payg_at_slider - hybrid_at_slider
    if abs(diff) > 0:
        if diff > 0:
            wi_text = f"<b>Your pick</b><br>Save ${diff:,.0f}/mo"
            wi_color = "#00d4aa"
        else:
            wi_text = f"<b>Your pick</b><br>+${abs(diff):,.0f}/mo"
            wi_color = "#ff8c00"
        fig.add_annotation(
            x=slider_baseline_tpm, y=hybrid_at_slider,
            text=wi_text,
            showarrow=True, arrowhead=2, arrowcolor=wi_color, arrowwidth=1.5,
            font=dict(color=wi_color, size=11, family="DM Sans"),
            bgcolor="rgba(26,26,36,0.95)", bordercolor=wi_color, borderwidth=1, borderpad=6,
            ax=-60, ay=40,
        )
    
    # Layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,26,36,0.3)",
        xaxis_title="Sustained TPM (Baseline)",
        yaxis_title="Monthly Cost ($)",
        yaxis_tickformat="$,.0f",
        xaxis_tickformat=",.0f",
        height=380,
        margin=dict(l=60, r=20, t=30, b=50),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
            font=dict(size=12, family="DM Sans", color="#b8b8c8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        font=dict(family="DM Sans", color="#b8b8c8"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
    )
    
    return fig



# =============================================================================
# Session State Initialization
# =============================================================================
if 'analysis_started' not in st.session_state:
    st.session_state['analysis_started'] = False
if 'focus_topic' not in st.session_state:
    st.session_state['focus_topic'] = "Cost Reduction"
if 'selected_scenario' not in st.session_state:
    st.session_state['selected_scenario'] = "cost-high-volume"
if 'analysis_period' not in st.session_state:
    st.session_state['analysis_period'] = 14

# =============================================================================
# Welcome/Setup Page (shown before analysis)
# =============================================================================
if not st.session_state['analysis_started']:
    # Clean header - no glow, no oversized emoji
    st.markdown("""
    <div style="text-align: center; padding: 46px 0 24px 0;">
        <h1 style="
            font-family: 'DM Sans', sans-serif;
            font-size: 2.65rem;
            font-weight: 700;
            margin: 0 0 8px 0;
            color: #f2f6ff;
            letter-spacing: -0.02em;
            text-wrap: balance;
        ">PTU Advisor</h1>
        <p style="
            font-family: 'DM Sans', sans-serif;
            font-size: 1.1rem;
            color: #9ca7c5;
            margin: 0;
            letter-spacing: 0.01em;
        ">Analyze your Foundry deployments. Get a clear PTU vs PAYG recommendation.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    
    # Three-column layout for setup
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Step 1: What's your focus?
        st.markdown("### Step 1: What's Your Focus?")
        st.caption("Select one primary concern — the analysis will focus on this topic")
        
        focus_options = list(FOCUS_TOPICS.keys())
        
        focus_topic = st.radio(
            "What's your primary concern?",
            options=focus_options,
            index=focus_options.index(st.session_state.get('focus_topic', 'Cost Reduction')),
            format_func=lambda x: x,
            help="""**Your focus shapes the entire analysis.**\n\n"
                "• **Cost Reduction** — is PTU cheaper than PAYG at my usage level?\n"
                "• **Throttling & Reliability** — are HTTP 429 errors hurting my users?\n"
                "• **Latency Optimization** — can dedicated capacity improve response times?\n"
                "• **Predictable Billing** — do I need fixed monthly costs for budgeting?\n"
                "• **Guaranteed Capacity** — do I need reserved GPU capacity for SLAs?""",
            label_visibility="collapsed"
        )
        st.session_state['focus_topic'] = focus_topic
        
        # Show focus tagline
        focus_info = FOCUS_TOPICS.get(focus_topic, {})
        st.caption(f"*{focus_info.get('tagline', '')}*")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Step 2: Data Source
        st.markdown("### Step 2: Select Data Source")
        
        mode = st.radio(
            "Choose mode",
            ["Connect to Azure", "Demo Mode (simulated data)"],
            index=0,
            label_visibility="collapsed"
        )
        st.session_state['data_source_mode'] = mode
        
        if "Demo Mode" in mode:
            # Build scenario options filtered by selected focus topic
            focus_scenarios = FOCUS_TOPICS.get(focus_topic, {}).get("scenarios", {})
            scenario_options = {
                scenario.value: label
                for scenario, label in focus_scenarios.items()
            }
            
            # If current selection is not in the filtered list, reset to first option
            current_scenario = st.session_state.get('selected_scenario', '')
            if current_scenario not in scenario_options and scenario_options:
                current_scenario = list(scenario_options.keys())[0]
                st.session_state['selected_scenario'] = current_scenario
            
            selected_scenario = st.selectbox(
                "Select demo scenario",
                options=list(scenario_options.keys()),
                format_func=lambda x: scenario_options.get(x, x),
                index=list(scenario_options.keys()).index(current_scenario) if current_scenario in scenario_options else 0,
                help=f"Each scenario demonstrates a different use case for **{focus_topic}**.\n\n"
                     "Select a scenario to see how the analysis applies to that workload pattern."
            )
            st.session_state['selected_scenario'] = selected_scenario

            # Default reservation type for new sessions
            if 'ptu_reservation_type' not in st.session_state:
                st.session_state['ptu_reservation_type'] = 'Monthly Commitment (Estimated 64% off)'

            # Show scenario description
            scenario_enum = DemoScenario(selected_scenario)
            scenario_config = SCENARIOS.get(scenario_enum)
            if scenario_config:
                st.info(f"**{scenario_config.name}**: {scenario_config.description}")
        else:
            # ── Live Azure Connection — Auto-Discovery ──
            try:
                disc = _import_discovery()
                if not disc.azure_sdk_available():
                    raise ImportError("sdk")
            except (ImportError, Exception):
                st.warning(
                    "**Azure SDK packages are required for live connection.** Run:\n\n"
                    "`pip install azure-identity azure-mgmt-subscription "
                    "azure-mgmt-cognitiveservices azure-mgmt-monitor`"
                )
                disc = None  # signal to skip the rest

            if disc is not None:
                # --- Step A: Authenticate ---
                cred = st.session_state.get('_azure_credential')
                user_info = st.session_state.get('_azure_user_info')

                if cred is None:
                    with st.spinner("Authenticating with Azure..."):
                        try:
                            cred, user_info = disc.authenticate()
                            st.session_state['_azure_credential'] = cred
                            st.session_state['_azure_user_info'] = user_info
                        except Exception as auth_err:
                            st.error(
                                f"**Authentication failed.** Please run `az login` in your terminal and refresh.\n\n"
                                f"`{auth_err}`"
                            )
                            cred = None

                if cred is not None and user_info is not None:
                    st.success(f"Signed in as **{user_info.display_name}** ({user_info.email})")

                    # --- Step B: Subscription picker ---
                    @st.cache_data(ttl=300, show_spinner=False)
                    def _cached_list_subs(cred_id: str):
                        """List subscriptions (cache keyed on user identity)."""
                        _d = _import_discovery()
                        _c = st.session_state['_azure_credential']
                        return _d.list_subscriptions(_c)

                    subs = _cached_list_subs(user_info.email or user_info.display_name)

                    if not subs:
                        st.warning("No Azure subscriptions found for your account.")
                    else:
                        sub_labels = [s.label for s in subs]
                        sub_idx = st.selectbox(
                            "Subscription",
                            options=range(len(subs)),
                            format_func=lambda i: sub_labels[i],
                            key='_azure_sub_idx',
                            help="Select the Azure subscription containing your AI Services account.",
                        )
                        chosen_sub = subs[sub_idx]
                        st.session_state['azure_subscription'] = chosen_sub.subscription_id

                        # --- Step C: Account picker ---
                        @st.cache_data(ttl=300, show_spinner="Discovering AI accounts...")
                        def _cached_list_accounts(cred_id: str, sub_id: str):
                            _d = _import_discovery()
                            _c = st.session_state['_azure_credential']
                            return _d.list_ai_accounts(_c, sub_id)

                        accounts = _cached_list_accounts(
                            user_info.email or user_info.display_name,
                            chosen_sub.subscription_id,
                        )

                        if not accounts:
                            st.warning("No AI Services / OpenAI accounts found in this subscription.")
                        else:
                            acct_labels = [a.label for a in accounts]
                            account_options = ["All discovered accounts (subscription-wide)"] + acct_labels
                            acct_choice = st.selectbox(
                                "AI Services Account",
                                options=account_options,
                                key='_azure_acct_choice',
                                help="Select one account or use the default to aggregate across all discovered accounts in this subscription.",
                            )
                            if acct_choice == "All discovered accounts (subscription-wide)":
                                selected_accounts = tuple((a.resource_group, a.name) for a in accounts)
                                st.session_state['azure_selected_accounts'] = selected_accounts
                                st.session_state['azure_resource_group'] = ""
                                st.session_state['azure_workspace'] = "__ALL__"
                                st.session_state['azure_selected_deployment'] = ""
                                st.session_state['azure_selected_deployment_label'] = ""
                            else:
                                acct_idx = acct_labels.index(acct_choice)
                                chosen_acct = accounts[acct_idx]
                                selected_accounts = ((chosen_acct.resource_group, chosen_acct.name),)
                                st.session_state['azure_selected_accounts'] = selected_accounts
                                st.session_state['azure_resource_group'] = chosen_acct.resource_group
                                st.session_state['azure_workspace'] = chosen_acct.name

                            # --- Step D: Show deployment summary (informational) ---
                            @st.cache_data(ttl=120, show_spinner="Loading deployments...")
                            def _cached_list_deployments(cred_id: str, sub_id: str, rg: str, acct: str):
                                _d = _import_discovery()
                                _c = st.session_state['_azure_credential']
                                return _d.list_deployments(_c, sub_id, rg, acct)

                            if len(selected_accounts) > 1:
                                st.markdown(f"**Accounts included** ({len(selected_accounts)} found)")
                                st.caption(
                                    "Metrics will be aggregated across **all deployments** in **all discovered accounts** in this subscription."
                                )
                                st.session_state['azure_selected_deployment'] = ""
                                st.session_state['azure_selected_deployment_label'] = ""
                                st.session_state['_azure_deployments'] = []
                                for rg_name, acct_name in selected_accounts[:8]:
                                    st.markdown(f"- `{acct_name}` ({rg_name})")
                                if len(selected_accounts) > 8:
                                    st.caption(f"…and {len(selected_accounts) - 8} more accounts")
                            else:
                                deployments = _cached_list_deployments(
                                    user_info.email or user_info.display_name,
                                    chosen_sub.subscription_id,
                                    selected_accounts[0][0],
                                    selected_accounts[0][1],
                                )

                                if not deployments:
                                    st.warning("No model deployments found in this account.")
                                else:
                                    # Deployment scope selector
                                    deployment_options = [dep.name for dep in deployments]
                                    dep_state_key = (
                                        f"_azure_dep_choice::{selected_accounts[0][0]}::{selected_accounts[0][1]}"
                                    )
                                    if (
                                        dep_state_key not in st.session_state
                                        or st.session_state[dep_state_key] not in deployment_options
                                    ):
                                        st.session_state[dep_state_key] = deployment_options[0]
                                    selected_label = st.radio(
                                        "Deployment to analyze",
                                        options=deployment_options,
                                        key=dep_state_key,
                                        help="Choose the specific deployment to analyze.",
                                    )
                                    st.session_state['azure_selected_deployment_label'] = selected_label
                                    st.session_state['azure_selected_deployment'] = selected_label

                                    # Show deployments summary
                                    st.markdown(f"**Deployments** ({len(deployments)} found)")
                                    st.caption(
                                        "PTU quota is **model-independent** and shared across all deployments. "
                                        "Metrics are filtered to the deployment selected above."
                                    )

                                    # Store deployments summary in session state
                                    st.session_state['_azure_deployments'] = deployments

                                    # Render summary cards for each deployment
                                    for dep in deployments:
                                        is_ptu = dep.sku_type.lower() in ('provisionedmanaged', 'provisioned',
                                                                           'globalprovisionedmanaged', 'datazoneprovisionedmanaged')

                                        badge_color = '#00d4aa' if is_ptu else '#0078D4'
                                        badge_text = dep.sku_type

                                        capacity_text = (
                                            f"{dep.sku_capacity} PTUs" if is_ptu and dep.sku_capacity
                                            else f"{dep.sku_capacity:,} TPM" if dep.sku_capacity
                                            else "—"
                                        )
                                        ptu_hint = (
                            '<span style="color:#00d4aa; font-size:12px;">PTU</span>'
                                        )

                                        st.markdown(f"""
                                        <div style="
                                            border: 1px solid #2a2a3a;
                                            border-radius: 10px;
                                            padding: 10px 16px;
                                            margin-bottom: 6px;
                                            background: rgba(26, 26, 36, 0.95);
                                        ">
                                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                                <span style="font-weight:600; color:#fff; font-size:14px;">{dep.name}</span>
                                                <span style="
                                                    background: {badge_color}22;
                                                    color: {badge_color};
                                                    padding: 2px 10px;
                                                    border-radius: 12px;
                                                    font-size: 11px;
                                                    font-weight: 500;
                                                ">{badge_text}</span>
                                            </div>
                                            <div style="color:#8b8b9a; font-size:12px; margin-top:3px;">
                                                Model: <b style="color:#c8c8d0;">{dep.model}</b>
                                                &nbsp;•&nbsp; Capacity: <b style="color:#c8c8d0;">{capacity_text}</b>
                                                &nbsp; {ptu_hint}
                                            </div>
                                        </div>
                                        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Step 3: Settings (collapsed by default)
        with st.expander("Advanced Settings (Optional)", expanded=False):
            st.caption("Fine-tune the analysis parameters")
            
            col_slider1, col_slider2 = st.columns(2)
            
            with col_slider1:
                analysis_period = st.slider(
                    "Analysis Period",
                    min_value=1,
                    max_value=30,
                    value=st.session_state.get('analysis_period', 14),
                    help="Number of days to analyze for usage patterns",
                    format="%d days"
                )
                st.session_state['analysis_period'] = analysis_period
            
            with col_slider2:
                safety_margin = st.slider(
                    "PTU Safety Margin",
                    min_value=1.0,
                    max_value=2.0,
                    value=st.session_state.get('safety_margin', 1.2),
                    step=0.1,
                    help="Buffer applied to peak usage for PTU sizing (1.2 = 20% headroom)",
                    format="%.1fx"
                )
                st.session_state['safety_margin'] = safety_margin
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Big Analyze Button
        st.markdown("### Step 3: Run Analysis")
        
        if st.button("Analyze My Account", type="primary", use_container_width=True):
            if not focus_topic:
                st.error("Please select a focus topic!")
            elif "Connect to Azure" in mode:
                # Validate that auto-discovery completed (at least one account selected)
                _selected = st.session_state.get('azure_selected_accounts', ())
                if not _selected:
                    st.error("Please select a subscription and AI Services account(s) above.")
                elif len(_selected) == 1 and not st.session_state.get('azure_selected_deployment', ''):
                    st.error("Please select a deployment to analyze.")
                else:
                    st.session_state['analysis_started'] = True
                    st.rerun()
            else:
                st.session_state['analysis_started'] = True
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Footer links
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; font-size: 14px; color: #888;">
            <a href="https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput" target="_blank">PTU Documentation</a> • 
            <a href="https://learn.microsoft.com/azure/ai-services/openai/how-to/provisioned-throughput-onboarding" target="_blank">Onboarding Guide</a> • 
            <a href="https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/" target="_blank">Pricing</a>
        </div>
        """, unsafe_allow_html=True)

else:
    # =============================================================================
    # Minimal Sidebar (only shown after analysis starts)
    # =============================================================================
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/azure-1.png", width=50)
        st.title("PTU Advisor")
        
        st.divider()
        
        # Show current focus
        current_focus = st.session_state.get('focus_topic', 'Cost Reduction')
        focus_icon = FOCUS_TOPICS.get(current_focus, {}).get('icon', '')
        st.markdown(f"**Focus:** {current_focus}")
        
        # Show data source info
        _sidebar_mode = st.session_state.get('data_source_mode', 'Connect to Azure')
        if 'Connect to Azure' in _sidebar_mode:
            _sidebar_acct = st.session_state.get('azure_workspace', '')
            _sidebar_deps = st.session_state.get('_azure_deployments', [])
            _sidebar_deployment = st.session_state.get('azure_selected_deployment', '')
            _sidebar_user = st.session_state.get('_azure_user_info')
            st.markdown(f"**Source:** Live Azure")
            _sidebar_selected = st.session_state.get('azure_selected_accounts', ())
            is_subscription_aggregate = (
                (_sidebar_selected and len(_sidebar_selected) > 1)
                or (_sidebar_acct == "__ALL__")
            )
            if is_subscription_aggregate:
                account_count = len(_sidebar_selected) if _sidebar_selected else 0
                if account_count > 0:
                    st.markdown(f"**Accounts:** {account_count} (subscription aggregate)")
                else:
                    st.markdown("**Scope:** Subscription aggregate")
            elif _sidebar_acct:
                st.markdown(f"**Account:** `{_sidebar_acct}`")

            if not is_subscription_aggregate and _sidebar_deployment:
                st.markdown(f"**Deployment:** `{_sidebar_deployment}`")

            if not is_subscription_aggregate and _sidebar_deps:
                st.markdown(f"**Deployments:** {len(_sidebar_deps)} (aggregated)")
            if _sidebar_user:
                st.caption(f"Signed in as {_sidebar_user.display_name}")
        else:
            st.markdown("**Source:** Demo Data")
        
        st.divider()
        
        # Change settings button
        if st.button("New Analysis", use_container_width=True):
            st.session_state['analysis_started'] = False
            st.rerun()
        
        st.divider()
        
        # Quick links
        st.caption("Resources")
        st.markdown("""
        - [PTU Docs](https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput)
        - [Pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/)
        """)
    
    # =============================================================================
    # Main Dashboard Content - Single Page Story Flow
    # =============================================================================
    
    # Get stored values
    selected_scenario = st.session_state.get('selected_scenario', 'ptu-recommended')
    analysis_period = st.session_state.get('analysis_period', 14)
    data_source_mode = st.session_state.get('data_source_mode', 'Connect to Azure')

    # Generate demo data
    @st.cache_data(ttl=300)
    def load_demo_data(scenario: str):
        """Load and cache demo data."""
        scenario_enum = DemoScenario(scenario)
        metrics, scenario_config = generate_demo_metrics(scenario_enum)
        
        analysis_config = AnalysisConfig(
            resource_group="demo-rg",
            workspace="demo-workspace",
            deployment=metrics.deployment_name,
            lookback_days=14
        )
        
        engine = DecisionEngine(analysis_config)
        analysis = engine.analyze(metrics)
        
        return metrics, analysis, scenario_config

    @st.cache_data(ttl=300, show_spinner=False)
    def load_live_data(
        subscription_id: str | None,
        lookback_days: int,
        selected_accounts: tuple[tuple[str, str], ...],
        selected_deployment: str,
    ):
        """Fetch real metrics from Azure and aggregate across selected accounts.

        Each account is queried at account scope (all deployments in that account),
        then results are merged to a subscription-wide consolidated view.
        """
        from ptu_advisor.metrics.collector import MetricsCollector
        from ptu_advisor.auth import get_azure_credential
        from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries
        from datetime import datetime

        def _merge_series(series_list: list[TimeSeries], mode: str = "sum") -> TimeSeries | None:
            if not series_list:
                return None
            merged: dict[str, list[float]] = {}
            ts_lookup: dict[str, datetime] = {}
            for series in series_list:
                for ts, val in zip(series.timestamps, series.values):
                    key = ts.isoformat()
                    merged.setdefault(key, []).append(float(val))
                    ts_lookup[key] = ts

            keys_sorted = sorted(merged.keys())
            timestamps = [ts_lookup[k] for k in keys_sorted]
            if mode == "avg":
                values = [sum(merged[k]) / len(merged[k]) for k in keys_sorted]
            else:
                values = [sum(merged[k]) for k in keys_sorted]

            first = series_list[0]
            return TimeSeries(
                timestamps=timestamps,
                values=values,
                metric_name=first.metric_name,
                unit=first.unit,
            )

        def _aggregate_metrics(metrics_list: list[DeploymentMetrics]) -> DeploymentMetrics:
            first = metrics_list[0]
            aggregated = DeploymentMetrics(
                deployment_name=f"subscription:{subscription_id or 'default'}",
                model_name="aggregated",
                start_time=first.start_time,
                end_time=first.end_time,
            )

            sum_fields = [
                "requests_per_minute",
                "successful_requests",
                "throttled_requests",
                "prompt_tokens",
                "completion_tokens",
                "tokens_per_minute",
            ]
            avg_fields = [
                "time_to_first_byte_p50",
                "time_to_first_byte_p95",
                "time_to_first_byte_p99",
                "ptu_utilization",
            ]

            for field_name in sum_fields:
                series_list = [getattr(m, field_name) for m in metrics_list if getattr(m, field_name)]
                setattr(aggregated, field_name, _merge_series(series_list, mode="sum"))

            for field_name in avg_fields:
                series_list = [getattr(m, field_name) for m in metrics_list if getattr(m, field_name)]
                setattr(aggregated, field_name, _merge_series(series_list, mode="avg"))

            if aggregated.tokens_per_minute:
                aggregated.timestamps = list(aggregated.tokens_per_minute.timestamps)
            elif aggregated.requests_per_minute:
                aggregated.timestamps = list(aggregated.requests_per_minute.timestamps)

            return aggregated

        # Prefer cached credential from discovery; fall back to fresh auth.
        credential = st.session_state.get('_azure_credential') or get_azure_credential()

        collected: list[DeploymentMetrics] = []
        deployment_filter = selected_deployment if len(selected_accounts) == 1 and selected_deployment else ""
        for rg_name, acct_name in selected_accounts:
            config = AnalysisConfig(
                resource_group=rg_name,
                workspace=acct_name,
                deployment=deployment_filter,
                subscription_id=subscription_id,
                lookback_days=lookback_days,
            )
            collector = MetricsCollector(credential, config)
            collected.append(collector.collect())

        if not collected:
            raise RuntimeError("No metrics could be collected from selected Azure accounts.")

        if len(collected) == 1:
            metrics = collected[0]
            engine_config = AnalysisConfig(
                resource_group=selected_accounts[0][0],
                workspace=selected_accounts[0][1],
                deployment=deployment_filter,
                subscription_id=subscription_id,
                lookback_days=lookback_days,
            )
        else:
            metrics = _aggregate_metrics(collected)
            engine_config = AnalysisConfig(
                resource_group="subscription-aggregate",
                workspace=f"{len(selected_accounts)}-accounts",
                deployment="",
                subscription_id=subscription_id,
                lookback_days=lookback_days,
            )

        engine = DecisionEngine(engine_config)
        analysis = engine.analyze(metrics)

        return metrics, analysis

    # Load data — route based on selected mode
    scenario_cfg = None  # only set in demo mode

    if "Demo Mode" in data_source_mode:
        with st.spinner("Analyzing deployment metrics..."):
            metrics, analysis, scenario_cfg = load_demo_data(selected_scenario)
    else:
        # Live Azure connection
        live_rg = st.session_state.get('azure_resource_group', '')
        live_ws = st.session_state.get('azure_workspace', '')
        live_sub = st.session_state.get('azure_subscription', '') or None
        selected_accounts = tuple(st.session_state.get('azure_selected_accounts', ()))
        selected_deployment = st.session_state.get('azure_selected_deployment', '')

        if not selected_accounts:
            if live_rg and live_ws:
                selected_accounts = ((live_rg, live_ws),)
            else:
                st.error(
                    "Resource discovery did not complete. Please go back to the welcome page, "
                    "select **Connect to Azure**, and pick a subscription and account(s)."
                )
                st.stop()

        try:
            if len(selected_accounts) > 1:
                loading_msg = f"Fetching metrics from Azure for **{len(selected_accounts)} accounts** (all deployments)..."
            else:
                if selected_deployment:
                    loading_msg = (
                        f"Fetching metrics from Azure for **{selected_accounts[0][1]}** / "
                        f"deployment **{selected_deployment}**..."
                    )
                else:
                    loading_msg = f"Fetching metrics from Azure for **{selected_accounts[0][1]}** (all deployments)..."
            with st.spinner(loading_msg):
                metrics, analysis = load_live_data(
                    subscription_id=live_sub,
                    lookback_days=analysis_period,
                    selected_accounts=selected_accounts,
                    selected_deployment=selected_deployment,
                )
        except Exception as e:
            st.error(
                f"Failed to connect to Azure: {e}"
            )
            st.info(
                "**Troubleshooting:**\n"
                "1. Run `az login` in your terminal\n"
                "2. Verify the Subscription and account access\n"
                "3. Ensure you have **Reader** + **Monitoring Reader** roles on the resource\n"
                "4. Check that the Subscription ID is correct (or leave blank for default)"
            )
            st.stop()
    
    # Import for comparison
    from ptu_advisor.metrics.models import Recommendation

    # =================================================================
    # Calculate all metrics upfront
    # =================================================================
    avg_tpm = metrics.tokens_per_minute.mean if metrics.tokens_per_minute else 0
    peak_tpm = metrics.tokens_per_minute.p95 if metrics.tokens_per_minute else 0
    throttle_rate = metrics.throttling_rate
    throttle_pct = throttle_rate * 100
    
    # Cost calculations with formulas
    # Azure OpenAI Pricing (January 2026): https://azure.microsoft.com/en-us/pricing/details/azure-openai/
    monthly_tokens = avg_tpm * 60 * 24 * 30
    
    # PAYG pricing: GPT-4o Global = $2.50/1M input + $10/1M output
    # Using blended rate assuming ~30% output tokens
    payg_input_rate = 2.50   # $ per 1M input tokens
    payg_output_rate = 10.0  # $ per 1M output tokens
    output_ratio = 0.30      # Assume 30% of tokens are output
    payg_blended_rate = (payg_input_rate * (1 - output_ratio) + payg_output_rate * output_ratio)  # $/1M tokens
    payg_rate = payg_blended_rate / 1000  # Convert to $ per 1K tokens
    
    payg_base = (monthly_tokens / 1_000_000) * payg_blended_rate
    
    # Throttling cost: each throttled request gets retried (paying tokens again)
    # plus the hidden cost of degraded UX, increased latency from retries, and lost requests.
    # Model: retry_overhead = base_cost × throttle_rate / (1 - throttle_rate)
    # This captures the geometric series of retries: if 5% fail, ~5.3% of total cost is wasted on retries
    # We add an additional "opportunity cost" multiplier for business impact of failures
    if throttle_rate > 0.01:
        retry_overhead = payg_base * (throttle_rate / (1 - throttle_rate))
        # Opportunity cost: failed requests that aren't retried, degraded UX
        # Scale from 1x at 1% to 5x at 20%+ throttling
        opportunity_multiplier = min(5.0, 1.0 + (throttle_rate * 20))
        throttle_impact = retry_overhead * opportunity_multiplier
    else:
        throttle_impact = 0
    payg_total = payg_base + throttle_impact
    
    # PTU capacity per unit (model-specific, using GPT-4o default)
    ptu_capacity = 2500  # TPM per PTU for GPT-4o
    
    # PTU Provisioned pricing (GPT-4o Global, Azure pricing Feb 2026)
    # Hourly (no commitment): $1.00/PTU-hour  → $720/PTU-month
    # Monthly commitment:     $260/PTU-month  → ~$0.361/PTU-hour (64% off)
    # 1-Year commitment:      $2,652/PTU-year → $221/PTU-month   (69% off)
    ptu_hourly = 1.00  # $ per PTU-hour (Global, no commitment)
    
    # Get reservation type from session state (default to monthly commitment)
    reservation_type = st.session_state.get('ptu_reservation_type', 'Monthly Commitment (Estimated 64% off)')
    if reservation_type == '1-Year Commitment (Estimated 69% off)':
        # $2,652/year = $221/month; $221/$720 = 0.307
        reservation_discount = 0.307
        reservation_discount_pct = 69
    elif reservation_type == 'Monthly Commitment (Estimated 64% off)':
        # $260/month; $260/$720 = 0.361
        reservation_discount = 0.361
        reservation_discount_pct = 64
    else:
        # Hourly (no commitment) = full list price
        reservation_discount = 1.0
        reservation_discount_pct = 0
    
    # Get baseline percentile from session state (default to P75)
    baseline_pctl = st.session_state.get('ptu_baseline_percentile', 75)
    baseline_label = f"P{baseline_pctl}" if baseline_pctl > 0 else "Min PTU (15)"
    
    # =================================================================
    # SPILLOVER STRATEGY: Size PTU to baseline, let peaks spill to PAYG
    # Reference: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management
    # =================================================================
    
    # Get raw TPM values for spillover calculation
    tpm_values = list(metrics.tokens_per_minute.values) if metrics.tokens_per_minute else []
    
    # Calculate spillover costs using selected baseline percentile
    spillover = calculate_spillover_cost(
        tpm_values=tpm_values,
        baseline_percentile=baseline_pctl,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_rate_per_1k=payg_rate,
        reservation_discount=reservation_discount
    )
    
    # Extract spillover results
    baseline_tpm = spillover["baseline_tpm"]
    baseline_ptu = spillover["baseline_ptu"]
    ptu_capacity_tpm = spillover["ptu_capacity_tpm"]
    spillover_tokens_monthly = spillover["spillover_tokens_monthly"]
    spillover_cost = spillover["spillover_cost"]
    ptu_baseline_cost = spillover["ptu_monthly_cost"]
    hybrid_total = spillover["total_hybrid_cost"]
    spillover_pct = spillover["spillover_pct"]
    avg_spillover_tpm = spillover["avg_spillover_tpm"]
    
    # Also calculate full PTU cost (sized to peak) for comparison
    ptu_needed_full = max(15, int((peak_tpm * 1.2 / ptu_capacity) + 0.5))
    ptu_needed_full = ((ptu_needed_full + 4) // 5) * 5  # Round to 5s
    ptu_monthly_full = ptu_needed_full * ptu_hourly * 24 * 30
    ptu_committed_cost = ptu_monthly_full * reservation_discount
    
    # Effective PTU cost based on reservation type
    ptu_effective_cost = ptu_committed_cost
    
    # Use hybrid (spillover) strategy as the recommended PTU approach
    # The ptu_needed now refers to the baseline-sized PTU for spillover
    ptu_needed = baseline_ptu
    
    # Savings comparison: PAYG vs Hybrid (not vs full PTU)
    savings = payg_total - hybrid_total
    savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0
    
    # Recommendation styling - dark theme colors
    if analysis.recommendation == Recommendation.PTU_RECOMMENDED:
        rec_color, rec_icon, rec_text, rec_bg = "#00d4aa", "PTU", "PTU RECOMMENDED", "rgba(0, 212, 170, 0.1)"
    elif analysis.recommendation == Recommendation.PTU_NOT_RECOMMENDED:
        rec_color, rec_icon, rec_text, rec_bg = "#0078d4", "PAYG", "STAY WITH PAYG", "rgba(0, 120, 212, 0.1)"
    else:
        rec_color, rec_icon, rec_text, rec_bg = "#ffaa00", "—", "NEEDS MORE DATA", "rgba(255, 170, 0, 0.1)"

    # =================================================================
    # SECTION 1: YOUR USAGE
    # =================================================================
    _scope_accounts = tuple(st.session_state.get('azure_selected_accounts', ()))
    _scope_deployment = st.session_state.get('azure_selected_deployment', '')
    _is_demo = "Demo Mode" in data_source_mode
    if _is_demo:
        usage_subtitle = "Metrics for the selected demo scenario"
        usage_caption = (
            "These four numbers summarise the scenario workload profile. "
            "Hover the \u24d8 icons for detailed explanations of each metric."
        )
    elif _scope_accounts and len(_scope_accounts) > 1:
        usage_subtitle = f"Aggregated metrics across {len(_scope_accounts)} selected accounts"
        usage_caption = (
            "These four numbers summarise total workload across all selected accounts and deployments. "
            "Hover the \u24d8 icons for detailed explanations of each metric."
        )
    elif _scope_deployment:
        usage_subtitle = f"Metrics for deployment: {_scope_deployment}"
        usage_caption = (
            "These four numbers summarise workload for the selected deployment only. "
            "Hover the \u24d8 icons for detailed explanations of each metric."
        )
    else:
        usage_subtitle = "Aggregated metrics across all deployments in your account"
        usage_caption = (
            "These four numbers summarise your account's total workload across all deployments. "
            "Hover the \u24d8 icons for detailed explanations of each metric."
        )

    render_section_header("Your Usage", usage_subtitle)
    st.caption(usage_caption)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Avg TPM", 
            format_number(avg_tpm),
            help="""**Average Tokens Per Minute**

The mean token throughput across your analysis period.

• Used to estimate monthly token volume for PAYG cost
• Higher values indicate more consistent usage
• Compared against Peak TPM to assess variability

*Formula: Sum of all TPM readings ÷ Number of readings*"""
        )
    with col2:
        st.metric(
            "Peak TPM", 
            format_number(peak_tpm),
            help="""**Peak Tokens Per Minute (P95)**

The 95th percentile of your token throughput - represents your near-maximum usage.

• Used to size PTU capacity (with safety margin)
• P95 chosen over max to exclude outlier spikes
• Lower peak-to-avg ratio = more stable workload

*This is the baseline for PTU sizing calculations*"""
        )
    with col3:
        st.metric(
            "Throttling", 
            f"{throttle_pct:.1f}%", 
            delta="High" if throttle_pct > 1 else "OK",
            delta_color="inverse" if throttle_pct > 1 else "normal",
            help="""**Throttling Rate (HTTP 429s)**

Percentage of requests that were rate-limited by Azure.

• **< 1%** → Healthy, capacity is sufficient
• **1-5%** → Moderate, consider increasing limits
• **> 5%** → High impact, PTU would eliminate this

*High throttling = lost revenue + poor user experience*
*PTU provides guaranteed capacity with zero throttling*"""
        )
    with col4:
        st.metric(
            "Period", 
            f"{analysis_period} days",
            help="""**Analysis Period**

The time window used for this analysis.

• Longer periods capture more usage patterns
• 7-14 days recommended for reliable insights
• Includes weekday/weekend variations

*Adjust in Advanced Settings on welcome page*"""
        )
    
    # =================================================================
    # FOCUS INSIGHT (topic-specific section before cost analysis)
    # =================================================================
    focus_topic = st.session_state.get('focus_topic', 'Cost Reduction')
    focus_icon = FOCUS_TOPICS.get(focus_topic, {}).get('icon', '')
    
    if focus_topic == "Throttling & Reliability":
        render_section_divider("Throttling Impact")
        render_section_header(
            "Throttling Analysis",
            "How HTTP 429 rate-limiting is affecting your deployment's reliability"
        )
        
        t_col1, t_col2 = st.columns([2, 1])
        with t_col1:
            throttle_chart = create_foundry_throttled_requests_chart(metrics)
            if throttle_chart:
                st.plotly_chart(throttle_chart, use_container_width=True, key="focus_throttle_chart")
        
        with t_col2:
            throttled_count = int(metrics.throttled_requests.total) if metrics.throttled_requests else 0
            st.metric("Throttled Requests", f"{throttled_count:,}",
                      help="Total HTTP 429 responses during the analysis period")
            st.metric("Throttling Rate", f"{throttle_pct:.1f}%",
                      help="Percentage of all requests that were rate-limited")
            
            if throttle_pct > 5:
                st.error(
                    f"**Critical:** {throttle_pct:.1f}% of requests are being rate-limited. "
                    f"That's approximately **{throttled_count:,} failed interactions**. "
                    "Each 429 error means a user saw an error or experienced a delay."
                )
            elif throttle_pct > 1:
                st.warning(
                    f"**Moderate:** {throttle_pct:.1f}% throttling is impacting reliability. "
                    "Users may experience intermittent errors during peak hours."
                )
            else:
                st.success(
                    f"**Healthy:** {throttle_pct:.1f}% throttling is within acceptable limits. "
                    "Current PAYG quota handles your workload well."
                )
        
        # Show requests breakdown
        requests_chart = create_foundry_requests_chart(metrics)
        if requests_chart:
            st.plotly_chart(requests_chart, use_container_width=True, key="focus_requests_chart")
        
        if throttle_pct > 1:
            st.info(
                "**PTU eliminates throttling** by providing dedicated capacity. "
                "With PTU, your deployment has reserved throughput — no more competing "
                "for shared resources during peak hours."
            )
    
    elif focus_topic == "Latency Optimization":
        render_section_divider("Latency Impact")
        render_section_header(
            "Latency Analysis",
            "Response time consistency and SLA compliance on shared PAYG infrastructure"
        )
        
        l_col1, l_col2 = st.columns([2, 1])
        with l_col1:
            latency_chart = create_foundry_latency_chart(metrics)
            if latency_chart:
                st.plotly_chart(latency_chart, use_container_width=True, key="focus_latency_chart")
        
        with l_col2:
            p50 = metrics.time_to_first_byte_p50
            p95 = metrics.time_to_first_byte_p95
            p99 = metrics.time_to_first_byte_p99
            
            if p50 and p95 and p99:
                st.metric("P50 (Median)", f"{p50.mean:,.0f} ms",
                          help="Median time to first byte — what most users experience")
                st.metric("P95 Latency", f"{p95.mean:,.0f} ms",
                          help="95th percentile — 1 in 20 requests is slower than this")
                st.metric("P99 Latency", f"{p99.mean:,.0f} ms",
                          help="99th percentile — worst-case tail latency")
                
                variance_ratio = p99.mean / p50.mean if p50.mean > 0 else 0
                st.metric("Variance (P99/P50)", f"{variance_ratio:.1f}x",
                          help="How much worse tail latency is vs median. >4x = unstable")
                
                if variance_ratio > 4:
                    st.error(
                        f"**High variance:** P99 is {variance_ratio:.1f}x the median. "
                        "Shared PAYG infrastructure is causing severe latency spikes. "
                        "Tail requests take significantly longer than average."
                    )
                elif variance_ratio > 2:
                    st.warning(
                        f"**Moderate variance:** P99 is {variance_ratio:.1f}x the median. "
                        "Some users experience noticeably slower responses."
                    )
                else:
                    st.success(
                        f"**Stable:** P99 is only {variance_ratio:.1f}x the median. "
                        "Latency is consistent — shared infrastructure performs well."
                    )
        
        if p95 and p95.mean > 2000:
            st.info(
                "**PTU provides dedicated compute** with consistent latency. "
                "No more competing for shared GPU resources during peak hours. "
                "Typical PTU latency improvement: 30-50% reduction in P95/P99."
            )
    
    elif focus_topic == "Predictable Billing":
        render_section_divider("Billing Predictability")
        render_section_header(
            "Billing Analysis",
            "How much your PAYG costs vary month-to-month vs fixed PTU pricing"
        )
        
        if metrics.tokens_per_minute:
            tpm = metrics.tokens_per_minute
            min_monthly_est = tpm.min * 43200 / 1_000_000 * payg_blended_rate
            avg_monthly_est = tpm.mean * 43200 / 1_000_000 * payg_blended_rate
            p95_monthly_est = tpm.p95 * 43200 / 1_000_000 * payg_blended_rate
            
            b_col1, b_col2, b_col3 = st.columns(3)
            with b_col1:
                st.metric("PAYG Low Estimate", f"${min_monthly_est:,.0f}/mo",
                          help="Monthly cost if usage stays at minimum observed level")
            with b_col2:
                st.metric("PAYG Average", f"${avg_monthly_est:,.0f}/mo",
                          help="Monthly cost at your average usage level")
            with b_col3:
                st.metric("PAYG High Estimate", f"${p95_monthly_est:,.0f}/mo",
                          help="Monthly cost during peak usage periods (P95)")
            
            range_pct = ((p95_monthly_est - min_monthly_est) / avg_monthly_est * 100) if avg_monthly_est > 0 else 0
            
            if range_pct > 50:
                st.error(
                    f"**High variability:** PAYG costs swing by **±{range_pct:.0f}%** around average. "
                    f"Monthly bills range from ${min_monthly_est:,.0f} to ${p95_monthly_est:,.0f}. "
                    "Budget forecasting is extremely difficult."
                )
            elif range_pct > 25:
                st.warning(
                    f"**Moderate variability:** PAYG costs vary by **±{range_pct:.0f}%**. "
                    "Monthly bills are somewhat unpredictable."
                )
            else:
                st.success(
                    f"**Stable billing:** PAYG costs only vary by **±{range_pct:.0f}%**. "
                    "Current billing is already quite predictable."
                )
            
            st.info(
                f"**PTU = fixed monthly cost:** {baseline_ptu} PTU at your selected "
                f"commitment level = **${ptu_baseline_cost:,.0f}/month** regardless of "
                "usage fluctuations. Budget it once, forget about surprises."
            )
    
    elif focus_topic == "Guaranteed Capacity":
        render_section_divider("Capacity Analysis")
        render_section_header(
            "Capacity Guarantee",
            "Dedicated GPU capacity vs shared PAYG infrastructure"
        )
        
        c_col1, c_col2 = st.columns([2, 1])
        with c_col1:
            tpm_chart = create_foundry_tokens_per_minute_chart(metrics)
            if tpm_chart:
                st.plotly_chart(tpm_chart, use_container_width=True, key="focus_capacity_chart")
        
        with c_col2:
            st.metric("Avg Throughput", format_number(avg_tpm) + " TPM",
                      help="Your average tokens-per-minute throughput")
            st.metric("Peak Throughput", format_number(peak_tpm) + " TPM",
                      help="Your 95th percentile throughput")
            st.metric("Throttling Rate", f"{throttle_pct:.1f}%",
                      help="Every throttled request = a capacity gap")
            
            if throttle_pct > 1:
                st.error(
                    f"**Capacity shortfall:** {throttle_pct:.1f}% of requests are rejected "
                    "because shared PAYG quota can't keep up. For mission-critical workloads, "
                    "any 429 error is unacceptable."
                )
            else:
                st.success(
                    "**Adequate capacity:** Current PAYG limits handle your workload. "
                    "However, shared capacity is not guaranteed — other tenants can affect availability."
                )
        
        st.info(
            f"**PTU guarantees dedicated capacity:** {baseline_ptu} PTU = "
            f"**{ptu_capacity_tpm:,.0f} TPM always available**, no sharing. "
            "Ideal for SLAs, compliance, and mission-critical applications."
        )
    
    # Cost Reduction topic — add brief context before Cost Explorer
    if focus_topic == "Cost Reduction":
        render_section_divider("Cost Analysis")
    else:
        render_section_divider("Cost Comparison")
    
    # =================================================================
    # SECTION 2: COST EXPLORER (Break-Even Chart + Slider)
    # =================================================================
    render_section_header("Cost Explorer", "Drag the slider to size your PTU baseline. The chart shows where PTU becomes cheaper than PAYG.")

    # Reservation term selector (above chart)
    reservation_options = [
        'Hourly — No Commitment',
        'Monthly Commitment (Estimated 64% off)',
        '1-Year Commitment (Estimated 69% off)',
    ]
    selected_reservation = st.selectbox(
        "PTU Pricing Term",
        options=reservation_options,
        index=reservation_options.index(
            st.session_state.get('ptu_reservation_type', 'Monthly Commitment (Estimated 64% off)')
        ),
        key='ptu_reservation_selector',
        help="**Hourly — No Commitment:** $1.00/PTU-hour ($720/PTU-month). Pay only while deployed, cancel anytime.\n\n"
             "**Monthly Commitment:** $260/PTU-month (~$0.36/PTU-hour). 64% cheaper, billed monthly.\n\n"
             "**1-Year Commitment:** $221/PTU-month ($2,652/PTU-year). 69% cheaper, 1-year term.\n\n"
             "Changing this shifts the break-even point on the chart below."
    )
    if selected_reservation != st.session_state.get('ptu_reservation_type'):
        st.session_state['ptu_reservation_type'] = selected_reservation
        st.rerun()

    # ── Compute break-even and cost curves ──
    break_even_tpm = calculate_break_even(
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        reservation_discount=reservation_discount,
        min_ptu=15,
        ptu_increment=5,
        max_search_tpm=max(peak_tpm * 3, 100_000) if peak_tpm > 0 else 200_000,
    )

    cost_curves = generate_cost_curves(
        tpm_values=tpm_values,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_blended_rate=payg_blended_rate,
        payg_rate_per_1k=payg_rate,
        reservation_discount=reservation_discount,
        min_ptu=15,
        ptu_increment=5,
    )

    # ── Smart default: set slider to percentile just above break-even ──
    if 'ptu_baseline_percentile' not in st.session_state:
        if break_even_tpm is not None and tpm_values:
            for p in range(0, 100, 5):
                if float(np.percentile(tpm_values, p)) >= break_even_tpm:
                    st.session_state['ptu_baseline_percentile'] = min(p, 95)
                    break
            else:
                st.session_state['ptu_baseline_percentile'] = 65
        else:
            st.session_state['ptu_baseline_percentile'] = 65

    # ── Baseline slider ──
    baseline_pctl = st.slider(
        "PTU Baseline Coverage",
        min_value=0,
        max_value=95,
        value=st.session_state.get('ptu_baseline_percentile', 65),
        step=5,
        format="P%d",
        help="Drag to set what percentage of your traffic the PTU covers. "
             "Traffic above this baseline spills to PAYG. "
             "The break-even marker (yellow) shows where PTU becomes cost-effective.",
        key='ptu_baseline_slider',
    )
    st.session_state['ptu_baseline_percentile'] = baseline_pctl
    baseline_label = f"P{baseline_pctl}" if baseline_pctl > 0 else "Min PTU (15)"

    # Recalculate spillover at the new slider position
    spillover = calculate_spillover_cost(
        tpm_values=tpm_values,
        baseline_percentile=baseline_pctl,
        ptu_capacity_per_unit=ptu_capacity,
        ptu_hourly_rate=ptu_hourly,
        payg_rate_per_1k=payg_rate,
        reservation_discount=reservation_discount,
    )
    baseline_tpm = spillover["baseline_tpm"]
    baseline_ptu = spillover["baseline_ptu"]
    ptu_capacity_tpm = spillover["ptu_capacity_tpm"]
    spillover_tokens_monthly = spillover["spillover_tokens_monthly"]
    spillover_cost = spillover["spillover_cost"]
    ptu_baseline_cost = spillover["ptu_monthly_cost"]
    hybrid_total = spillover["total_hybrid_cost"]
    spillover_pct = spillover["spillover_pct"]
    avg_spillover_tpm = spillover["avg_spillover_tpm"]

    # Recalculate savings with new hybrid_total
    savings = payg_total - hybrid_total
    savings_pct = (savings / payg_total * 100) if payg_total > 0 else 0

    # Slider context line
    slider_tpm_val = baseline_tpm if baseline_pctl > 0 else (15 * ptu_capacity)
    st.caption(
        f"**{baseline_label}** → {baseline_tpm:,.0f} TPM → **{baseline_ptu} PTU** "
        f"({ptu_capacity_tpm:,.0f} TPM capacity) · "
        f"{spillover_pct:.0f}% of traffic spills to PAYG"
    )

    # ── Break-even chart ──
    if not cost_curves.empty:
        # PAYG cost at the slider's baseline TPM (for the marker dot)
        payg_at_slider = baseline_tpm * 43_200 / 1_000_000 * payg_blended_rate

        fig_be = create_breakeven_chart(
            cost_curves=cost_curves,
            break_even_tpm=break_even_tpm,
            user_avg_tpm=avg_tpm,
            slider_baseline_tpm=baseline_tpm,
            payg_at_slider=payg_at_slider,
            hybrid_at_slider=hybrid_total,
            payg_blended_rate=payg_blended_rate,
        )
        st.plotly_chart(fig_be, use_container_width=True)

    # ── Cost summary strip ──
    summary_col1, summary_col2, summary_col3 = st.columns(3)
    with summary_col1:
        st.metric(
            "PAYG Monthly",
            f"${payg_total:,.0f}",
            help="**Pay-As-You-Go** — you pay per token with no commitment. "
                 "Cost scales linearly with usage. Includes estimated throttling impact."
        )
    with summary_col2:
        st.metric(
            "PTU + Spillover",
            f"${hybrid_total:,.0f}",
            help=f"**Hybrid strategy** — reserve {baseline_ptu} PTU for baseline ({baseline_label}), "
                 "let traffic peaks automatically overflow to PAYG. "
                 "[Azure Docs](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management)"
        )
    with summary_col3:
        delta_val = payg_total - hybrid_total
        st.metric(
            "Difference",
            f"${abs(delta_val):,.0f}/mo",
            delta=f"{'Saving' if delta_val > 0 else 'Extra cost'} with PTU",
            delta_color="normal" if delta_val > 0 else "inverse",
            help="Positive = PTU + Spillover is cheaper. Negative = PAYG is cheaper."
        )

    # ── Break-even callout banner ──
    if break_even_tpm is not None and break_even_tpm > 0:
        distance_pct = ((avg_tpm - break_even_tpm) / break_even_tpm * 100) if break_even_tpm > 0 else 0
        be_monthly_cost = break_even_tpm * 43_200 / 1_000_000 * payg_blended_rate

        if distance_pct > 10:
            # Well above break-even — PTU wins
            be_color = "#00d4aa"
            be_bg = "rgba(0, 212, 170, 0.08)"
            be_icon = ""
            be_text = (
                f"Your avg usage ({avg_tpm:,.0f} TPM) is **{distance_pct:.0f}% above** the break-even point. "
                f"PTU is cost-effective at your current usage level."
            )
        elif distance_pct > -10:
            # Near break-even — marginal
            be_color = "#FFB900"
            be_bg = "rgba(255, 185, 0, 0.08)"
            be_icon = ""
            be_text = (
                f"Your avg usage ({avg_tpm:,.0f} TPM) is **near the break-even point** ({break_even_tpm:,.0f} TPM). "
                f"Small usage changes could tip the balance either way."
            )
        else:
            # Below break-even — PAYG wins
            be_color = "#0078D4"
            be_bg = "rgba(0, 120, 212, 0.08)"
            be_icon = ""
            be_text = (
                f"Your avg usage ({avg_tpm:,.0f} TPM) is **{abs(distance_pct):.0f}% below** the break-even point ({break_even_tpm:,.0f} TPM). "
                f"PAYG is more cost-effective at your current usage level."
            )

        st.markdown(f"""
        <div style="background: {be_bg}; border: 1px solid {be_color}; border-left: 4px solid {be_color};
                    padding: 16px 20px; border-radius: 12px; margin: 16px 0;">
            <div style="font-size: 14px; color: #ffffff; font-family: 'DM Sans', sans-serif; line-height: 1.6;">
                {be_icon}<strong style="color: {be_color};">Break-even: {break_even_tpm:,.0f} TPM</strong> (${be_monthly_cost:,.0f}/mo)
                <br>
                <span style="color: #b8b8c8;">{be_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Break-even doesn't exist in range
        if payg_total <= hybrid_total:
            st.info("**PAYG is cheaper** at all usage levels for the selected pricing term. PTU break-even is not reached.")
            if reservation_discount >= 1.0:
                st.warning(
                    "**Tip:** You are viewing hourly PTU ($1/PTU-hour) with no commitment. "
                    "Most customers use **Monthly** ($260/PTU-month, 64 % off) or "
                    "**1-Year** ($221/PTU-month, 69 % off) commitments. "
                    "Switch the *PTU Pricing Term* dropdown above to see committed pricing."
                )
        else:
            st.success("**PTU + Spillover is cheaper** at virtually all usage levels for the selected pricing term.")

    # ── Detailed formulas (collapsed) ──
    with st.expander("Show detailed cost calculations", expanded=False):
        col_payg, col_ptu = st.columns(2)

        with col_payg:
            st.markdown("#### PAYG Cost")
            st.caption("Pay per token processed — no commitment, scales with usage.")
            throttle_text = f"\nThrottling impact ({throttle_pct:.1f}%):\n+${throttle_impact:,.0f}/mo" if throttle_impact > 0 else ""
            st.code(f"""
Monthly tokens:
{avg_tpm:,.0f} TPM × 60 × 24 × 30 = {monthly_tokens/1_000_000:.1f}M tokens

Base cost:
{monthly_tokens/1_000_000:.1f}M × ${payg_blended_rate:.2f}/1M = ${payg_base:,.0f}/mo
{throttle_text}

TOTAL: ${payg_total:,.0f}/month
            """, language=None)

        with col_ptu:
            st.markdown("#### PTU + Spillover")
            st.caption(
                f"Reserve PTU for baseline ({baseline_label}), overflow peaks to PAYG. "
                "[Azure Docs](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management)"
            )
            ptu_cost_label = {
                69: f"{baseline_ptu} PTU × $221/mo (1-yr) = ${ptu_baseline_cost:,.0f}/mo",
                64: f"{baseline_ptu} PTU × $260/mo (monthly) = ${ptu_baseline_cost:,.0f}/mo",
            }.get(
                reservation_discount_pct,
                f"{baseline_ptu} PTU × ${ptu_hourly}/hr × 720 hrs = ${ptu_baseline_cost:,.0f}/mo"
            )
            st.code(f"""
Baseline ({baseline_label}):
{baseline_tpm:,.0f} TPM ÷ {ptu_capacity:,} TPM/PTU = {baseline_ptu} PTU

PTU cost ({reservation_type}):
{ptu_cost_label}

Spillover (~{avg_spillover_tpm:,.0f} TPM overflow):
= ${spillover_cost:,.0f}/mo

TOTAL: ${hybrid_total:,.0f}/month
            """, language=None)

    render_section_divider("Recommendation")
    
    # =================================================================
    # SECTION 3: THE ANSWER
    # =================================================================
    # Build confidence bar and summary text for the recommendation banner
    confidence_pct = int(analysis.confidence * 100)
    confidence_bar_color = rec_color
    analysis_summary_text = analysis.summary if hasattr(analysis, 'summary') and analysis.summary else ""
    
    # Build cost context line based on recommendation + savings alignment
    if analysis.recommendation == Recommendation.PTU_RECOMMENDED:
        if savings > 0:
            cost_line = f"""Save <strong style="color: {rec_color}; text-shadow: 0 0 20px {rec_color};">${savings:,.0f}/month</strong> <span style="color: #6b6b7a;">({savings_pct:.0f}%)</span>"""
            benefit_line = "Eliminate throttling / Guaranteed capacity / Predictable billing"
        else:
            # PTU recommended for performance, but costs more — show the trade-off
            extra = abs(savings)
            cost_line = f"""<span style="color: #6b6b7a;">+${extra:,.0f}/month</span> for <strong style="color: {rec_color};">guaranteed performance</strong>"""
            benefit_line = f"Eliminate {throttle_pct:.1f}% throttling / Guaranteed latency / Zero 429 errors"
        shadow_color = "rgba(0, 212, 170, 0.15)"  # kept for potential future use
    elif analysis.recommendation == Recommendation.PTU_NOT_RECOMMENDED:
        additional = abs(savings) if savings < 0 else savings
        cost_line = f"""PAYG saves <strong style="color: {rec_color};">${additional:,.0f}/month</strong> at current usage"""
        benefit_line = "Variable usage pattern / PTU would be underutilized"
        shadow_color = "rgba(0, 120, 212, 0.15)"  # kept for potential future use
    else:
        # BORDERLINE
        if savings > 0:
            cost_line = f"""PTU could save <strong style="color: {rec_color};">${savings:,.0f}/month</strong> — but more data needed"""
        else:
            cost_line = f"""Cost difference is <strong style="color: {rec_color};">${abs(savings):,.0f}/month</strong> — more data needed"""
        benefit_line = "Collect more data for a confident recommendation"
        shadow_color = "rgba(255, 170, 0, 0.15)"

    st.markdown(f"""
    <div style="background: {rec_bg}; border: 1px solid {rec_color}; border-left: 4px solid {rec_color};
                padding: 28px 32px; border-radius: 12px; margin: 24px 0;">
        <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px;">
            <span style="font-size: 12px; font-weight: 600; color: {rec_color}; background: {rec_color}18;
                         padding: 4px 10px; border-radius: 4px; letter-spacing: 0.08em;
                         font-family: 'JetBrains Mono', monospace;">{rec_icon}</span>
            <span style="font-size: 22px; font-weight: 700; color: {rec_color};
                         font-family: 'DM Sans', sans-serif; letter-spacing: 0.02em;">{rec_text}</span>
        </div>
        <div style="font-size: 18px; color: #ffffff; font-family: 'JetBrains Mono', monospace; margin-bottom: 12px;">
            {cost_line}
        </div>
        <div style="display: flex; align-items: center; gap: 12px; margin: 14px 0 10px 0;">
            <div style="flex: 0 0 200px; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                <div style="width: {confidence_pct}%; height: 100%; background: {confidence_bar_color}; border-radius: 2px;"></div>
            </div>
            <span style="font-size: 12px; color: #6b6b7a; font-family: 'JetBrains Mono', monospace;">
                {confidence_pct}% confidence
            </span>
        </div>
        <div style="font-size: 14px; color: #b8b8c8; font-family: 'DM Sans', sans-serif; line-height: 1.6; margin-top: 8px;">
            {analysis_summary_text}
        </div>
        <div style="font-size: 13px; color: #6b6b7a; margin-top: 10px; font-family: 'DM Sans', sans-serif;">
            {benefit_line}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # =================================================================
    # NEXT STEP
    # =================================================================
    if analysis.recommendation == Recommendation.PTU_RECOMMENDED:
        st.success("**Next Step:** Contact your Azure account team to request PTU capacity.")
    elif analysis.recommendation == Recommendation.PTU_NOT_RECOMMENDED:
        st.info("**Next Step:** Stay with PAYG. Set alerts for throttling >3% to reassess later.")
    else:
        st.warning("**Next Step:** Collect 1-2 more weeks of data for a clearer recommendation.")
    
    # =================================================================
    # DETAILED TABS
    # =================================================================
    st.markdown("<hr style='border-color: #2a2a3a; margin: 32px 0;'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #ffffff; font-family: DM Sans;'>Detailed Analysis</h3>", unsafe_allow_html=True)
    st.caption("Dive into raw metrics, full cost breakdowns, and educational resources.")
    
    tab_data, tab_cost, tab_learn = st.tabs([
        "Your Data",
        "Cost Details", 
        "Learn More"
    ])
    
    # -----------------------------------------------------------------
    # TAB: YOUR DATA (Azure AI Foundry Style Monitoring)
    # -----------------------------------------------------------------
    with tab_data:
        # Header styled like Azure AI Foundry
        if _scope_accounts and len(_scope_accounts) > 1:
            raw_scope_line = f"Aggregated monitoring data across {len(_scope_accounts)} selected accounts"
            raw_scope_caption = (
                "These charts show aggregated metrics across selected accounts and deployments. "
                "Look for consistent patterns (stable = good for PTU) vs large spikes (better for PAYG)."
            )
        elif _scope_deployment:
            raw_scope_line = f"Monitoring data for deployment: {_scope_deployment}"
            raw_scope_caption = (
                "These charts show metrics for the selected deployment. "
                "Look for consistent patterns (stable = good for PTU) vs large spikes (better for PAYG)."
            )
        else:
            raw_scope_line = "Aggregated monitoring data across all deployments in your account"
            raw_scope_caption = (
                "These charts show aggregated metrics across all deployments. "
                "Look for consistent patterns (stable = good for PTU) vs large spikes (better for PAYG)."
            )

        st.markdown("""
        <div style="background: linear-gradient(90deg, #0078D4 0%, #106EBE 100%); 
                    padding: 16px 24px; border-radius: 8px; margin-bottom: 20px;">
            <h4 style="margin: 0; color: white; font-family: 'Segoe UI', sans-serif; font-weight: 600;">
                Raw Metrics from Azure AI Foundry
            </h4>
            <p style="margin: 4px 0 0 0; color: rgba(255,255,255,0.85); font-size: 13px;">
                {raw_scope_line}
            </p>
        </div>
        """.replace("{raw_scope_line}", raw_scope_line), unsafe_allow_html=True)
        st.caption(raw_scope_caption)
        
        # Summary metrics row (like Foundry's metric cards)
        throttled_count = int(metrics.throttled_requests.total) if metrics.throttled_requests else 0
        
        m1, m2, m3, m4, m5 = st.columns(5)
        
        with m1:
            st.metric(
                "Total Requests",
                f"{metrics.total_requests:,}",
                help="Sum of successful + throttled requests over the analysis period",
            )
        
        with m2:
            if metrics.tokens_per_minute:
                total_tokens = int(metrics.tokens_per_minute.mean * 60 * 24 * analysis_period)
                st.metric(
                    "Total Tokens",
                    f"{total_tokens / 1_000_000:.1f}M",
                    help="Estimated total tokens processed (prompt + completion)",
                )
        
        with m3:
            throttle_delta = "Healthy" if throttle_pct <= 1 else "High"
            st.metric(
                "Throttle Rate",
                f"{throttle_pct:.2f}%",
                delta=throttle_delta,
                delta_color="normal" if throttle_pct <= 1 else "inverse",
                help="Percentage of requests that received HTTP 429 (rate-limited)",
            )
        
        with m4:
            if metrics.time_to_first_byte_p50:
                ttft_val = metrics.time_to_first_byte_p50.mean
                st.metric(
                    "Avg Latency (TTFT)",
                    f"{ttft_val:,.0f}ms",
                    help="Median time-to-first-byte across all requests",
                )
        
        with m5:
            if metrics.tokens_per_minute:
                st.metric(
                    "Avg TPM",
                    f"{metrics.tokens_per_minute.mean:,.0f}",
                    help="Average tokens-per-minute throughput",
                )
        
        # Charts Grid - 2x2 layout like Azure Monitor
        st.markdown("##### Monitoring Charts")
        
        chart_row1_col1, chart_row1_col2 = st.columns(2)
        
        with chart_row1_col1:
            tokens_chart = create_foundry_processed_tokens_chart(metrics)
            if tokens_chart:
                st.plotly_chart(tokens_chart, use_container_width=True, key="foundry_tokens_chart")
            else:
                st.info("No token data available — the deployment may not have processed traffic in this period.")
        
        with chart_row1_col2:
            requests_chart = create_foundry_requests_chart(metrics)
            if requests_chart:
                st.plotly_chart(requests_chart, use_container_width=True, key="foundry_requests_chart")
            else:
                st.info("No request data available.")
        
        chart_row2_col1, chart_row2_col2 = st.columns(2)
        
        with chart_row2_col1:
            latency_chart = create_foundry_latency_chart(metrics)
            if latency_chart:
                st.plotly_chart(latency_chart, use_container_width=True, key="foundry_latency_chart")
            else:
                st.info("No latency data available.")
        
        with chart_row2_col2:
            throttle_chart = create_foundry_throttled_requests_chart(metrics)
            if throttle_chart:
                st.plotly_chart(throttle_chart, use_container_width=True, key="foundry_throttle_chart")
            else:
                st.info("No throttling data available.")
        
        # TPM Detail Chart (full width)
        st.markdown("##### Tokens Per Minute Detail")
        tpm_detail_chart = create_foundry_tokens_per_minute_chart(metrics)
        if tpm_detail_chart:
            st.plotly_chart(tpm_detail_chart, use_container_width=True, key="foundry_tpm_detail_chart")
        else:
            st.info("No tokens-per-minute data available for this account.")
        
        # Detailed metrics tables (collapsible)
        with st.expander("Detailed Metrics Tables", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**Token Metrics**")
                if metrics.tokens_per_minute:
                    tpm = metrics.tokens_per_minute
                    st.markdown(f"""
                    | Metric | Value |
                    |--------|-------|
                    | Mean TPM | {tpm.mean:,.0f} |
                    | P50 TPM | {tpm.p50:,.0f} |
                    | P95 TPM | {tpm.p95:,.0f} |
                    | P99 TPM | {tpm.p99:,.0f} |
                    | Max TPM | {tpm.max:,.0f} |
                    | Std Dev | {tpm.std:,.0f} |
                    """)
            
            with col2:
                st.markdown("**Latency Metrics**")
                if metrics.time_to_first_byte_p50:
                    st.markdown(f"""
                    | Percentile | Value |
                    |------------|-------|
                    | P50 | {metrics.time_to_first_byte_p50.mean:,.0f} ms |
                    | P95 | {metrics.time_to_first_byte_p95.mean:,.0f} ms |
                    | P99 | {metrics.time_to_first_byte_p99.mean:,.0f} ms |
                    """)
            
            with col3:
                st.markdown("**Request Metrics**")
                st.markdown(f"""
                | Metric | Value |
                |--------|-------|
                | Total Requests | {metrics.total_requests:,} |
                | Throttled | {throttled_count:,} |
                | Throttle Rate | {throttle_pct:.2f}% |
                | Analysis Period | {analysis_period} days |
                """)
        
        # Utilization metrics
        if metrics.tokens_per_minute:
            tpm = metrics.tokens_per_minute
            st.markdown("##### Utilization Analysis")
            st.caption(
                "These metrics measure how consistently your workload uses capacity. "
                "High sustained utilization and 24/7 activity make PTU cost-effective; "
                "spiky, business-hours-only patterns favour PAYG."
            )
            
            util_col1, util_col2, util_col3, util_col4 = st.columns(4)
            
            with util_col1:
                par = tpm.peak_to_average_ratio
                st.metric(
                    "Peak-to-Avg Ratio",
                    f"{par:.2f}x",
                    delta="Stable" if par < 1.5 else "Variable",
                    delta_color="normal" if par < 1.5 else "inverse",
                    help="""**Peak-to-Average Ratio**
                    
Measures how much your peak usage exceeds your average.

• **< 1.5x** → Stable workload, ideal for PTU
• **1.5x - 2.5x** → Moderate variability, PTU may work
• **> 2.5x** → High variability, PAYG may be better

*Formula: P95 TPM ÷ Mean TPM*"""
                )
            
            with util_col2:
                sustained = tpm.sustained_utilization_rate(0.3)
                st.metric(
                    "Sustained Util",
                    f"{sustained:.0f}%",
                    delta="Good" if sustained > 60 else "Low",
                    delta_color="normal" if sustained > 60 else "inverse",
                    help="""**Sustained Utilization Rate**
                    
Percentage of time your usage stays above 30% of peak capacity.

• **> 60%** → High sustained usage, PTU is cost-effective
• **40-60%** → Moderate, borderline for PTU
• **< 40%** → Low sustained usage, PAYG likely better

*Higher = more consistent workload = better PTU fit*"""
                )
            
            with util_col3:
                active = tpm.active_hours_percentage
                st.metric(
                    "Active Hours",
                    f"{active:.0f}%",
                    delta="High" if active > 70 else "Sparse",
                    delta_color="normal" if active > 70 else "off",
                    help="""**Active Hours Percentage**
                    
Percentage of hours with meaningful traffic (>5% of peak).

• **> 70%** → Near 24/7 usage, excellent for PTU
• **50-70%** → Extended business hours usage
• **< 50%** → Sparse usage, PTU capacity underutilized

*Higher = more hours generating value from PTU*"""
                )
            
            with util_col4:
                biz = tpm.business_hours_concentration
                st.metric(
                    "Business Hours",
                    f"{biz:.0f}%",
                    delta="24/7" if biz < 50 else "Peak Only",
                    delta_color="normal" if biz < 75 else "off",
                    help="""**Business Hours Concentration**
                    
Percentage of total traffic occurring during business hours (9 AM - 5 PM).

• **< 50%** → 24/7 workload, great PTU utilization
• **50-75%** → Mixed pattern, moderate PTU fit
• **> 75%** → Business hours only, PTU idle nights/weekends

*Lower = more evenly distributed = better PTU ROI*"""
                )
    
    # -----------------------------------------------------------------
    # TAB: COST DETAILS
    # -----------------------------------------------------------------
    with tab_cost:
        st.markdown("#### Detailed Cost Breakdown")
        st.caption(
            "Full formulas and line-by-line calculations for each pricing strategy. "
            "All prices are based on Azure OpenAI published rates (Jan 2026)."
        )
        
        # Show the full calculation
        st.markdown("##### PAYG Only")
        st.code(f"""
# Token Volume
avg_tpm = {avg_tpm:,.0f}
monthly_minutes = 60 * 24 * 30 = 43,200
monthly_tokens = {avg_tpm:,.0f} × 43,200 = {monthly_tokens:,.0f}

# PAYG Pricing (Azure Jan 2026)
# GPT-4o: $2.50/1M input + $10/1M output
# Blended rate (30% output): ${payg_blended_rate:.2f}/1M tokens

base_cost = {monthly_tokens:,.0f} ÷ 1M × ${payg_blended_rate:.2f}
         = ${payg_base:,.0f}/month

# Throttling Impact (if >1% throttling)
throttle_rate = {throttle_pct:.1f}%
throttle_impact = ${payg_base:,.0f} × {throttle_rate:.3f} × 2
                = ${throttle_impact:,.0f}/month

# Total PAYG Cost
total = ${payg_base:,.0f} + ${throttle_impact:,.0f} = ${payg_total:,.0f}/month
        """, language="python")
        
        st.markdown("##### PTU + Spillover Strategy")
        st.caption("Size PTU to baseline, let peaks overflow to PAYG ([Azure Docs](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management))")
        
        # Show reservation type
        res_badge = {
            69: "[1-Year Commitment]",
            64: "[Monthly Commitment]",
        }.get(reservation_discount_pct, "[Hourly — No Commitment]")
        st.markdown(f"**Selected Pricing:** {res_badge}")
        
        st.code(f"""
# SPILLOVER STRATEGY: Commit to baseline, NOT peak
# Reference: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management

# Step 1: Analyze your TPM distribution
peak_tpm (P95)     = {peak_tpm:,.0f} TPM  ← Don't commit to this!
baseline_tpm ({baseline_label}) = {baseline_tpm:,.0f} TPM  ← Commit to this instead

# Step 2: Size PTU to BASELINE (not peak!)
# {baseline_label} baseline: {'covers ' + str(baseline_pctl) + '% of traffic' if baseline_pctl > 0 else 'minimum PTU block (15 PTU)'}
headroom = 1.1 (10% buffer)
capacity_per_ptu = {ptu_capacity:,} TPM

ptu_needed = ceil({baseline_tpm:,.0f} × 1.1 ÷ {ptu_capacity:,})
           = {baseline_ptu} PTU (rounded to nearest 5)

# Your committed PTU capacity:
ptu_capacity = {baseline_ptu} PTU × {ptu_capacity:,} TPM/PTU = {ptu_capacity_tpm:,.0f} TPM

# Step 3: Calculate PTU cost (Azure Pricing Feb 2026)
# Hourly: $1/PTU-hr ($720/mo), Monthly: $260/PTU-mo (64% off), 1-Year: $221/PTU-mo (69% off)
{({69: "ptu_cost = " + str(baseline_ptu) + f" PTU × $221/month = ${ptu_baseline_cost:,.0f}/month  (1-yr commitment)", 64: "ptu_cost = " + str(baseline_ptu) + f" PTU × $260/month = ${ptu_baseline_cost:,.0f}/month  (monthly commitment)"}).get(reservation_discount_pct, "ptu_cost = " + str(baseline_ptu) + f" PTU × ${ptu_hourly}/hr × 720 hrs = ${ptu_baseline_cost:,.0f}/month  (hourly, no commitment)")}

# Step 4: Calculate spillover (PAYG for traffic above PTU capacity)
# When usage exceeds {ptu_capacity_tpm:,.0f} TPM, overflow goes to PAYG
avg_spillover = ~{avg_spillover_tpm:,.0f} TPM overflows to PAYG on average
overflow_tokens_monthly = {spillover_tokens_monthly:,.0f}
spillover_cost = {spillover_tokens_monthly:,.0f} ÷ 1M × ${payg_blended_rate:.2f}
               = ${spillover_cost:,.0f}/month

# Total Hybrid Cost (PTU + Spillover)
total = ${ptu_baseline_cost:,.0f} + ${spillover_cost:,.0f} = ${hybrid_total:,.0f}/month
        """, language="python")
        
        # Show comparison of all strategies
        st.markdown("##### Strategy Comparison")
        
        comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
        
        with comp_col1:
            st.metric("PAYG Only", f"${payg_total:,.0f}", help="All traffic on pay-as-you-go")
        
        with comp_col2:
            st.metric("Full PTU", f"${ptu_effective_cost:,.0f}", help=f"PTU sized to peak ({ptu_needed_full} PTU)")
        
        with comp_col3:
            st.metric(
                "PTU + Spillover", 
                f"${hybrid_total:,.0f}", 
                help=f"PTU at baseline ({baseline_ptu} PTU) + PAYG overflow"
            )
        
        with comp_col4:
            best_strategy = min(
                [("PAYG Only", payg_total), ("Full PTU", ptu_effective_cost), ("Hybrid", hybrid_total)],
                key=lambda x: x[1]
            )
            savings_vs_worst = max(payg_total, ptu_effective_cost, hybrid_total) - best_strategy[1]
            st.metric(
                "Best Option", 
                best_strategy[0],
                delta=f"${savings_vs_worst:,.0f} saved",
                delta_color="normal"
            )
        
        st.info("**Note:** The spillover strategy lets you commit to a lower PTU baseline and automatically overflow peaks to PAYG. This optimizes cost without over-provisioning for peak usage.")
    
    # -----------------------------------------------------------------
    # TAB: LEARN MORE
    # -----------------------------------------------------------------
    with tab_learn:
        st.markdown("#### Quick-Start Decision Guide")

        # --- Decision tree style callout ---
        with st.expander("Should I use PTU or PAYG?", expanded=True):
            st.markdown("""
**Answer these three questions:**

1. **Is your monthly token spend > $5 000?**  
   → *No* — stay with **PAYG**. PTU minimum commitment is ~$3 300/mo (15 PTU reserved).

2. **Is your usage pattern stable (CV < 0.5)?**  
   → *No* — stay with **PAYG** or consider the **Hybrid** strategy (PTU baseline + PAYG spillover).

3. **Are you experiencing throttling (>1 % of requests)?**  
   → *Yes* — **PTU** gives guaranteed capacity and eliminates 429 errors.

> **Rule of thumb:** If you answered *Yes* to questions 2 **and** 3, PTU almost always saves money.
            """)

        # --- PTU vs PAYG comparison ---
        with st.expander("PTU vs PAYG — detailed comparison"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
##### When PTU fits
- **High sustained usage** (>50 % utilization 24/7)
- **Throttling issues** (>1 % of requests getting 429s)
- **Latency-sensitive** applications
- **Predictable billing** requirements
- **Guaranteed capacity** needed for SLAs
- **Production workloads** with consistent patterns
                """)
            with col2:
                st.markdown("""
##### When PAYG fits
- **Variable / spiky** usage patterns
- **Dev/test workloads** with unpredictable usage
- **New applications** without usage history
- **Cost flexibility** more important than predictability
- **Low overall volume** that doesn't justify a reservation
- **Experimentation** phase before production
                """)

        # --- Sizing guide ---
        with st.expander("PTU Sizing Guide"):
            st.markdown(
                """
                <div style=\"display:flex;align-items:center;gap:8px;color:#9aa0aa;font-size:0.9rem;margin-bottom:0.5rem;\">
                    <svg width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\" aria-hidden=\"true\">
                        <path d=\"M3 1.5H9.5L13 5V14.5H3V1.5Z\" stroke=\"#9aa0aa\" stroke-width=\"1.2\"/>
                        <path d=\"M9.5 1.5V5H13\" stroke=\"#9aa0aa\" stroke-width=\"1.2\"/>
                        <path d=\"M5 8H11M5 10H11M5 12H9\" stroke=\"#9aa0aa\" stroke-width=\"1.1\" stroke-linecap=\"round\"/>
                    </svg>
                    <a href=\"https://learn.microsoft.com/azure/ai-services/openai/how-to/provisioned-throughput-onboarding\" target=\"_blank\" style=\"color:#9aa0aa;text-decoration:none;\">Capacity &amp; performance</a>
                    <span>·</span>
                    <a href=\"https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management\" target=\"_blank\" style=\"color:#9aa0aa;text-decoration:none;\">Spillover traffic management</a>
                    <span>·</span>
                    <a href=\"https://learn.microsoft.com/azure/ai-services/openai/quotas-limits\" target=\"_blank\" style=\"color:#9aa0aa;text-decoration:none;\">Quotas &amp; limits</a>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("""
| Model | Approx TPM per PTU | Min PTU (Global) | Min PTU (Regional) |
|-------|-------------------|------------------|--------------------|
| GPT-4o | ~2,500 TPM | 15 | 50 |
| GPT-4o-mini | ~7,500 TPM | 15 | 50 |
| GPT-4 | ~1,500 TPM | 50 | 100 |
| GPT-3.5-Turbo | ~6,000 TPM | 50 | 50 |

*Actual capacity varies based on prompt/completion ratio and token length.*
            """)
            st.info("**Sizing formula:** `PTU needed = ceil(baseline_TPM × 1.1 ÷ TPM_per_PTU)` rounded to nearest 5.")

        # --- FAQ ---
        with st.expander("Frequently Asked Questions"):
            st.markdown("""
**Q: Can I mix PTU and PAYG on the same deployment?**  
A: Not on the *same* deployment, but you can create a second PAYG deployment of the same model and use the **spillover** pattern. PTU quota is **model-independent** — your PTU reservation within a subscription+region can cover multiple deployments across different models (e.g. GPT-4o + DeepSeek-R1).

**Q: What happens if I hit PTU capacity?**  
A: Requests above your provisioned capacity get HTTP 429 responses. With spillover enabled, Azure automatically redirects overflow to a PAYG endpoint.

**Q: How do commitment discounts work?**  
A: Azure offers three PTU pricing tiers: **Hourly** ($1/PTU-hour = $720/mo, no commitment), **Monthly** ($260/PTU-month, 64% off), and **1-Year** ($221/PTU-month, 69% off). Each commitment applies at the subscription level and auto-renews unless cancelled.

**Q: Can I scale PTU up or down?**  
A: You can increase PTU count at any time. Decreasing requires a support request or waiting for the commitment period to end, depending on your billing model.
            """)

        # --- Resources ---
        with st.expander("Useful Resources"):
            st.markdown("""
**Concepts & Planning**
- [PTU Overview](https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput) — what PTU is and how it works
- [Provisioned Managed (Foundry)](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/provisioned-managed) — Foundry-specific model
- [PTU Onboarding Guide](https://learn.microsoft.com/azure/ai-services/openai/how-to/provisioned-throughput-onboarding) — step-by-step setup

**Capacity & Limits**
- [Quotas & Limits](https://learn.microsoft.com/azure/ai-services/openai/quotas-limits) — per-model TPM caps & regional limits
- [Spillover Traffic](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/spillover-traffic-management) — PTU baseline + PAYG overflow

**Pricing & Cost**
- [Azure OpenAI Pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/) — current PAYG & PTU rates
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimate monthly costs
- [Azure Reservations](https://learn.microsoft.com/azure/cost-management-billing/reservations/save-compute-costs-reservations) — commitment discounts

**Monitoring & Optimization**
- [Monitor Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/how-to/monitor-openai) — metrics & dashboards
- [Latency & Performance](https://learn.microsoft.com/azure/ai-services/openai/how-to/latency) — reduce latency tips
- [Content Filtering](https://learn.microsoft.com/azure/ai-services/openai/concepts/content-filter) — 400-level errors vs throttling
            """)
    
    # -----------------------------------------------------------------
    # EXPORT / DOWNLOAD
    # -----------------------------------------------------------------
    st.markdown("")
    exp_col1, exp_col2, exp_col3 = st.columns([1, 2, 1])
    with exp_col2:
        try:
            payload = build_export_payload(
                metrics=metrics,
                analysis=analysis,
                spillover=spillover,
                payg_total=payg_total,
                hybrid_total=hybrid_total,
                reservation_type=reservation_type,
            )
            st.download_button(
                label="Export Analysis (JSON)",
                data=json.dumps(payload, indent=2, default=str),
                file_name=f"ptu_advisor_{metrics.deployment_name.replace(' ', '_')}_{datetime.now():%Y%m%d}.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception:
            pass  # Silently skip if variables not yet computed

    # Footer - dark theme
    st.markdown("<hr style='border-color: #2a2a3a; margin: 32px 0;'>", unsafe_allow_html=True)
    footer_label = f"Demo: {scenario_cfg.name}" if scenario_cfg else f"Live: {metrics.deployment_name} — Account-Level Analysis"
    st.markdown(f"""
    <div style="text-align: center; padding: 16px 0; color: #6b6b7a; font-family: 'DM Sans', sans-serif; font-size: 13px;">
        {footer_label} &nbsp;•&nbsp; PTU Advisor v1.0 &nbsp;•&nbsp; © 2026 Microsoft
    </div>
    """, unsafe_allow_html=True)
