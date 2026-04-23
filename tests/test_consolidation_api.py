"""Tests for POST /api/analyze-consolidation endpoint logic.

NOTE: Due to a pre-existing starlette version incompatibility,
``TestClient(app)`` cannot be instantiated at module level.
These tests call the endpoint handler function directly instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from ptu_advisor.api.server import (
    ConsolidationRequest,
    ConsolidationResponse,
    DeploymentPreview,
    analyze_consolidation,
    deployment_preview,
)
from ptu_advisor.metrics.models import DeploymentInfo, DeploymentMetrics, TimeSeries
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Demo mode consolidation
# ---------------------------------------------------------------------------


def _make_request(**overrides) -> ConsolidationRequest:
    """Helper to build a ConsolidationRequest with sensible demo defaults."""
    defaults = {
        "mode": "demo",
        "deployments": ["dep-a", "dep-b"],
        "focus_topic": "Cost Reduction",
        "lookback_days": 7,
        "granularity_minutes": 30,
    }
    defaults.update(overrides)
    return ConsolidationRequest(**defaults)


class TestConsolidationDemoMode:
    """Tests for consolidation analysis in demo mode."""

    def test_demo_consolidation_returns_consolidation_response(self):
        request = _make_request()
        result = analyze_consolidation(request)
        assert isinstance(result, ConsolidationResponse)

    def test_demo_consolidation_has_consolidation_summary(self):
        request = _make_request()
        result = analyze_consolidation(request)
        summary = result.consolidation_summary
        assert summary.deployment_count == 3  # Demo generates 3 siblings
        assert summary.model_name is not None
        assert len(summary.individual_deployments) == 3

    def test_demo_consolidation_has_standard_analysis_fields(self):
        request = _make_request()
        result = analyze_consolidation(request)

        # All standard AnalyzeResponse fields should be present
        assert result.recommendation is not None
        assert result.confidence > 0
        assert result.summary is not None
        assert result.dimensions is not None
        assert result.metrics is not None
        assert result.charts is not None
        assert result.cost_analysis is not None
        assert result.insights is not None

    def test_demo_consolidation_individual_deployments_have_costs(self):
        request = _make_request()
        result = analyze_consolidation(request)
        summary = result.consolidation_summary

        for dep in summary.individual_deployments:
            assert dep.name is not None
            assert dep.avg_tpm >= 0
            assert dep.peak_tpm >= 0
            assert dep.throttling_rate_pct >= 0
            assert dep.total_requests >= 0
            assert dep.latency_p50 >= 0
            assert dep.latency_p95 >= 0
            assert dep.payg_monthly_cost >= 0

    def test_demo_consolidation_savings_math_is_consistent(self):
        request = _make_request()
        result = analyze_consolidation(request)
        summary = result.consolidation_summary

        # savings = individual_payg_total - consolidated_hybrid_cost
        expected_savings = summary.individual_payg_total - summary.consolidated_hybrid_cost
        assert abs(summary.savings - expected_savings) < 0.01

        # savings_pct = savings / individual_payg_total * 100
        if summary.individual_payg_total > 0:
            expected_pct = expected_savings / summary.individual_payg_total * 100
            assert abs(summary.savings_pct - expected_pct) < 0.01

    def test_demo_not_worth_it_scenario_via_non_cost_topic(self):
        """When focus_topic is not 'Cost Reduction', uses CONSOLIDATE_NOT_WORTH_IT."""
        request = _make_request(focus_topic="Throttling & Reliability")
        result = analyze_consolidation(request)
        summary = result.consolidation_summary
        assert summary.deployment_count == 3
        # The "not worth it" scenario uses gpt-4o-mini model
        assert "mini" in summary.model_name.lower()

    def test_demo_consolidation_combined_tpm_is_close_to_sum(self):
        request = _make_request()
        result = analyze_consolidation(request)
        summary = result.consolidation_summary

        individual_avg_tpm_sum = sum(d.avg_tpm for d in summary.individual_deployments)
        # Combined avg TPM should be close to the sum of individuals
        assert summary.combined_avg_tpm > 0
        # Ratio check: combined should be within 20% of individual sum
        if individual_avg_tpm_sum > 0:
            ratio = summary.combined_avg_tpm / individual_avg_tpm_sum
            assert 0.8 <= ratio <= 1.2, (
                f"Combined avg TPM {summary.combined_avg_tpm:.0f} differs too much "
                f"from individual sum {individual_avg_tpm_sum:.0f}"
            )

    def test_demo_cost_analysis_contains_hybrid_and_payg(self):
        request = _make_request()
        result = analyze_consolidation(request)
        assert "payg" in result.cost_analysis
        assert "hybrid" in result.cost_analysis
        assert "pricing" in result.cost_analysis
        assert "formula_blocks" in result.cost_analysis

    def test_demo_charts_contain_expected_sections(self):
        request = _make_request()
        result = analyze_consolidation(request)
        assert "tokens" in result.charts
        assert "requests" in result.charts
        assert "cost_curves" in result.charts
        assert "tpm" in result.charts


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestConsolidationValidation:
    def test_rejects_single_deployment(self):
        with pytest.raises(Exception):
            # Pydantic validation rejects min_length=2
            _make_request(deployments=["dep-a"])

    def test_rejects_empty_deployment_list(self):
        with pytest.raises(Exception):
            _make_request(deployments=[])

    def test_rejects_more_than_10_deployments(self):
        with pytest.raises(Exception):
            # Pydantic validation rejects max_length=10
            _make_request(deployments=[f"dep-{i}" for i in range(11)])

    def test_live_mode_requires_subscription_info(self):
        request = _make_request(mode="live")
        with pytest.raises(HTTPException) as exc_info:
            analyze_consolidation(request)
        assert exc_info.value.status_code == 400
        assert "subscription_id" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Request parameters
# ---------------------------------------------------------------------------


class TestConsolidationRequestParams:
    def test_supports_reservation_type(self):
        request = _make_request(
            reservation_type="1-Year Commitment (Estimated 69% off)",
        )
        result = analyze_consolidation(request)
        pricing = result.cost_analysis["pricing"]
        assert pricing["reservation_discount_pct"] == 69

    def test_supports_baseline_ptu_override(self):
        request = _make_request(baseline_ptu=100)
        result = analyze_consolidation(request)
        hybrid = result.cost_analysis["hybrid"]
        assert hybrid["baseline_ptu"] == 100

    def test_supports_granularity_minutes(self):
        request = _make_request(granularity_minutes=15)
        result = analyze_consolidation(request)
        assert result.consolidation_summary.deployment_count == 3

    def test_supports_pricing_overrides(self):
        request = _make_request(
            payg_input_rate_override=2.50,
            payg_output_rate_override=10.00,
            ptu_hourly_rate_override=2.00,
        )
        result = analyze_consolidation(request)
        pricing = result.cost_analysis["pricing"]
        assert pricing["payg_input_rate_per_million"] == 2.50
        assert pricing["payg_output_rate_per_million"] == 10.00
        assert pricing["ptu_hourly_rate"] == 2.00

    def test_both_scenarios_produce_different_models(self):
        """Worth-it scenario uses gpt-4o, not-worth-it uses gpt-4o-mini."""
        worth_it = analyze_consolidation(_make_request(focus_topic="Cost Reduction"))
        not_worth_it = analyze_consolidation(_make_request(focus_topic="Throttling & Reliability"))
        assert (
            worth_it.consolidation_summary.model_name
            != not_worth_it.consolidation_summary.model_name
        )


# ---------------------------------------------------------------------------
# Per-deployment chart attribution (Phase 2)
# ---------------------------------------------------------------------------


class TestPerDeploymentChartData:
    """Tests that consolidation response charts include per_deployment data."""

    @pytest.fixture()
    def result(self) -> ConsolidationResponse:
        return analyze_consolidation(_make_request())

    # -- tokens --

    def test_tokens_per_deployment_present(self, result: ConsolidationResponse):
        tokens = result.charts["tokens"]
        assert "per_deployment" in tokens
        assert isinstance(tokens["per_deployment"], dict)
        assert len(tokens["per_deployment"]) == 3  # demo generates 3 siblings

    def test_tokens_per_deployment_has_prompt_and_completion(self, result: ConsolidationResponse):
        for name, data in result.charts["tokens"]["per_deployment"].items():
            assert "prompt" in data, f"Missing prompt for {name}"
            assert "completion" in data, f"Missing completion for {name}"
            assert len(data["prompt"]) == len(result.charts["tokens"]["timestamps"])
            assert len(data["completion"]) == len(result.charts["tokens"]["timestamps"])

    # -- requests --

    def test_requests_per_deployment_present(self, result: ConsolidationResponse):
        requests = result.charts["requests"]
        assert "per_deployment" in requests
        assert len(requests["per_deployment"]) == 3

    def test_requests_per_deployment_has_successful_and_throttled(
        self, result: ConsolidationResponse
    ):
        for name, data in result.charts["requests"]["per_deployment"].items():
            assert "successful" in data, f"Missing successful for {name}"
            assert "throttled" in data, f"Missing throttled for {name}"

    # -- tpm --

    def test_tpm_per_deployment_present(self, result: ConsolidationResponse):
        tpm = result.charts["tpm"]
        assert "per_deployment" in tpm
        assert len(tpm["per_deployment"]) == 3

    def test_tpm_per_deployment_values_aligned_to_timestamps(self, result: ConsolidationResponse):
        ts_len = len(result.charts["tpm"]["timestamps"])
        for name, values in result.charts["tpm"]["per_deployment"].items():
            assert len(values) == ts_len, f"TPM length mismatch for {name}"

    # -- throttling --

    def test_throttling_per_deployment_present(self, result: ConsolidationResponse):
        throttling = result.charts["throttling"]
        assert "per_deployment" in throttling
        assert len(throttling["per_deployment"]) == 3

    def test_throttling_per_deployment_values_aligned(self, result: ConsolidationResponse):
        ts_len = len(result.charts["throttling"]["timestamps"])
        for name, values in result.charts["throttling"]["per_deployment"].items():
            assert len(values) == ts_len, f"Throttling length mismatch for {name}"

    # -- latency (new section) --

    def test_latency_section_present(self, result: ConsolidationResponse):
        assert "latency" in result.charts
        latency = result.charts["latency"]
        assert "timestamps" in latency
        assert "combined" in latency
        assert "per_deployment" in latency

    def test_latency_combined_has_percentiles(self, result: ConsolidationResponse):
        combined = result.charts["latency"]["combined"]
        assert "p50" in combined
        assert "p95" in combined
        assert "p99" in combined
        ts_len = len(result.charts["latency"]["timestamps"])
        assert len(combined["p50"]) == ts_len
        assert len(combined["p95"]) == ts_len
        assert len(combined["p99"]) == ts_len

    def test_latency_per_deployment_has_percentiles(self, result: ConsolidationResponse):
        latency = result.charts["latency"]
        assert len(latency["per_deployment"]) == 3
        ts_len = len(latency["timestamps"])
        for name, data in latency["per_deployment"].items():
            assert "p50" in data, f"Missing p50 for {name}"
            assert "p95" in data, f"Missing p95 for {name}"
            assert "p99" in data, f"Missing p99 for {name}"
            assert len(data["p50"]) == ts_len
            assert len(data["p95"]) == ts_len
            assert len(data["p99"]) == ts_len

    # -- deployment names match summary --

    def test_per_deployment_names_match_summary(self, result: ConsolidationResponse):
        """Deployment keys in chart data should match the summary's individual deployments."""
        expected_names = {d.name for d in result.consolidation_summary.individual_deployments}
        tokens_names = set(result.charts["tokens"]["per_deployment"].keys())
        assert tokens_names == expected_names

        requests_names = set(result.charts["requests"]["per_deployment"].keys())
        assert requests_names == expected_names

        tpm_names = set(result.charts["tpm"]["per_deployment"].keys())
        assert tpm_names == expected_names

        latency_names = set(result.charts["latency"]["per_deployment"].keys())
        assert latency_names == expected_names


