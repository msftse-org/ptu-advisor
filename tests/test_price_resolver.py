"""Tests for ptu_advisor.cost.price_resolver — live pricing resolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from ptu_advisor.cost.price_resolver import (
    DEFAULT_PAYG_INPUT,
    DEFAULT_PAYG_OUTPUT,
    MODEL_METER_PATTERNS,
    STATIC_PAYG_RATES,
    STATIC_PTU_HOURLY,
    STATIC_REGIONAL_PTU_RATES,
    PricingResolver,
    PricingResult,
    get_pricing_resolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_response(items: list[Dict[str, Any]]) -> Dict[str, Any]:
    return {"Items": items, "BillingCurrency": "USD", "CustomerEntityId": "Default"}


def _payg_item(
    meter_name: str,
    unit_price: float,
    region: str = "eastus",
    uom: str = "1K",
) -> Dict[str, Any]:
    return {
        "currencyCode": "USD",
        "unitPrice": unit_price,
        "armRegionName": region,
        "meterName": meter_name,
        "serviceName": "Foundry Models",
        "unitOfMeasure": uom,
        "type": "Consumption",
        "effectiveStartDate": "2025-11-01T00:00:00Z",
    }


def _ptu_item(meter_name: str, unit_price: float, region: str = "eastus") -> Dict[str, Any]:
    return {
        "currencyCode": "USD",
        "unitPrice": unit_price,
        "armRegionName": region,
        "meterName": meter_name,
        "serviceName": "Foundry Models",
        "unitOfMeasure": "1 Hour",
        "type": "Consumption",
        "effectiveStartDate": "2025-11-01T00:00:00Z",
    }


def _route_api_calls(
    payg_items: list[Dict[str, Any]],
    ptu_items: list[Dict[str, Any]],
) -> Any:
    """Return a side_effect function that routes httpx.get calls.

    The resolver calls the API multiple times:
    - PAYG: iterates service names × meter patterns (stops on first hit)
    - PTU: iterates service names (stops on first hit)

    This helper inspects the ``$filter`` param to decide whether to return
    PAYG items or PTU items (based on 'Provisioned' in the filter).
    """

    def _side_effect(*args: Any, **kwargs: Any) -> FakeResponse:
        params = kwargs.get("params", {})
        odata_filter = params.get("$filter", "")
        if "Provisioned" in odata_filter:
            return FakeResponse(_make_api_response(ptu_items))
        return FakeResponse(_make_api_response(payg_items))

    return _side_effect


class FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, data: Dict[str, Any], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._data


# ---------------------------------------------------------------------------
# Tests: model normalization
# ---------------------------------------------------------------------------


class TestModelNormalization:
    def test_exact_match(self) -> None:
        assert PricingResolver._normalize_model("gpt-4o") == "gpt-4o"

    def test_versioned_model(self) -> None:
        assert PricingResolver._normalize_model("gpt-4o-2024-11-20") == "gpt-4o"

    def test_mini_model(self) -> None:
        assert PricingResolver._normalize_model("gpt-4.1-mini-2025-04-14") == "gpt-4.1-mini"

    def test_o_model(self) -> None:
        assert PricingResolver._normalize_model("o4-mini-2025-04-16") == "o4-mini"

    def test_unknown_model(self) -> None:
        assert PricingResolver._normalize_model("totally-new-model") == "totally-new-model"

    def test_empty_string(self) -> None:
        assert PricingResolver._normalize_model("") == ""

    def test_prefers_longer_prefix(self) -> None:
        # "gpt-4.1-mini" should match over "gpt-4.1"
        assert PricingResolver._normalize_model("gpt-4.1-mini-2025-04") == "gpt-4.1-mini"

    def test_gpt5(self) -> None:
        assert PricingResolver._normalize_model("gpt-5-turbo-2026-01-01") == "gpt-5"


# ---------------------------------------------------------------------------
# Tests: static fallback
# ---------------------------------------------------------------------------


@patch("ptu_advisor.cost.price_resolver._httpx", None)
class TestStaticFallback:
    def test_known_model_global(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")
        assert result.source == "fallback"
        assert result.payg_input_rate == 2.50
        assert result.payg_output_rate == 10.00
        assert result.ptu_hourly_rate == 1.00  # global flat rate
        assert result.currency == "USD"
        assert result.model_name == "gpt-4o"
        assert result.region == "eastus"

    def test_known_model_data_zone(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "westeurope", "data_zone")
        assert result.ptu_hourly_rate == 1.10  # data zone flat rate

    def test_known_model_regional_tier1(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "regional")
        assert result.ptu_hourly_rate == 2.00

    def test_known_model_regional_tier2(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "switzerlandnorth", "regional")
        assert result.ptu_hourly_rate == 2.20

    def test_known_model_regional_tier3(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "brazilsouth", "regional")
        assert result.ptu_hourly_rate == 2.40

    def test_unknown_model_uses_default(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("mystery-model-9000", "eastus", "global")
        assert result.payg_input_rate == DEFAULT_PAYG_INPUT
        assert result.payg_output_rate == DEFAULT_PAYG_OUTPUT

    def test_all_static_payg_models_covered(self) -> None:
        resolver = PricingResolver()
        for model, (expected_input, expected_output) in STATIC_PAYG_RATES.items():
            result = resolver.resolve(model, "eastus", "global")
            assert result.payg_input_rate == expected_input, f"{model} input rate mismatch"
            assert result.payg_output_rate == expected_output, f"{model} output rate mismatch"


# ---------------------------------------------------------------------------
# Tests: manual overrides
# ---------------------------------------------------------------------------


class TestManualOverrides:
    def test_all_overrides(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve(
            "gpt-4o",
            "eastus",
            "global",
            payg_input_override=5.0,
            payg_output_override=20.0,
            ptu_hourly_override=3.0,
        )
        assert result.source == "manual"
        assert result.payg_input_rate == 5.0
        assert result.payg_output_rate == 20.0
        assert result.ptu_hourly_rate == 3.0

    def test_partial_override_fills_from_fallback(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve(
            "gpt-4o",
            "eastus",
            "global",
            payg_input_override=5.0,
        )
        assert result.source == "manual"
        assert result.payg_input_rate == 5.0
        assert result.payg_output_rate == 10.0  # fallback
        assert result.ptu_hourly_rate == 1.00  # fallback

    def test_override_takes_priority_over_cache(self) -> None:
        resolver = PricingResolver()
        # Warm the cache
        resolver.resolve("gpt-4o", "eastus", "global")
        # Override should still win
        result = resolver.resolve(
            "gpt-4o",
            "eastus",
            "global",
            ptu_hourly_override=99.0,
        )
        assert result.source == "manual"
        assert result.ptu_hourly_rate == 99.0


# ---------------------------------------------------------------------------
# Tests: cache behavior
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_hit_returns_cached_source(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=24)
        now = datetime.now(timezone.utc)

        # Manually seed the cache
        cached_result = PricingResult(
            payg_input_rate=1.11,
            payg_output_rate=2.22,
            ptu_hourly_rate=3.33,
            source="live",
            as_of=now,
            model_name="gpt-4o",
            region="eastus",
            deployment_type="global",
        )
        resolver._cache["gpt-4o:eastus:global"] = (cached_result, now)

        result = resolver.resolve("gpt-4o", "eastus", "global")
        assert result.source == "cached"
        assert result.payg_input_rate == 1.11

    @patch("ptu_advisor.cost.price_resolver._httpx", None)
    def test_cache_ttl_expiry(self) -> None:
        resolver = PricingResolver(cache_ttl_hours=1)
        expired_time = datetime.now(timezone.utc) - timedelta(hours=2)

        cached_result = PricingResult(
            payg_input_rate=1.11,
            payg_output_rate=2.22,
            ptu_hourly_rate=3.33,
            source="live",
            as_of=expired_time,
            model_name="gpt-4o",
            region="eastus",
            deployment_type="global",
        )
        resolver._cache["gpt-4o:eastus:global"] = (cached_result, expired_time)

        # With no live API available, should fall through to fallback
        result = resolver.resolve("gpt-4o", "eastus", "global")
        assert result.source == "fallback"
        assert resolver.cache_size == 0  # expired entry evicted

    def test_clear_cache(self) -> None:
        resolver = PricingResolver()
        now = datetime.now(timezone.utc)
        resolver._cache["test:key:1"] = (
            PricingResult(
                payg_input_rate=1,
                payg_output_rate=1,
                ptu_hourly_rate=1,
                source="live",
                as_of=now,
            ),
            now,
        )
        assert resolver.cache_size == 1
        resolver.clear_cache()
        assert resolver.cache_size == 0


# ---------------------------------------------------------------------------
# Tests: live API fetch
# ---------------------------------------------------------------------------


class TestLiveFetch:
    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_successful_live_fetch(self, mock_httpx: MagicMock) -> None:
        """Simulate a successful API call returning PAYG + PTU rates."""
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.0025),  # $2.50/1M
                _payg_item("gpt 4o 1120 Outp glbl Tokens", 0.01),  # $10.00/1M
            ],
            ptu_items=[
                _ptu_item("Global Provisioned Managed Base Unit", 1.00),
            ],
        )

        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")

        assert result.source == "live"
        assert result.payg_input_rate == pytest.approx(2.50, rel=0.01)
        assert result.payg_output_rate == pytest.approx(10.00, rel=0.01)
        assert result.ptu_hourly_rate == 1.00
        assert resolver.cache_size == 1  # result was cached

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_live_fetch_caches_result(self, mock_httpx: MagicMock) -> None:
        """Second call should return cached result, not hit API again."""
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.0025),
                _payg_item("gpt 4o 1120 Outp glbl Tokens", 0.01),
            ],
            ptu_items=[
                _ptu_item("Global Provisioned Managed Base Unit", 1.00),
            ],
        )

        resolver = PricingResolver()
        result1 = resolver.resolve("gpt-4o", "eastus", "global")
        assert result1.source == "live"

        call_count_after_first = mock_httpx.get.call_count

        # Second call — should be cached, no more API calls
        result2 = resolver.resolve("gpt-4o", "eastus", "global")
        assert result2.source == "cached"
        assert mock_httpx.get.call_count == call_count_after_first  # no new calls

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_api_error_falls_back(self, mock_httpx: MagicMock) -> None:
        """When the API fails, we should get a fallback result."""
        mock_httpx.get.side_effect = Exception("Connection refused")

        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")

        assert result.source == "fallback"
        assert result.payg_input_rate == 2.50
        assert resolver.cache_size == 0

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_empty_api_response_falls_back(self, mock_httpx: MagicMock) -> None:
        """API returns 200 but no items."""
        mock_httpx.get.return_value = FakeResponse(_make_api_response([]))

        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")

        assert result.source == "fallback"

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_partial_api_response_fills_gaps(self, mock_httpx: MagicMock) -> None:
        """API returns only input rate — output and PTU should come from fallback."""
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.003),  # $3.00/1M
            ],
            ptu_items=[],
        )

        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")

        assert result.source == "live"
        assert result.payg_input_rate == pytest.approx(3.00, rel=0.01)
        assert result.payg_output_rate == 10.00  # fallback
        assert result.ptu_hourly_rate == 1.00  # fallback


# ---------------------------------------------------------------------------
# Tests: sanity check
# ---------------------------------------------------------------------------


class TestSanityCheck:
    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_absurd_rate_rejected(self, mock_httpx: MagicMock) -> None:
        """A rate 200x the fallback should be rejected."""
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                # $500/1M (200x the $2.50 fallback) — absurd
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.5),
                _payg_item("gpt 4o 1120 Outp glbl Tokens", 0.01),
            ],
            ptu_items=[],
        )

        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")

        assert result.source == "fallback"
        assert result.payg_input_rate == 2.50  # fallback, not 500

    def test_sanity_check_passes_for_reasonable_rates(self) -> None:
        now = datetime.now(timezone.utc)
        live = PricingResult(
            payg_input_rate=2.60,
            payg_output_rate=10.50,
            ptu_hourly_rate=1.05,
            source="live",
            as_of=now,
        )
        fallback = PricingResult(
            payg_input_rate=2.50,
            payg_output_rate=10.00,
            ptu_hourly_rate=1.00,
            source="fallback",
            as_of=now,
        )
        assert PricingResolver._passes_sanity_check(live, fallback) is True

    def test_sanity_check_fails_for_extreme_rates(self) -> None:
        now = datetime.now(timezone.utc)
        live = PricingResult(
            payg_input_rate=50000.0,
            payg_output_rate=10.00,
            ptu_hourly_rate=1.00,
            source="live",
            as_of=now,
        )
        fallback = PricingResult(
            payg_input_rate=2.50,
            payg_output_rate=10.00,
            ptu_hourly_rate=1.00,
            source="fallback",
            as_of=now,
        )
        assert PricingResolver._passes_sanity_check(live, fallback) is False


# ---------------------------------------------------------------------------
# Tests: rate normalization
# ---------------------------------------------------------------------------


class TestRateNormalization:
    def test_per_token(self) -> None:
        assert PricingResolver._normalize_rate(0.0000025, "1 Token") == pytest.approx(2.50)

    def test_per_1k(self) -> None:
        assert PricingResolver._normalize_rate(0.0025, "1K Tokens") == pytest.approx(2.50)

    def test_per_1m(self) -> None:
        assert PricingResolver._normalize_rate(2.50, "1M Tokens") == pytest.approx(2.50)

    def test_unknown_uom_assumes_per_token(self) -> None:
        assert PricingResolver._normalize_rate(0.0000025, "Something") == pytest.approx(2.50)


# ---------------------------------------------------------------------------
# Tests: singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_pricing_resolver_returns_same_instance(self) -> None:
        r1 = get_pricing_resolver()
        r2 = get_pricing_resolver()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Tests: regional PTU rate accuracy
# ---------------------------------------------------------------------------


class TestRegionalPTURates:
    """Verify the static regional PTU rate data matches the 3-tier structure
    discovered from the Azure Retail Prices API."""

    TIER1_REGIONS = [
        "eastus",
        "eastus2",
        "westus",
        "westus2",
        "westus3",
        "centralus",
        "northcentralus",
        "southcentralus",
        "australiaeast",
        "southindia",
    ]
    TIER2_REGIONS = [
        "canadacentral",
        "canadaeast",
        "northeurope",
        "uksouth",
        "ukwest",
        "francecentral",
        "germanywestcentral",
        "norwayeast",
        "switzerlandnorth",
        "swedencentral",
        "japaneast",
        "japanwest",
        "koreacentral",
        "koreasouth",
        "eastasia",
        "uaenorth",
        "qatarcentral",
        "polandcentral",
        "centralindia",
        "southafricanorth",
    ]
    TIER3_REGIONS = [
        "brazilsouth",
        "southeastasia",
        "westeurope",
        "australiasoutheast",
        "westindia",
    ]

    @pytest.mark.parametrize("region", TIER1_REGIONS)
    def test_tier1_rate(self, region: str) -> None:
        assert STATIC_REGIONAL_PTU_RATES[region] == 2.00

    @pytest.mark.parametrize("region", TIER2_REGIONS)
    def test_tier2_rate(self, region: str) -> None:
        assert STATIC_REGIONAL_PTU_RATES[region] == 2.20

    @pytest.mark.parametrize("region", TIER3_REGIONS)
    def test_tier3_rate(self, region: str) -> None:
        assert STATIC_REGIONAL_PTU_RATES[region] == 2.40
