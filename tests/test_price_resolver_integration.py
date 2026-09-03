"""Integration tests for PricingResolver against the live Azure Retail Prices API.

These tests hit the real API at https://prices.azure.com and verify that
resolved rates match the known Azure OpenAI pricing page. They are
excluded from the default test run — invoke with:

    pytest -m integration tests/test_price_resolver_integration.py

Expected pricing (as of March 2026, eastus, Global deployment):
    - GPT-4o:  $2.50/1M input, $10.00/1M output
    - GPT-4o-mini: $0.15/1M input, $0.60/1M output
    - Global Provisioned PTU: $1.00/PTU-hour (flat across all regions)
"""

from __future__ import annotations

import pytest

from ptu_advisor.cost.price_resolver import PricingResolver, PricingResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_httpx_available() -> bool:
    try:
        import httpx  # noqa: F401

        return True
    except ImportError:
        return False


skip_no_httpx = pytest.mark.skipif(
    not _check_httpx_available(),
    reason="httpx not installed — cannot run live API integration tests",
)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@skip_no_httpx
class TestLiveAPIResolution:
    """Verify resolver returns rates matching Azure pricing page for known models."""

    # Tolerance: rates should be within 5% of expected values.
    # This accounts for minor price adjustments between the time this test
    # was written and when it is run, while still catching gross errors
    # (e.g., wrong normalization, wrong meter matched).
    TOLERANCE = 0.05

    def _assert_close(self, actual: float, expected: float, label: str) -> None:
        if expected == 0:
            assert actual == 0, f"{label}: expected 0, got {actual}"
            return
        ratio = actual / expected
        assert 1 - self.TOLERANCE <= ratio <= 1 + self.TOLERANCE, (
            f"{label}: expected ~{expected}, got {actual} "
            f"(ratio {ratio:.4f}, tolerance {self.TOLERANCE})"
        )

    # --- GPT-4o / eastus / global -----------------------------------------

    def test_gpt4o_eastus_global_source_is_live(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)  # no cache
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        assert result.source == "live", (
            f"Expected source='live' but got '{result.source}'. "
            "This may mean the Azure Retail Prices API is unreachable."
        )

    def test_gpt4o_eastus_global_payg_input(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        self._assert_close(result.payg_input_rate, 2.50, "GPT-4o PAYG input (eastus)")

    def test_gpt4o_eastus_global_payg_output(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        self._assert_close(result.payg_output_rate, 10.00, "GPT-4o PAYG output (eastus)")

    def test_gpt4o_eastus_global_ptu_hourly(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        self._assert_close(result.ptu_hourly_rate, 1.00, "Global Provisioned PTU hourly (eastus)")

    # --- GPT-4o with version suffix ---------------------------------------

    def test_gpt4o_with_version_suffix(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o-2024-11-20", region="eastus", deployment_type="global")
        self._assert_close(result.payg_input_rate, 2.50, "GPT-4o (versioned) PAYG input")
        self._assert_close(result.payg_output_rate, 10.00, "GPT-4o (versioned) PAYG output")
        assert result.model_name == "gpt-4o-2024-11-20"

    # --- GPT-4o-mini / eastus / global ------------------------------------

    def test_gpt4o_mini_eastus_global_payg_input(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o-mini", region="eastus", deployment_type="global")
        self._assert_close(result.payg_input_rate, 0.15, "GPT-4o-mini PAYG input (eastus)")

    def test_gpt4o_mini_eastus_global_payg_output(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o-mini", region="eastus", deployment_type="global")
        self._assert_close(result.payg_output_rate, 0.60, "GPT-4o-mini PAYG output (eastus)")

    # --- Regional deployment type -----------------------------------------

    def test_gpt4o_eastus_regional_ptu_hourly(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="regional")
        self._assert_close(result.ptu_hourly_rate, 2.00, "Regional Provisioned PTU hourly (eastus)")

    # --- Different region (westeurope = tier 3, $2.40/hr regional) --------

    def test_gpt4o_westeurope_regional_ptu_hourly(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="westeurope", deployment_type="regional")
        self._assert_close(
            result.ptu_hourly_rate, 2.40, "Regional Provisioned PTU hourly (westeurope)"
        )

    # --- Result metadata --------------------------------------------------

    def test_result_metadata_fields(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=0)
        result = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        assert result.currency == "USD"
        assert result.model_name == "gpt-4o"
        assert result.region == "eastus"
        assert result.deployment_type == "global"
        assert result.as_of is not None

    # --- Cache interaction ------------------------------------------------

    def test_second_call_uses_cache(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=24)
        first = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        assert first.source == "live"
        second = resolver.resolve("gpt-4o", region="eastus", deployment_type="global")
        assert second.source == "cached"
        # Rates should be identical
        assert first.payg_input_rate == second.payg_input_rate
        assert first.payg_output_rate == second.payg_output_rate
        assert first.ptu_hourly_rate == second.ptu_hourly_rate