# ---------------------------------------------------------------------------
# Helpers for time-window / SKU tests
# ---------------------------------------------------------------------------


def _make_stub_metrics(
    name: str,
    start: datetime,
    end: datetime,
    sku_type: str = "Standard",
    model_name: str = "gpt-4o",
    num_points: int = 100,
) -> DeploymentMetrics:
    """Create a minimal but valid DeploymentMetrics for testing consolidation logic."""
    import numpy as np

    timestamps = [
        start + timedelta(seconds=i * (end - start).total_seconds() / max(num_points - 1, 1))
        for i in range(num_points)
    ]

    def _ts(metric_name: str, values: list) -> TimeSeries:
        return TimeSeries(timestamps=list(timestamps), values=values, metric_name=metric_name)

    base_tpm = np.random.uniform(800, 1200, num_points).tolist()
    prompt = [v * 0.6 for v in base_tpm]
    completion = [v * 0.4 for v in base_tpm]
    reqs = np.random.uniform(5, 15, num_points).tolist()
    throttled = np.random.uniform(0, 1, num_points).tolist()
    latency_vals = np.random.uniform(50, 200, num_points).tolist()

    m = DeploymentMetrics(
        deployment_name=name,
        model_name=model_name,
        start_time=start,
        end_time=end,
        timestamps=list(timestamps),
        tokens_per_minute=_ts("TotalTokens", base_tpm),
        prompt_tokens=_ts("ProcessedPromptTokens", prompt),
        completion_tokens=_ts("GeneratedTokens", completion),
        requests_per_minute=_ts("AzureOpenAIRequests", reqs),
        successful_requests=_ts("SuccessfulCalls", reqs),
        throttled_requests=_ts("Ratelimit", throttled),
        time_to_first_byte_p50=_ts("AzureOpenAITimeToResponse", latency_vals),
        time_to_first_byte_p95=_ts("AzureOpenAITimeToResponse", [v * 1.5 for v in latency_vals]),
        time_to_first_byte_p99=_ts("AzureOpenAITimeToResponse", [v * 2.0 for v in latency_vals]),
    )
    m.deployment_info = DeploymentInfo(
        name=name,
        model=model_name,
        sku_type=sku_type,
    )
    return m


