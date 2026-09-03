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


def _ptu_item(
    meter_name: str,
    unit_price: float,
    region: str = "eastus",
    product_name: str = "Azure OpenAI",
) -> Dict[str, Any]:
    return {
        "currencyCode": "USD",
        "unitPrice": unit_price,
        "armRegionName": region,
        "meterName": meter_name,
        "serviceName": "Foundry Models",
        "productName": product_name,
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
        assert PricingResolver._normalize_model("gpt-4o-2024-11-20") == "gpt-4o-2024-11-20"

    def test_parenthesized_versioned_model(self) -> None:
        assert (
            PricingResolver._normalize_model("gpt-4o (2024-11-20)")
            == "gpt-4o-2024-11-20"
        )

    def test_parenthesized_versioned_mini_model(self) -> None:
        assert (
            PricingResolver._normalize_model("gpt-4o-mini (2024-07-18)")
            == "gpt-4o-mini"
        )

    def test_mini_model(self) -> None:
        assert PricingResolver._normalize_model("gpt-4.1-mini-2025-04-14") == "gpt-4.1-mini"

    def test_o_model(self) -> None:
        assert PricingResolver._normalize_model("o4-mini-2025-04-16") == "o4-mini"

    def test_unknown_model(self) -> None:
        assert PricingResolver._normalize_model("totally-new-model") == "totally-new-model"

    def test_empty_string(self) -> None:
        assert PricingResolver._normalize_model("") == ""

    def test_prefers_longer_prefix(self) -> None:
        assert PricingResolver._normalize_model("gpt-4.1-mini-2025-04") == "gpt-4.1-mini-2025-04"

    def test_gpt5(self) -> None:
        assert PricingResolver._normalize_model("gpt-5-turbo-2026-01-01") == "gpt-5-turbo-2026-01-01"

    @pytest.mark.parametrize("model", ["gpt-5.4-pro", "gpt-5.4-longco", "gpt-5.2-pro"])
    def test_unknown_gpt5_siblings_do_not_collapse_to_base(self, model: str) -> None:
        assert PricingResolver._normalize_model(model) == model

    @pytest.mark.parametrize(
        "model",
        ["gpt-5-mini", "gpt-5.1", "gpt-5.2", "gpt-5.3-codex", "gpt-5.4", "gpt-5.4-mini", "gpt-5.5"],
    )
    def test_gpt5_variants_do_not_collapse_to_base_model(self, model: str) -> None:
        assert PricingResolver._normalize_model(model) == model


# ---------------------------------------------------------------------------
# Tests: static fallback
# ---------------------------------------------------------------------------


@patch("ptu_advisor.cost.price_resolver._httpx", None)
class TestStaticFallback:
    def test_gpt4o_0513_does_not_receive_unsupported_cache_discount(self) -> None:
        result = PricingResolver().resolve("gpt-4o-2024-05-13", "eastus", "global")

        assert result.payg_input_rate == pytest.approx(5.0)
        assert result.payg_cached_input_rate == pytest.approx(5.0)
        assert result.payg_output_rate == pytest.approx(15.0)
        assert result.cached_input_source == "conservative"

    def test_invalid_deployment_type_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="deployment_type"):
            PricingResolver().resolve("gpt-4o", "eastus", "globall")

    def test_known_model_global(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "global")
        assert result.source == "fallback"
        assert result.payg_input_rate == 2.50
        assert result.payg_cached_input_rate == 1.25
        assert result.cached_input_source == "fallback"
        assert result.payg_output_rate == 10.00
        assert result.ptu_hourly_rate == 1.00  # global flat rate
        assert result.currency == "USD"
        assert result.model_name == "gpt-4o"
        assert result.region == "eastus"

    def test_known_model_data_zone(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "westeurope", "data_zone")
        assert result.ptu_hourly_rate == 1.10  # data zone flat rate
        assert result.payg_input_rate == pytest.approx(2.75)
        assert result.payg_cached_input_rate == pytest.approx(1.375)
        assert result.payg_output_rate == pytest.approx(11.0)
        assert result.cached_input_source == "fallback"

    def test_known_model_regional_tier1(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "eastus", "regional")
        assert result.ptu_hourly_rate == 2.00
        assert result.payg_input_rate == pytest.approx(2.75)
        assert result.payg_cached_input_rate == pytest.approx(1.375)
        assert result.payg_output_rate == pytest.approx(11.0)

    @pytest.mark.parametrize(
        ("model", "deployment_type", "expected"),
        [
            ("gpt-4.1", "data_zone", (2.2, 0.55, 8.8)),
            ("gpt-4.1-mini", "regional", (0.44, 0.11, 1.76)),
            ("o1", "global", (15.0, 7.5, 60.0)),
            ("o3-mini", "data_zone", (1.21, 0.605, 4.84)),
            ("o4-mini", "global", (1.10, 0.275, 4.40)),
            ("gpt-5.2", "global", (1.75, 0.175, 14.0)),
            ("gpt-5.4-mini", "data_zone", (0.825, 0.0825, 4.95)),
        ],
    )
    def test_scoped_static_token_rates(
        self,
        model: str,
        deployment_type: str,
        expected: tuple[float, float, float],
    ) -> None:
        result = PricingResolver().resolve(model, "eastus", deployment_type)

        assert (
            result.payg_input_rate,
            result.payg_cached_input_rate,
            result.payg_output_rate,
        ) == pytest.approx(expected)
        assert result.cached_input_source == "fallback"

    def test_known_model_regional_tier2(self) -> None:
        resolver = PricingResolver()
        result = resolver.resolve("gpt-4o", "switzerlandnorth", "regional")
        assert result.ptu_hourly_rate == 2.20
        assert result.payg_cached_input_rate == result.payg_input_rate
        assert result.cached_input_source == "conservative"

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
            payg_cached_input_override=1.25,
            ptu_hourly_override=3.0,
        )
        assert result.source == "manual"
        assert result.payg_input_rate == 5.0
        assert result.payg_output_rate == 20.0
        assert result.payg_cached_input_rate == 1.25
        assert result.cached_input_source == "manual"
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
        assert result.payg_cached_input_rate == 5.0
        assert result.cached_input_source == "conservative"
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
    def test_live_fetch_matches_current_global_ptu_meter_name(
        self, mock_httpx: MagicMock
    ) -> None:
        payg_items = [
            _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.0025),
            _payg_item("gpt 4o 1120 cached Inp glbl Tokens", 0.00125),
            _payg_item("gpt 4o 1120 Outp glbl Tokens", 0.01),
        ]

        def route(*args: Any, **kwargs: Any) -> FakeResponse:
            filter_text = kwargs.get("params", {}).get("$filter", "")
            if "Provisioned Managed Global" in filter_text:
                return FakeResponse(
                    _make_api_response([_ptu_item("Provisioned Managed Global Unit", 1.00)])
                )
            if "Provisioned" in filter_text:
                return FakeResponse(_make_api_response([]))
            return FakeResponse(_make_api_response(payg_items))

        mock_httpx.get.side_effect = route

        result = PricingResolver().resolve("gpt-4o-2024-11-20", "eastus", "global")

        assert result.source == "live"
        assert result.cached_input_source == "live"
        assert result.ptu_pricing_source == "live"

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_live_fetch_resolves_cached_input_meter(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.0025),
                _payg_item("gpt 4o 1120 Cchd Inp glbl Tokens", 0.00125),
                _payg_item("gpt 4o 1120 Outp glbl Tokens", 0.01),
            ],
            ptu_items=[_ptu_item("Global Provisioned Managed Base Unit", 1.00)],
        )

        result = PricingResolver().resolve("gpt-4o", "eastus", "global")

        assert result.payg_cached_input_rate == pytest.approx(1.25, rel=0.01)
        assert result.cached_input_source == "live"

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_gpt41_live_fetch_includes_cached_and_output_meters(
        self, mock_httpx: MagicMock
    ) -> None:
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4.1 Inp glbl Tokens", 0.002),
                _payg_item("gpt 4.1 cached Inp glbl Tokens", 0.0005),
                _payg_item("gpt 4.1 Outp glbl Tokens", 0.008),
            ],
            ptu_items=[_ptu_item("Global Provisioned Managed Base Unit", 1.00)],
        )

        result = PricingResolver().resolve("gpt-4.1", "eastus", "global")

        assert result.payg_input_rate == pytest.approx(2.0)
        assert result.payg_cached_input_rate == pytest.approx(0.5)
        assert result.payg_output_rate == pytest.approx(8.0)

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_gpt52_cd_input_is_not_classified_as_standard_input(
        self, mock_httpx: MagicMock
    ) -> None:
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("GPT 5.2 inp Gl 1M Tokens", 1.75, uom="1M"),
                _payg_item("GPT 5.2 cd inp Gl 1M Tokens", 0.175, uom="1M"),
                _payg_item("GPT 5.2 opt Gl 1M Tokens", 14.0, uom="1M"),
                _payg_item("GPT 5.2 chat inp Gl 1M Tokens", 1.75, uom="1M"),
            ],
            ptu_items=[_ptu_item("Global Provisioned Managed Base Unit", 1.00)],
        )

        result = PricingResolver().resolve("gpt-5.2", "eastus", "global")

        assert result.payg_input_rate == pytest.approx(1.75)
        assert result.payg_cached_input_rate == pytest.approx(0.175)
        assert result.payg_output_rate == pytest.approx(14.0)

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_live_fetch_combines_rates_across_meter_patterns(
        self, mock_httpx: MagicMock
    ) -> None:
        def route(*args: Any, **kwargs: Any) -> FakeResponse:
            filter_text = kwargs.get("params", {}).get("$filter", "")
            if "Provisioned" in filter_text:
                return FakeResponse(
                    _make_api_response([_ptu_item("Global Provisioned Managed Base Unit", 1.0)])
                )
            if "gpt 4o mini 0718" in filter_text:
                return FakeResponse(
                    _make_api_response(
                        [_payg_item("gpt 4o mini 0718 cached Inp glbl Tokens", 0.000075)]
                    )
                )
            if "gpt-4o-mini-0718" in filter_text:
                return FakeResponse(
                    _make_api_response(
                        [
                            _payg_item("gpt-4o-mini-0718-Inp-glbl Tokens", 0.00015),
                            _payg_item("gpt-4o-mini-0718-Outp-glbl Tokens", 0.0006),
                        ]
                    )
                )
            return FakeResponse(_make_api_response([]))

        mock_httpx.get.side_effect = route

        result = PricingResolver().resolve("gpt-4o-mini", "eastus", "global")

        assert result.payg_input_rate == pytest.approx(0.15)
        assert result.payg_cached_input_rate == pytest.approx(0.075)
        assert result.payg_output_rate == pytest.approx(0.6)

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_standard_meters_exclude_priority_processing(self, mock_httpx: MagicMock) -> None:
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("5.4 mini pp Inp Gl 1M Tokens", 1.5, uom="1M"),
                _payg_item("5.4 mini pp cd Inp Gl 1M Tokens", 0.15, uom="1M"),
                _payg_item("5.4 mini pp Opt Gl 1M Tokens", 9.0, uom="1M"),
                _payg_item("5.4 mini Inp Gl 1M Tokens", 0.75, uom="1M"),
                _payg_item("5.4 mini cd Inp Gl 1M Tokens", 0.075, uom="1M"),
                _payg_item("5.4 mini Opt Gl 1M Tokens", 4.5, uom="1M"),
            ],
            ptu_items=[_ptu_item("Global Provisioned Managed Base Unit", 1.0)],
        )

        result = PricingResolver().resolve("gpt-5.4-mini", "eastus", "global")

        assert result.payg_input_rate == pytest.approx(0.75)
        assert result.payg_cached_input_rate == pytest.approx(0.075)
        assert result.payg_output_rate == pytest.approx(4.5)

    @patch("ptu_advisor.cost.price_resolver._httpx")
    def test_successful_live_fetch(self, mock_httpx: MagicMock) -> None:
        """Simulate a successful API call returning PAYG + PTU rates."""
        mock_httpx.get.side_effect = _route_api_calls(
            payg_items=[
                _payg_item("gpt 4o 1120 Inp glbl Tokens", 0.0025),  # $2.50/1M
                _payg_item("gpt 4o 1120 cached Inp glbl Tokens", 0.00125),
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
                _payg_item("gpt 4o 1120 cached Inp glbl Tokens", 0.00125),
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

        assert result.source == "fallback"
        assert result.payg_input_rate == pytest.approx(3.00, rel=0.01)
        assert result.payg_output_rate == 10.00  # fallback
        assert result.payg_cached_input_rate == 3.00  # no unverified discount
        assert result.cached_input_source == "conservative"
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


# ---------------------------------------------------------------------------
# Tests: structured logging (_log_resolution)
# ---------------------------------------------------------------------------


class TestStructuredLogging:
    def test_log_resolution_emits_info(self) -> None:
        """_log_resolution should emit a structured logger.info call."""
        result = PricingResult(
            payg_input_rate=2.50,
            payg_output_rate=10.00,
            ptu_hourly_rate=1.00,
            source="live",
            as_of=datetime.now(timezone.utc),
            model_name="gpt-4o",
            region="eastus",
            deployment_type="global",
        )
        with patch("ptu_advisor.cost.price_resolver.logger") as mock_logger:
            PricingResolver._log_resolution(result, 0.042)
            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "pricing_resolved" in log_msg
            assert "model=%s" in log_msg
            # Verify the positional args contain key values
            args = mock_logger.info.call_args[0]
            assert "gpt-4o" in args
            assert "eastus" in args
            assert "live" in args

    def test_log_resolution_latency_ms(self) -> None:
        """Latency should be passed as milliseconds."""
        result = PricingResult(
            payg_input_rate=1.0,
            payg_output_rate=2.0,
            ptu_hourly_rate=3.0,
            source="fallback",
            as_of=datetime.now(timezone.utc),
        )
        with patch("ptu_advisor.cost.price_resolver.logger") as mock_logger:
            PricingResolver._log_resolution(result, 0.123)
            args = mock_logger.info.call_args[0]
            # The latency_ms positional arg should be ~123.0
            latency_ms = args[5]  # positional: msg, model, region, dtype, source, latency_ms, ...
            assert abs(latency_ms - 123.0) < 0.1


# ---------------------------------------------------------------------------
# Tests: cache warm-up
# ---------------------------------------------------------------------------


class TestCacheWarmup:
    @patch("ptu_advisor.cost.price_resolver._httpx", None)
    def test_warm_cache_returns_count(self) -> None:
        """warm_cache should return the number of successfully warmed combos."""
        resolver = PricingResolver()
        # With httpx=None, all will go to fallback (not "live" or "cached")
        warmed = resolver.warm_cache()
        assert warmed == 0  # fallback is not counted as "warmed"

    @patch("ptu_advisor.cost.price_resolver._httpx", None)
    def test_warm_cache_custom_combos(self) -> None:
        """warm_cache accepts a custom combos list."""
        resolver = PricingResolver()
        # Manually seed one cache entry so it counts as "cached"
        now = datetime.now(timezone.utc)
        resolver._cache["gpt-4o:eastus:global"] = (
            PricingResult(
                payg_input_rate=2.5,
                payg_output_rate=10.0,
                ptu_hourly_rate=1.0,
                source="live",
                as_of=now,
                model_name="gpt-4o",
                region="eastus",
                deployment_type="global",
            ),
            now,
        )
        warmed = resolver.warm_cache(combos=[("gpt-4o", "eastus", "global")])
        assert warmed == 1  # should hit cache → "cached" counts

    @patch("ptu_advisor.cost.price_resolver._httpx", None)
    def test_warm_cache_handles_errors(self) -> None:
        """warm_cache should not raise even if resolve throws."""
        resolver = PricingResolver()
        # Monkeypatch resolve to raise
        original_resolve = resolver.resolve
        call_count = 0

        def _failing_resolve(*args: Any, **kwargs: Any) -> PricingResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("test error")
            return original_resolve(*args, **kwargs)

        resolver.resolve = _failing_resolve  # type: ignore[assignment]
        warmed = resolver.warm_cache(
            combos=[("gpt-4o", "eastus", "global"), ("gpt-5", "eastus", "global")]
        )
        assert warmed == 0  # first fails, second goes to fallback (not counted)
        assert call_count == 2

    @patch("ptu_advisor.cost.price_resolver._httpx", None)
    def test_start_background_warmup_returns_daemon_thread(self) -> None:
        """start_background_warmup should return a running daemon thread."""
        resolver = PricingResolver()
        thread = resolver.start_background_warmup(interval_seconds=999999)
        try:
            assert thread.is_alive()
            assert thread.daemon is True
            assert thread.name == "pricing-cache-warmup"
        finally:
            resolver.stop_background_warmup()

    def test_background_warmup_start_is_idempotent(self) -> None:
        resolver = PricingResolver()

        first = resolver.start_background_warmup(interval_seconds=999999)
        second = resolver.start_background_warmup(interval_seconds=999999)
        try:
            assert second is first
        finally:
            resolver.stop_background_warmup()

    def test_background_warmup_can_stop_while_waiting(self) -> None:
        resolver = PricingResolver()
        resolver.warm_cache = lambda combos=None: 0  # type: ignore[assignment]

        thread = resolver.start_background_warmup(interval_seconds=999999)
        resolver.stop_background_warmup(timeout_seconds=1.0)

        assert thread.is_alive() is False


# ---------------------------------------------------------------------------
# Tests: _build_formula_blocks "(custom rate)" annotation
# ---------------------------------------------------------------------------


class TestFormulaBlocksCustomRateAnnotation:
    """Phase 2.1: _build_formula_blocks annotates with '(custom rate)' when source is manual."""

    def _common_kwargs(self, pricing_source: str = "") -> Dict[str, Any]:
        return dict(
            avg_tpm=10000,
            total_tokens=432_000_000,
            lookback_days=14,
            avg_daily_tokens=14_400_000,
            payg_input_rate=2.50,
            payg_output_rate=10.00,
            output_ratio=0.30,
            payg_blended_rate=4.75,
            payg_base=2052,
            payg_total=2052,
            throttle_rate=0.0,
            throttle_rate_pct=0.0,
            throttle_impact=0.0,
            include_throttle=False,
            baseline_ptu=20,
            ptu_monthly_rate=263.43,
            ptu_baseline_cost=5269,
            avg_spillover_tpm=500,
            spillover_cost=200,
            hybrid_total=5469,
            effective_mult=1.60,
            input_tpm_per_ptu=2500,
            model_output_multiplier=3,
            pricing_source=pricing_source,
        )

    def test_manual_source_adds_custom_rate_tag(self) -> None:
        from ptu_advisor.api.server import _build_formula_blocks

        blocks = _build_formula_blocks(**self._common_kwargs(pricing_source="manual"))
        assert "(custom rate)" in blocks["payg"]
        assert "(custom rate)" in blocks["hybrid"]

    def test_live_source_no_custom_rate_tag(self) -> None:
        from ptu_advisor.api.server import _build_formula_blocks

        blocks = _build_formula_blocks(**self._common_kwargs(pricing_source="live"))
        assert "(custom rate)" not in blocks["payg"]
        assert "(custom rate)" not in blocks["hybrid"]

    def test_empty_source_no_custom_rate_tag(self) -> None:
        from ptu_advisor.api.server import _build_formula_blocks

        blocks = _build_formula_blocks(**self._common_kwargs(pricing_source=""))
        assert "(custom rate)" not in blocks["payg"]
        assert "(custom rate)" not in blocks["hybrid"]
