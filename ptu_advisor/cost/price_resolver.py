"""Live pricing resolution for Azure OpenAI models.

Resolves current model-specific rates through a layered strategy:
1. Manual overrides (highest priority)
2. In-memory cache (TTL-based, 24h default)
3. Azure Retail Prices API (public, no auth required)
4. Static fallback (hardcoded rates from pricing.py + generator.py)

Reference:
    https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional, Tuple

try:
    import httpx as _httpx  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _httpx = None  # type: ignore[assignment]

from ptu_advisor.cost.pricing import (
    DEPLOYMENT_TYPE_CONFIGS,
    DeploymentType,
    get_deployment_type,
    get_region_config,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Azure Retail Prices API constants
# ---------------------------------------------------------------------------
RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"
API_TIMEOUT_SECONDS = 5
# The Azure Retail Prices API rebranded from "Azure OpenAI Service" to
# "Foundry Models" in early 2026.  We try the new name first and fall back
# to the legacy name for backwards compatibility.
API_SERVICE_NAMES = ("Foundry Models", "Azure OpenAI Service")

# ---------------------------------------------------------------------------
# Model-to-meter mapping
# ---------------------------------------------------------------------------
# Maps internal model name prefixes to one or more substrings used in the
# Azure Retail Prices API ``contains(meterName, ...)`` OData filter.
#
# The API meter naming is inconsistent across models:
#   - "gpt 4o 1120 Inp glbl Tokens"  (space-separated, version suffix)
#   - "gpt-4o-mini-0718-Inp-glbl Tokens" (hyphen-separated, version suffix)
#   - "GPT 5 Inpt Glbl 1M Tokens" (title-case, no version suffix, 1M UoM)
#   - "o4-mini 0416 Inp glbl Tokens" (hyphen model, space version)
#
# Each entry is a *list* of candidate search patterns (tried in order).
# The first pattern that returns results is used.
MODEL_METER_PATTERNS: Dict[str, List[str]] = {
    "gpt-5": ["GPT 5 Chat", "GPT 5 Inpt"],
    "gpt-4.1": ["gpt 4.1 Inp", "gpt-4.1 Inp"],
    "gpt-4.1-mini": ["gpt 4.1 mini Inp", "gpt-4.1-mini Inp"],
    "gpt-4.1-nano": ["gpt 4.1 nano Inp", "gpt-4.1-nano Inp"],
    "gpt-4o": ["gpt 4o 1120", "gpt 4o 0806", "gpt 4o 0513"],
    "gpt-4o-mini": ["gpt-4o-mini-0718"],
    "o1": ["o1 1217"],
    "o3-mini": ["o3 mini 0131", "o3-mini"],
    "o4-mini": ["o4-mini 0416", "o4-mini"],
}

# ---------------------------------------------------------------------------
# PTU meter patterns per deployment type
# ---------------------------------------------------------------------------
PTU_METER_KEYWORDS: Dict[str, str] = {
    "global": "Global Provisioned Managed",
    "data_zone": "Data Zone Provisioned Managed",
    "regional": "Provisioned Managed",
}

# ---------------------------------------------------------------------------
# Static fallback rates  (last resort — current hardcoded values)
# ---------------------------------------------------------------------------
# Consolidated from server.py ($2.50/$10.00 for gpt-4o) and
# report/generator.py (per-model PAYG rates).
STATIC_PAYG_RATES: Dict[str, Tuple[float, float]] = {
    # (input_rate_per_1M_tokens, output_rate_per_1M_tokens)
    "gpt-5": (1.25, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}

# Static PTU hourly rates per deployment type (from pricing.py)
STATIC_PTU_HOURLY: Dict[str, float] = {
    "global": 1.00,
    "data_zone": 1.10,
    "regional": 2.00,
}

# Actual per-region PTU hourly rates from the Azure Retail Prices API
# (queried March 2026).  These replace the inaccurate multiplier model.
# Key: (deployment_type, region) -> hourly rate per PTU.
# Only Regional has per-region variation; Global and Data Zone are flat.
STATIC_REGIONAL_PTU_RATES: Dict[str, float] = {
    # Tier 1: $2.00/hr
    "eastus": 2.00,
    "eastus2": 2.00,
    "westus": 2.00,
    "westus2": 2.00,
    "westus3": 2.00,
    "centralus": 2.00,
    "northcentralus": 2.00,
    "southcentralus": 2.00,
    "australiaeast": 2.00,
    "southindia": 2.00,
    # Tier 2: $2.20/hr
    "canadacentral": 2.20,
    "canadaeast": 2.20,
    "northeurope": 2.20,
    "uksouth": 2.20,
    "ukwest": 2.20,
    "francecentral": 2.20,
    "germanywestcentral": 2.20,
    "norwayeast": 2.20,
    "switzerlandnorth": 2.20,
    "swedencentral": 2.20,
    "japaneast": 2.20,
    "japanwest": 2.20,
    "koreacentral": 2.20,
    "koreasouth": 2.20,
    "eastasia": 2.20,
    "uaenorth": 2.20,
    "qatarcentral": 2.20,
    "polandcentral": 2.20,
    "centralindia": 2.20,
    "southafricanorth": 2.20,
    # Tier 3: $2.40/hr
    "brazilsouth": 2.40,
    "southeastasia": 2.40,
    "westeurope": 2.40,
    "australiasoutheast": 2.40,
    "westindia": 2.40,
}

# Default fallback PAYG rate when model is unknown
DEFAULT_PAYG_INPUT = 2.50
DEFAULT_PAYG_OUTPUT = 10.00

# Sanity check bounds — if the resolved rate differs from the fallback by
# more than this factor, we reject it and use the fallback instead.
SANITY_RATIO_UPPER = 100.0
SANITY_RATIO_LOWER = 0.01

# Popular model/region combos for background cache warm-up.
# These are pre-warmed on startup and refreshed periodically to ensure
# the most common queries hit cache instead of the API.
POPULAR_WARMUP_COMBOS: List[Tuple[str, str, str]] = [
    # (model, region, deployment_type)
    ("gpt-4o", "eastus", "global"),
    ("gpt-4o", "eastus2", "global"),
    ("gpt-4o", "westus", "global"),
    ("gpt-4o-mini", "eastus", "global"),
    ("gpt-5", "eastus", "global"),
    ("gpt-4.1", "eastus", "global"),
    ("gpt-4.1-mini", "eastus", "global"),
    ("o4-mini", "eastus", "global"),
    ("gpt-4o", "swedencentral", "global"),
    ("gpt-4o", "northeurope", "global"),
]

# Background warm-up interval (seconds).  Re-warms cache every 12 hours.
WARMUP_INTERVAL_SECONDS = 12 * 3600


# ---------------------------------------------------------------------------
# PricingResult
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PricingResult:
    """Resolved pricing for a model + region + deployment type."""

    payg_input_rate: float  # $ per 1M input tokens
    payg_output_rate: float  # $ per 1M output tokens
    ptu_hourly_rate: float  # $ per PTU-hour (region- and type-specific)
    source: Literal["live", "cached", "fallback", "manual"]
    as_of: datetime
    currency: str = "USD"
    model_name: str = ""
    region: str = ""
    deployment_type: str = ""


# ---------------------------------------------------------------------------
# PricingResolver
# ---------------------------------------------------------------------------
class PricingResolver:
    """Resolves current Azure OpenAI pricing through a layered strategy.

    Resolution priority:
        1. Manual overrides (caller-provided)
        2. In-memory cache (TTL: ``cache_ttl_hours``, default 24h)
        3. Azure Retail Prices API (public, no auth)
        4. Static fallback (hardcoded rates)
    """

    def __init__(self, cache_ttl_hours: int = 24) -> None:
        self._cache: Dict[str, Tuple[PricingResult, datetime]] = {}
        self._ttl = timedelta(hours=cache_ttl_hours)

    # -- public API --------------------------------------------------------

    def resolve(
        self,
        model_name: str,
        region: str,
        deployment_type: str,
        *,
        payg_input_override: Optional[float] = None,
        payg_output_override: Optional[float] = None,
        ptu_hourly_override: Optional[float] = None,
    ) -> PricingResult:
        """Resolve pricing for the given model/region/deployment-type.

        Args:
            model_name: Model identifier (e.g. ``"gpt-4o-2024-11-20"``).
            region: Azure region slug (e.g. ``"eastus"``).
            deployment_type: One of ``"global"``, ``"data_zone"``, ``"regional"``.
            payg_input_override: Custom PAYG input rate ($/1M tokens).
            payg_output_override: Custom PAYG output rate ($/1M tokens).
            ptu_hourly_override: Custom PTU hourly rate.

        Returns:
            :class:`PricingResult` with resolved rates and source metadata.
        """
        t0 = time.monotonic()
        now = datetime.now(timezone.utc)
        model_key = self._normalize_model(model_name)
        region_key = (region or "eastus").strip().lower().replace(" ", "")
        dtype_key = (
            (deployment_type or "global").strip().lower().replace("-", "_").replace(" ", "_")
        )

        # ------------------------------------------------------------------
        # Layer 1: Manual overrides
        # ------------------------------------------------------------------
        if any(
            v is not None for v in (payg_input_override, payg_output_override, ptu_hourly_override)
        ):
            fallback = self._static_fallback(model_key, region_key, dtype_key, now)
            result = PricingResult(
                payg_input_rate=payg_input_override
                if payg_input_override is not None
                else fallback.payg_input_rate,
                payg_output_rate=payg_output_override
                if payg_output_override is not None
                else fallback.payg_output_rate,
                ptu_hourly_rate=ptu_hourly_override
                if ptu_hourly_override is not None
                else fallback.ptu_hourly_rate,
                source="manual",
                as_of=now,
                model_name=model_key,
                region=region_key,
                deployment_type=dtype_key,
            )
            self._log_resolution(result, time.monotonic() - t0)
            return result

        # ------------------------------------------------------------------
        # Layer 2: Cache
        # ------------------------------------------------------------------
        cache_key = f"{model_key}:{region_key}:{dtype_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            result, cached_at = cached
            if now - cached_at < self._ttl:
                cached_result = PricingResult(
                    payg_input_rate=result.payg_input_rate,
                    payg_output_rate=result.payg_output_rate,
                    ptu_hourly_rate=result.ptu_hourly_rate,
                    source="cached",
                    as_of=result.as_of,
                    currency=result.currency,
                    model_name=result.model_name,
                    region=result.region,
                    deployment_type=result.deployment_type,
                )
                self._log_resolution(cached_result, time.monotonic() - t0)
                return cached_result
            # TTL expired — evict
            del self._cache[cache_key]

        # ------------------------------------------------------------------
        # Layer 3: Azure Retail Prices API
        # ------------------------------------------------------------------
        live = self._fetch_live(model_key, region_key, dtype_key, now)
        if live is not None:
            # Sanity check against fallback
            fallback = self._static_fallback(model_key, region_key, dtype_key, now)
            if self._passes_sanity_check(live, fallback):
                self._cache[cache_key] = (live, now)
                self._log_resolution(live, time.monotonic() - t0)
                return live
            else:
                logger.warning(
                    "Live pricing for %s/%s/%s failed sanity check "
                    "(live input=%.4f vs fallback input=%.4f). Using fallback.",
                    model_key,
                    region_key,
                    dtype_key,
                    live.payg_input_rate,
                    fallback.payg_input_rate,
                )

        # ------------------------------------------------------------------
        # Layer 4: Static fallback
        # ------------------------------------------------------------------
        fallback_result = self._static_fallback(model_key, region_key, dtype_key, now)
        self._log_resolution(fallback_result, time.monotonic() - t0)
        return fallback_result

    def clear_cache(self) -> None:
        """Flush the in-memory pricing cache."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Number of entries currently in the cache."""
        return len(self._cache)

    # -- structured logging ------------------------------------------------

    @staticmethod
    def _log_resolution(result: PricingResult, latency_s: float) -> None:
        """Emit a structured log entry for a pricing resolution event."""
        logger.info(
            "pricing_resolved model=%s region=%s deployment_type=%s "
            "source=%s latency_ms=%.1f "
            "payg_input=%.4f payg_output=%.4f ptu_hourly=%.4f",
            result.model_name,
            result.region,
            result.deployment_type,
            result.source,
            latency_s * 1000,
            result.payg_input_rate,
            result.payg_output_rate,
            result.ptu_hourly_rate,
        )

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _normalize_model(raw: str) -> str:
        """Map a deployment model identifier to a canonical short name.

        Examples:
            ``"gpt-4o-2024-11-20"`` -> ``"gpt-4o"``
            ``"gpt-4.1-mini-2025-04-14"`` -> ``"gpt-4.1-mini"``
            ``"o4-mini-2025-04-16"`` -> ``"o4-mini"``
        """
        name = (raw or "").strip().lower()
        # Try exact match first
        if name in MODEL_METER_PATTERNS:
            return name
        # Try prefix match from longest to shortest (to prefer "gpt-4.1-mini" over "gpt-4.1")
        sorted_keys = sorted(MODEL_METER_PATTERNS.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if name.startswith(key):
                return key
        return name  # return as-is if unrecognized

    def _fetch_live(
        self,
        model_key: str,
        region: str,
        deployment_type: str,
        now: datetime,
    ) -> Optional[PricingResult]:
        """Attempt to fetch PAYG and PTU rates from the Azure Retail Prices API."""
        if _httpx is None:
            logger.debug("httpx not installed; skipping live pricing fetch.")
            return None

        meter_patterns = MODEL_METER_PATTERNS.get(model_key)
        if not meter_patterns:
            logger.debug("No meter pattern for model %s; skipping live fetch.", model_key)
            return None

        # -- Fetch PAYG rates --
        payg_input: Optional[float] = None
        payg_output: Optional[float] = None

        try:
            payg_input, payg_output = self._fetch_payg_rates(
                meter_patterns, region, deployment_type
            )
        except Exception:
            logger.warning(
                "Failed to fetch PAYG pricing from Azure Retail API for %s/%s",
                model_key,
                region,
                exc_info=True,
            )

        # -- Fetch PTU hourly rate --
        ptu_hourly: Optional[float] = None

        try:
            ptu_hourly = self._fetch_ptu_rate(region, deployment_type)
        except Exception:
            logger.warning(
                "Failed to fetch PTU pricing from Azure Retail API for %s/%s/%s",
                model_key,
                region,
                deployment_type,
                exc_info=True,
            )

        # If we got at least one rate, build a result (fill gaps from fallback)
        if payg_input is not None or payg_output is not None or ptu_hourly is not None:
            fb = self._static_fallback(model_key, region, deployment_type, now)
            return PricingResult(
                payg_input_rate=payg_input if payg_input is not None else fb.payg_input_rate,
                payg_output_rate=payg_output if payg_output is not None else fb.payg_output_rate,
                ptu_hourly_rate=ptu_hourly if ptu_hourly is not None else fb.ptu_hourly_rate,
                source="live",
                as_of=now,
                model_name=model_key,
                region=region,
                deployment_type=deployment_type,
            )

        return None

    def _fetch_payg_rates(
        self,
        meter_patterns: List[str],
        region: str,
        deployment_type: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Fetch PAYG input/output rates, trying each meter pattern in order."""
        # Map deployment type to the region qualifier used in meter names
        region_qualifier = {
            "global": "glbl",
            "data_zone": "Zone",
            "regional": "regnl",
        }.get(deployment_type, "glbl")

        for svc_name in API_SERVICE_NAMES:
            for pattern in meter_patterns:
                payg_filter = (
                    f"serviceName eq '{svc_name}' "
                    f"and armRegionName eq '{region}' "
                    f"and priceType eq 'Consumption' "
                    f"and contains(meterName, '{pattern}')"
                )
                resp = _httpx.get(
                    RETAIL_PRICES_URL,
                    params={"$filter": payg_filter},
                    timeout=API_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("Items", [])
                if not items:
                    continue

                payg_input: Optional[float] = None
                payg_output: Optional[float] = None

                for item in items:
                    meter = item.get("meterName", "")
                    unit_price = float(item.get("unitPrice", 0))
                    unit_of_measure = item.get("unitOfMeasure", "")
                    meter_lower = meter.lower()

                    # Skip non-standard meters (batch, cached, fine-tuned,
                    # audio, realtime, transcribe, tts)
                    if any(
                        kw in meter_lower
                        for kw in (
                            "batch",
                            "cchd",
                            "cached",
                            "ft ",
                            "-ft ",
                            "-ft-",
                            "dev-ft",
                            "dev ft",
                            "aud",
                            "rt-",
                            "rt ",
                            "rtime",
                            "tts",
                            "transcribe",
                            "img",
                        )
                    ):
                        continue

                    # Check deployment scope qualifier (glbl, regnl, Zone, etc.)
                    if region_qualifier.lower() not in meter_lower:
                        # Also accept "Glbl" / "global" as alternate spellings
                        alt_qualifiers = {
                            "glbl": ["global"],
                            "regnl": ["regional"],
                            "zone": ["dz", "data zone", "dzone"],
                        }
                        alts = alt_qualifiers.get(region_qualifier.lower(), [])
                        if not any(a in meter_lower for a in alts):
                            continue

                    rate_per_1m = self._normalize_rate(unit_price, unit_of_measure)

                    # Classify as input or output
                    if self._is_input_meter(meter_lower) and payg_input is None:
                        payg_input = rate_per_1m
                    elif self._is_output_meter(meter_lower) and payg_output is None:
                        payg_output = rate_per_1m

                if payg_input is not None or payg_output is not None:
                    return payg_input, payg_output

        return None, None

    def _fetch_ptu_rate(self, region: str, deployment_type: str) -> Optional[float]:
        """Fetch PTU hourly rate for the given region and deployment type."""
        ptu_keyword = PTU_METER_KEYWORDS.get(deployment_type, "Provisioned Managed")
        ptu_hourly: Optional[float] = None

        for svc_name in API_SERVICE_NAMES:
            ptu_filter = (
                f"serviceName eq '{svc_name}' "
                f"and armRegionName eq '{region}' "
                f"and contains(meterName, '{ptu_keyword}')"
            )
            resp = _httpx.get(
                RETAIL_PRICES_URL,
                params={"$filter": ptu_filter},
                timeout=API_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("Items", [])

            for item in items:
                meter = item.get("meterName", "")
                unit_price = float(item.get("unitPrice", 0))
                uom = item.get("unitOfMeasure", "")

                # PTU meters: "1/Hour" → per-PTU per-hour directly
                # Skip monthly commitment meters (large values like $286, $2916)
                if "Provisioned" not in meter or unit_price <= 0:
                    continue
                if "month" in uom.lower():
                    continue
                # Skip obviously wrong values (commitment tiers reported hourly
                # but with huge unit prices — they represent bulk commitments)
                if unit_price > 10:
                    continue

                if ptu_keyword.lower() in meter.lower():
                    ptu_hourly = unit_price
                    break
                elif ptu_hourly is None:
                    ptu_hourly = unit_price

            if ptu_hourly is not None:
                return ptu_hourly

        return None

    @staticmethod
    def _is_input_meter(meter_lower: str) -> bool:
        """Return True if the meter name indicates an input token meter."""
        return any(kw in meter_lower for kw in ("inp", "input", "inpt"))

    @staticmethod
    def _is_output_meter(meter_lower: str) -> bool:
        """Return True if the meter name indicates an output token meter."""
        return any(kw in meter_lower for kw in ("outp", "output", "outpt"))

    @staticmethod
    def _normalize_rate(unit_price: float, unit_of_measure: str) -> float:
        """Normalize an API unit price to a per-1M-token rate.

        The Azure Retail API returns prices in varying units:
        - "1 Token"  -> unit_price is per-token   -> multiply by 1,000,000
        - "1K Tokens" -> unit_price is per-1K      -> multiply by 1,000
        - "1M Tokens" -> already per-1M            -> use as-is

        Returns:
            Price per 1M tokens.
        """
        uom = (unit_of_measure or "").lower().strip()
        if "1m" in uom or "1,000,000" in uom:
            return unit_price
        if "1k" in uom or "1,000" in uom:
            return unit_price * 1_000
        # Default: assume per-token
        return unit_price * 1_000_000

    @staticmethod
    def _static_fallback(
        model_key: str,
        region: str,
        deployment_type: str,
        now: datetime,
    ) -> PricingResult:
        """Build a PricingResult from hardcoded static rates."""
        input_rate, output_rate = STATIC_PAYG_RATES.get(
            model_key, (DEFAULT_PAYG_INPUT, DEFAULT_PAYG_OUTPUT)
        )

        # PTU hourly: use the accurate per-region rates for Regional,
        # flat rates for Global/Data Zone
        dtype_key = (
            (deployment_type or "global").strip().lower().replace("-", "_").replace(" ", "_")
        )
        if dtype_key == "regional":
            ptu_hourly = STATIC_REGIONAL_PTU_RATES.get(region, 2.00)
        else:
            ptu_hourly = STATIC_PTU_HOURLY.get(dtype_key, 1.00)

        return PricingResult(
            payg_input_rate=input_rate,
            payg_output_rate=output_rate,
            ptu_hourly_rate=ptu_hourly,
            source="fallback",
            as_of=now,
            model_name=model_key,
            region=region,
            deployment_type=dtype_key,
        )

    @staticmethod
    def _passes_sanity_check(live: PricingResult, fallback: PricingResult) -> bool:
        """Return True if the live result is within reasonable bounds of the fallback."""
        for live_val, fallback_val in [
            (live.payg_input_rate, fallback.payg_input_rate),
            (live.payg_output_rate, fallback.payg_output_rate),
            (live.ptu_hourly_rate, fallback.ptu_hourly_rate),
        ]:
            if fallback_val <= 0:
                continue
            ratio = live_val / fallback_val
            if ratio > SANITY_RATIO_UPPER or ratio < SANITY_RATIO_LOWER:
                return False
        return True

    # -- background cache warm-up ------------------------------------------

    def warm_cache(
        self,
        combos: Optional[List[Tuple[str, str, str]]] = None,
    ) -> int:
        """Pre-warm the cache for popular model/region/deployment-type combos.

        Args:
            combos: List of ``(model, region, deployment_type)`` tuples.
                    Defaults to :data:`POPULAR_WARMUP_COMBOS`.

        Returns:
            Number of combos successfully warmed.
        """
        targets = combos or POPULAR_WARMUP_COMBOS
        warmed = 0
        for model, region, dtype in targets:
            try:
                result = self.resolve(model, region, dtype)
                if result.source in ("live", "cached"):
                    warmed += 1
            except Exception:
                logger.debug("Cache warm-up failed for %s/%s/%s", model, region, dtype)
        logger.info(
            "pricing_cache_warmup completed=%d/%d cache_size=%d",
            warmed,
            len(targets),
            self.cache_size,
        )
        return warmed

    def start_background_warmup(self, interval_seconds: Optional[int] = None) -> threading.Thread:
        """Start a daemon thread that periodically warms the cache.

        Args:
            interval_seconds: Seconds between warm-up cycles.
                              Defaults to :data:`WARMUP_INTERVAL_SECONDS`.

        Returns:
            The daemon thread (already started).
        """
        interval = interval_seconds or WARMUP_INTERVAL_SECONDS

        def _loop() -> None:
            while True:
                try:
                    self.warm_cache()
                except Exception:
                    logger.warning("Background cache warm-up cycle failed.", exc_info=True)
                time.sleep(interval)

        t = threading.Thread(target=_loop, name="pricing-cache-warmup", daemon=True)
        t.start()
        logger.info("pricing_background_warmup started interval_s=%d", interval)
        return t


# ---------------------------------------------------------------------------
# Module-level singleton for easy import
# ---------------------------------------------------------------------------
_default_resolver: Optional[PricingResolver] = None


def get_pricing_resolver() -> PricingResolver:
    """Return the module-level PricingResolver singleton."""
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = PricingResolver()
    return _default_resolver