# ---------------------------------------------------------------------------
# Time-window mismatch warnings (Phase 3)
# ---------------------------------------------------------------------------


class TestTimeWindowMismatchWarnings:
    """Tests for consolidation warnings when deployments have mismatched time windows."""

    def _run_with_custom_metrics(
        self, metrics_list: list[DeploymentMetrics]
    ) -> ConsolidationResponse:
        """Run consolidation with patched demo metrics."""
        with patch(
            "ptu_advisor.api.server.generate_consolidation_demo_metrics",
            return_value=metrics_list,
        ):
            return analyze_consolidation(_make_request())

    def test_no_warnings_when_time_windows_match(self):
        """Identical time windows should produce no warnings."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-a", start, now),
            _make_stub_metrics("dep-b", start, now),
        ]
        result = self._run_with_custom_metrics(metrics)
        # Filter out "already on PTU" warnings — we only care about time-window warnings
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        assert time_warnings == []

    def test_warning_when_one_deployment_starts_late(self):
        """Deployment that starts 3 days into a 7-day window (< 80% coverage) should warn."""
        now = datetime.now(timezone.utc)
        global_start = now - timedelta(days=7)
        late_start = now - timedelta(days=4)  # ~57% coverage
        metrics = [
            _make_stub_metrics("dep-a", global_start, now),
            _make_stub_metrics("dep-late", late_start, now),
        ]
        result = self._run_with_custom_metrics(metrics)
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        assert len(time_warnings) == 1
        assert "dep-late" in time_warnings[0]
        assert "0 TPM" in time_warnings[0]

    def test_warning_when_one_deployment_ends_early(self):
        """Deployment that ends early (< 80% coverage) should warn."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        early_end = now - timedelta(days=3)  # ~57% coverage
        metrics = [
            _make_stub_metrics("dep-a", start, now),
            _make_stub_metrics("dep-short", start, early_end),
        ]
        result = self._run_with_custom_metrics(metrics)
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        assert len(time_warnings) == 1
        assert "dep-short" in time_warnings[0]

    def test_no_warning_when_coverage_above_80_percent(self):
        """Deployment covering 90% of the span should NOT trigger a warning."""
        now = datetime.now(timezone.utc)
        global_start = now - timedelta(days=10)
        slightly_late = now - timedelta(days=9)  # 90% coverage
        metrics = [
            _make_stub_metrics("dep-a", global_start, now),
            _make_stub_metrics("dep-b", slightly_late, now),
        ]
        result = self._run_with_custom_metrics(metrics)
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        assert time_warnings == []

    def test_multiple_deployments_can_each_produce_warnings(self):
        """Two deployments with short coverage should each produce a warning."""
        now = datetime.now(timezone.utc)
        global_start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-full", global_start, now),
            _make_stub_metrics("dep-late", now - timedelta(days=3), now),  # 43%
            _make_stub_metrics("dep-short", global_start, now - timedelta(days=3)),  # 57%
        ]
        result = self._run_with_custom_metrics(metrics)
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        warned_names = {w.split("'")[1] for w in time_warnings}
        assert "dep-late" in warned_names
        assert "dep-short" in warned_names

    def test_default_demo_has_no_time_window_warnings(self):
        """Standard demo mode should not produce time-window warnings."""
        result = analyze_consolidation(_make_request())
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        assert time_warnings == []


# ---------------------------------------------------------------------------
# "Already on PTU" detection (Phase 3)
# ---------------------------------------------------------------------------


class TestAllOnPtuDetection:
    """Tests for the all_on_ptu flag and messaging when all deployments are ProvisionedManaged."""

    def _run_with_custom_metrics(
        self, metrics_list: list[DeploymentMetrics]
    ) -> ConsolidationResponse:
        with patch(
            "ptu_advisor.api.server.generate_consolidation_demo_metrics",
            return_value=metrics_list,
        ):
            return analyze_consolidation(_make_request())

    def test_all_on_ptu_when_all_provisioned_managed(self):
        """all_on_ptu should be True when every deployment is ProvisionedManaged."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-a", start, now, sku_type="ProvisionedManaged"),
            _make_stub_metrics("dep-b", start, now, sku_type="ProvisionedManaged"),
        ]
        result = self._run_with_custom_metrics(metrics)
        assert result.consolidation_summary.all_on_ptu is True

    def test_not_all_on_ptu_when_mixed_skus(self):
        """all_on_ptu should be False when deployments have mixed SKU types.

        NOTE: The current backend rejects mixed SKUs with a 422 error.
        This test verifies that mixed SKU deployments are indeed rejected.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-a", start, now, sku_type="Standard"),
            _make_stub_metrics("dep-b", start, now, sku_type="ProvisionedManaged"),
        ]
        with pytest.raises(HTTPException) as exc_info:
            self._run_with_custom_metrics(metrics)
        assert exc_info.value.status_code == 422
        assert "SKU types" in str(exc_info.value.detail)

    def test_not_all_on_ptu_when_all_standard(self):
        """all_on_ptu should be False when all deployments are Standard."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-a", start, now, sku_type="Standard"),
            _make_stub_metrics("dep-b", start, now, sku_type="Standard"),
        ]
        result = self._run_with_custom_metrics(metrics)
        assert result.consolidation_summary.all_on_ptu is False

    def test_all_on_ptu_warning_message(self):
        """When all_on_ptu is True, a specific warning message should be present."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        metrics = [
            _make_stub_metrics("dep-a", start, now, sku_type="ProvisionedManaged"),
            _make_stub_metrics("dep-b", start, now, sku_type="ProvisionedManaged"),
        ]
        result = self._run_with_custom_metrics(metrics)
        ptu_warnings = [w for w in result.consolidation_summary.warnings if "already use PTU" in w]
        assert len(ptu_warnings) == 1
        assert "PAYG cost" in ptu_warnings[0]

    def test_default_demo_not_all_on_ptu(self):
        """Standard demo uses Standard SKU, so all_on_ptu should be False."""
        result = analyze_consolidation(_make_request())
        assert result.consolidation_summary.all_on_ptu is False

    def test_warnings_field_is_list(self):
        """The warnings field should always be a list (possibly empty)."""
        result = analyze_consolidation(_make_request())
        assert isinstance(result.consolidation_summary.warnings, list)

    def test_all_on_ptu_combined_with_time_mismatch(self):
        """Both all_on_ptu and time-window warnings can coexist."""
        now = datetime.now(timezone.utc)
        global_start = now - timedelta(days=7)
        late_start = now - timedelta(days=3)  # < 80% coverage
        metrics = [
            _make_stub_metrics("dep-a", global_start, now, sku_type="ProvisionedManaged"),
            _make_stub_metrics("dep-late", late_start, now, sku_type="ProvisionedManaged"),
        ]
        result = self._run_with_custom_metrics(metrics)
        assert result.consolidation_summary.all_on_ptu is True
        time_warnings = [w for w in result.consolidation_summary.warnings if "no data for" in w]
        ptu_warnings = [w for w in result.consolidation_summary.warnings if "already use PTU" in w]
        assert len(time_warnings) == 1
        assert len(ptu_warnings) == 1


# ---------------------------------------------------------------------------
# Deployment preview endpoint (Phase 3)
# ---------------------------------------------------------------------------


def _call_preview(**kwargs):
    """Call deployment_preview with plain Python defaults (not FastAPI Query objects).

    When the endpoint function is called directly (not via FastAPI HTTP),
    Query() defaults are not resolved — they stay as Query objects. This
    helper fills in the defaults that FastAPI would normally inject.
    """
    defaults = {
        "mode": "demo",
        "deployments": "",
        "subscription_id": None,
        "resource_group": None,
        "workspace": None,
        "lookback_days": 7,
        "focus_topic": "Cost Reduction",
    }
    defaults.update(kwargs)
    return deployment_preview(**defaults)


class TestDeploymentPreviewDemoMode:
    """Tests for GET /api/deployments/preview in demo mode."""

    def test_returns_list_of_deployment_previews(self):
        """Demo preview should return a list of DeploymentPreview objects."""
        result = _call_preview()
        assert isinstance(result, list)
        assert len(result) == 3  # Demo generates 3 siblings
        for item in result:
            assert isinstance(item, DeploymentPreview)

    def test_each_preview_has_name_and_metrics(self):
        """Each preview should have a non-empty name, avg_tpm, and throttling_rate_pct."""
        result = _call_preview()
        for item in result:
            assert item.name
            assert isinstance(item.avg_tpm, float)
            assert isinstance(item.throttling_rate_pct, float)

    def test_avg_tpm_is_positive(self):
        """Demo deployments should have positive average TPM."""
        result = _call_preview()
        for item in result:
            assert item.avg_tpm > 0, f"{item.name} has avg_tpm={item.avg_tpm}"

    def test_throttling_rate_is_bounded(self):
        """Throttling rate should be between 0 and 100 percent."""
        result = _call_preview()
        for item in result:
            assert 0 <= item.throttling_rate_pct <= 100, (
                f"{item.name} has throttling_rate_pct={item.throttling_rate_pct}"
            )

    def test_cost_reduction_scenario_uses_gpt4o(self):
        """Cost Reduction focus_topic should produce gpt-4o deployments."""
        result = _call_preview(focus_topic="Cost Reduction")
        assert any("gpt-4o" in item.name for item in result)

    def test_non_cost_topic_uses_not_worth_it_scenario(self):
        """Non-Cost Reduction topic should use CONSOLIDATE_NOT_WORTH_IT (gpt-4o-mini)."""
        result = _call_preview(focus_topic="Throttling & Reliability")
        # The not-worth-it scenario uses gpt-4o-mini siblings
        names = [item.name for item in result]
        assert any("mini" in n for n in names)

    def test_lookback_days_respected(self):
        """Changing lookback_days should not error and should return 3 previews."""
        result = _call_preview(lookback_days=3)
        assert len(result) == 3

    def test_values_are_rounded(self):
        """Preview values should be rounded (no excessive decimal places)."""
        result = _call_preview()
        for item in result:
            # Check at most 1 decimal place
            assert item.avg_tpm == round(item.avg_tpm, 1)
            assert item.throttling_rate_pct == round(item.throttling_rate_pct, 1)


class TestDeploymentPreviewLiveMode:
    """Tests for GET /api/deployments/preview live mode validation."""

    def test_live_mode_requires_subscription_id(self):
        """Live mode without subscription_id should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call_preview(
                mode="live",
                deployments="dep-a,dep-b",
                resource_group="rg",
                workspace="ws",
            )
        assert exc_info.value.status_code == 400
        assert "subscription_id" in str(exc_info.value.detail)

    def test_live_mode_requires_resource_group(self):
        """Live mode without resource_group should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call_preview(
                mode="live",
                deployments="dep-a",
                subscription_id="sub-123",
                workspace="ws",
            )
        assert exc_info.value.status_code == 400

    def test_live_mode_requires_workspace(self):
        """Live mode without workspace should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call_preview(
                mode="live",
                deployments="dep-a",
                subscription_id="sub-123",
                resource_group="rg",
            )
        assert exc_info.value.status_code == 400

    def test_live_mode_requires_at_least_one_deployment(self):
        """Live mode with empty deployments string should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call_preview(
                mode="live",
                deployments="",
                subscription_id="sub-123",
                resource_group="rg",
                workspace="ws",
            )
        assert exc_info.value.status_code == 400
        assert "deployment" in str(exc_info.value.detail).lower()

    def test_live_mode_with_valid_params_calls_collector(self):
        """Live mode should instantiate MetricsCollector for each deployment."""
        mock_metrics = _make_stub_metrics(
            "dep-a",
            datetime.now(timezone.utc) - timedelta(days=7),
            datetime.now(timezone.utc),
        )
        with (
            patch("ptu_advisor.api.server.get_azure_credential"),
            patch("ptu_advisor.api.server.MetricsCollector") as mock_collector_cls,
        ):
            mock_collector_cls.return_value.collect.return_value = mock_metrics
            result = _call_preview(
                mode="live",
                deployments="dep-a,dep-b",
                subscription_id="sub-123",
                resource_group="rg",
                workspace="ws",
            )
        assert len(result) == 2
        assert mock_collector_cls.call_count == 2

    def test_live_mode_graceful_fallback_on_collection_error(self):
        """If MetricsCollector raises, the deployment should get zero values."""
        with (
            patch("ptu_advisor.api.server.get_azure_credential"),
            patch("ptu_advisor.api.server.MetricsCollector") as mock_collector_cls,
        ):
            mock_collector_cls.return_value.collect.side_effect = RuntimeError("fail")
            result = _call_preview(
                mode="live",
                deployments="dep-fail",
                subscription_id="sub-123",
                resource_group="rg",
                workspace="ws",
            )
        assert len(result) == 1
        assert result[0].name == "dep-fail"
        assert result[0].avg_tpm == 0.0
        assert result[0].throttling_rate_pct == 0.0

    def test_live_mode_strips_whitespace_from_deployment_names(self):
        """Deployment names should have whitespace stripped."""
        mock_metrics = _make_stub_metrics(
            "dep-a",
            datetime.now(timezone.utc) - timedelta(days=7),
            datetime.now(timezone.utc),
        )
        with (
            patch("ptu_advisor.api.server.get_azure_credential"),
            patch("ptu_advisor.api.server.MetricsCollector") as mock_collector_cls,
        ):
            mock_collector_cls.return_value.collect.return_value = mock_metrics
            result = _call_preview(
                mode="live",
                deployments="  dep-a , dep-b  ",
                subscription_id="sub-123",
                resource_group="rg",
                workspace="ws",
            )
        assert len(result) == 2
