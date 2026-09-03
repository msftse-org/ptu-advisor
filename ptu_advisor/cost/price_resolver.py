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
import re
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
MODEL_PRODUCT_NAMES: Dict[str, str] = {
    "o4-mini": "Azure OpenAI Reasoning",
}

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
    "gpt-4o-2024-11-20": ["gpt 4o 1120"],
    "gpt-4o-2024-08-06": ["gpt 4o 0806"],
    "gpt-4o-2024-05-13": ["gpt 4o 0513"],
    "gpt-5.5": ["5.5 ShortCo"],
    "gpt-5.4-mini": ["5.4 mini"],
    "gpt-5.4": ["5.4"],
    "gpt-5.3-codex": ["5.3 codex"],
    "gpt-5.2-codex": ["5.2 codex"],
    "gpt-5.2": ["GPT 5.2"],
    "gpt-5.1-codex": ["5.1 codex"],
    "gpt-5.1": ["GPT 5.1"],
    "gpt-5-mini": ["GPT 5 Mini"],
    "gpt-5": ["GPT 5 Inpt", "GPT 5 cchd", "GPT 5 outpt"],
    "gpt-4.1": ["gpt 4.1"],
    "gpt-4.1-mini": ["gpt 4.1 mini"],
    "gpt-4.1-nano": ["gpt 4.1 nano"],
    "gpt-4o": ["gpt 4o 1120", "gpt 4o 0806", "gpt 4o 0513"],
    "gpt-4o-mini": ["gpt-4o-mini-0718", "gpt 4o mini 0718"],
    "o1": ["o1 1217"],
    "o3-mini": ["o3 mini 0131", "o3-mini"],
    "o4-mini": ["o4-mini 0416", "o4-mini"],
}

# ---------------------------------------------------------------------------
# PTU meter patterns per deployment type
# ---------------------------------------------------------------------------
PTU_METER_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "global": ("Provisioned Managed Global", "Global Provisioned Managed"),
    "data_zone": ("Provisioned Managed Data Zone", "Data Zone Provisioned Managed"),
    "regional": ("Provisioned Managed Regional", "Regional Provisioned Managed"),
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

# Verified standard input, cached input, and output rates per 1M tokens.
# Source: Azure Retail Prices API, queried July 14, 2026 in East US. Global
# meters use Gl/glbl; Data Zone meters use Dz/DZone/Data Zone. Regional rates
# are included only where explicit regnl meters exist. Unknown combinations
# deliberately price cached input at the standard input rate.
STATIC_TOKEN_RATES: Dict[Tuple[str, str], Tuple[float, float, float]] = {
    ("gpt-4o-2024-11-20", "global"): (2.50, 1.25, 10.00),
    ("gpt-4o-2024-11-20", "data_zone"): (2.75, 1.375, 11.00),
    ("gpt-4o-2024-08-06", "global"): (2.50, 1.25, 10.00),
    ("gpt-4o-2024-08-06", "data_zone"): (2.75, 1.375, 11.00),
    ("gpt-4o-2024-05-13", "global"): (5.00, 5.00, 15.00),
    ("gpt-4o-2024-05-13", "data_zone"): (5.50, 5.50, 16.50),
    ("gpt-4o", "global"): (2.50, 1.25, 10.00),
    ("gpt-4o", "data_zone"): (2.75, 1.375, 11.00),
    ("gpt-4o-mini", "global"): (0.15, 0.075, 0.60),
    ("gpt-4o-mini", "data_zone"): (0.165, 0.0825, 0.66),
    ("gpt-4.1", "global"): (2.00, 0.50, 8.00),
    ("gpt-4.1", "data_zone"): (2.20, 0.55, 8.80),
    ("gpt-4.1-mini", "global"): (0.40, 0.10, 1.60),
    ("gpt-4.1-mini", "data_zone"): (0.44, 0.11, 1.76),
    ("gpt-4.1-nano", "global"): (0.10, 0.025, 0.40),
    ("gpt-4.1-nano", "data_zone"): (0.11, 0.0275, 0.44),
    ("gpt-5", "global"): (1.25, 0.125, 10.00),
    ("gpt-5", "data_zone"): (1.375, 0.1375, 11.00),
    ("gpt-5-mini", "global"): (0.25, 0.025, 2.00),
    ("gpt-5-mini", "data_zone"): (0.275, 0.0275, 2.20),
    ("gpt-5.1", "global"): (1.25, 0.125, 10.00),
    ("gpt-5.1", "data_zone"): (1.375, 0.1375, 11.00),
    ("gpt-5.1-codex", "global"): (1.25, 0.125, 10.00),
    ("gpt-5.1-codex", "data_zone"): (1.375, 0.1375, 11.00),
    ("gpt-5.2", "global"): (1.75, 0.175, 14.00),
    ("gpt-5.2", "data_zone"): (1.925, 0.1925, 15.40),
    ("gpt-5.2-codex", "global"): (1.75, 0.175, 14.00),
    ("gpt-5.2-codex", "data_zone"): (1.925, 0.1925, 15.40),
    ("gpt-5.3-codex", "global"): (1.75, 0.175, 14.00),
    ("gpt-5.3-codex", "data_zone"): (1.925, 0.1925, 15.40),
    ("gpt-5.4", "global"): (2.50, 0.25, 15.00),
    ("gpt-5.4", "data_zone"): (2.75, 0.275, 16.50),
    ("gpt-5.4-mini", "global"): (0.75, 0.075, 4.50),
    ("gpt-5.4-mini", "data_zone"): (0.825, 0.0825, 4.95),
    ("gpt-5.5", "global"): (5.00, 0.50, 30.00),
    ("gpt-5.5", "data_zone"): (5.50, 0.55, 33.00),
    ("o1", "global"): (15.00, 7.50, 60.00),
    ("o1", "data_zone"): (16.50, 8.25, 66.00),
    ("o3-mini", "global"): (1.10, 0.55, 4.40),
    ("o3-mini", "data_zone"): (1.21, 0.605, 4.84),
    ("o4-mini", "global"): (1.10, 0.275, 4.40),
    ("o4-mini", "data_zone"): (1.21, 0.303, 4.84),
}

STATIC_REGIONAL_TOKEN_RATES: Dict[Tuple[str, str], Tuple[float, float, float]] = {
    ("gpt-4o-2024-11-20", "eastus"): (2.75, 1.375, 11.00),
    ("gpt-4o-2024-08-06", "eastus"): (2.75, 1.375, 11.00),
    ("gpt-4o-2024-05-13", "eastus"): (5.50, 5.50, 16.50),
    ("gpt-4o", "eastus"): (2.75, 1.375, 11.00),
    ("gpt-4o-mini", "eastus"): (0.165, 0.0825, 0.66),
    ("gpt-4.1", "eastus"): (2.20, 0.55, 8.80),
    ("gpt-4.1-mini", "eastus"): (0.44, 0.11, 1.76),
    ("gpt-4.1-nano", "eastus"): (0.11, 0.0275, 0.44),
    ("o1", "eastus"): (16.50, 8.25, 66.00),
    ("o3-mini", "eastus"): (1.21, 0.605, 4.84),
    ("o4-mini", "eastus"): (1.21, 0.303, 4.84),
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
    payg_cached_input_rate: float = 0.0  # $ per 1M cached input tokens
    cached_input_source: Literal[
        "live", "cached", "fallback", "manual", "conservative"
    ] = "conservative"
    ptu_pricing_source: Literal["live", "cached", "fallback", "manual"] = "fallback"
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
        self._warmup_lock = threading.Lock()
        self._warmup_stop = threading.Event()
        self._warmup_thread: Optional[threading.Thread] = None

    # -- public API --------------------------------------------------------

    def resolve(
        self,
        model_name: str,
        region: str,
        deployment_type: str,
        *,
        payg_input_override: Optional[float] = None,
        payg_output_override: Optional[float] = None,
        payg_cached_input_override: Optional[float] = None,
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
        if dtype_key not in {"global", "data_zone", "regional"}:
            raise ValueError("deployment_type must be global, data_zone, or regional")

        # ------------------------------------------------------------------
        # Layer 1: Manual overrides
        # ------------------------------------------------------------------
        if any(
            v is not None
            for v in (
                payg_input_override,
                payg_output_override,
                payg_cached_input_override,
                ptu_hourly_override,
            )
        ):
            fallback = self._static_fallback(model_key, region_key, dtype_key, now)
            resolved_input = (
                payg_input_override
                if payg_input_override is not None
                else fallback.payg_input_rate
            )
            result = PricingResult(
                payg_input_rate=resolved_input,
                payg_output_rate=payg_output_override
                if payg_output_override is not None
                else fallback.payg_output_rate,
                payg_cached_input_rate=payg_cached_input_override
                if payg_cached_input_override is not None
                else resolved_input
                if payg_input_override is not None
                else fallback.payg_cached_input_rate,
                cached_input_source="manual"
                if payg_cached_input_override is not None
                else "conservative"
                if payg_input_override is not None
                else fallback.cached_input_source,
                ptu_hourly_rate=ptu_hourly_override
                if ptu_hourly_override is not None
                else fallback.ptu_hourly_rate,
                ptu_pricing_source="manual"
                if ptu_hourly_override is not None
                else fallback.ptu_pricing_source,
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
                    payg_cached_input_rate=result.payg_cached_input_rate,
                    cached_input_source=(
                        "cached" if result.cached_input_source == "live" else result.cached_input_source
                    ),
                    ptu_hourly_rate=result.ptu_hourly_rate,
                    ptu_pricing_source=(
                        "cached" if result.ptu_pricing_source == "live" else result.ptu_pricing_source
                    ),
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
                if live.source == "live":
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
        parenthesized = re.fullmatch(r"(.+?)\s*\((\d{4}-\d{2}-\d{2})\)", name)
        if parenthesized:
            base_name, version = parenthesized.groups()
            exact_version = f"{base_name.strip()}-{version}"
            if exact_version in MODEL_METER_PATTERNS:
                return exact_version
            if base_name.strip() in MODEL_METER_PATTERNS:
                return base_name.strip()
        # Try exact match first
        if name in MODEL_METER_PATTERNS:
            return name
        # Only strip a date suffix. Unknown sibling variants must remain unknown
        # so they receive conservative pricing instead of a cheaper base model.
        sorted_keys = sorted(MODEL_METER_PATTERNS.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if re.fullmatch(rf"{re.escape(key)}-\d{{4}}-\d{{2}}-\d{{2}}", name):
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
        payg_cached_input: Optional[float] = None
        payg_output: Optional[float] = None

        try:
            payg_input, payg_cached_input, payg_output = self._fetch_payg_rates(
                model_key, meter_patterns, region, deployment_type
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
        if (
            payg_input is not None
            or payg_cached_input is not None
            or payg_output is not None
            or ptu_hourly is not None
        ):
            fb = self._static_fallback(model_key, region, deployment_type, now)
            token_rates_complete = (
                payg_input is not None
                and payg_cached_input is not None
                and payg_output is not None
            )
            return PricingResult(
                payg_input_rate=payg_input if payg_input is not None else fb.payg_input_rate,
                payg_output_rate=payg_output if payg_output is not None else fb.payg_output_rate,
                payg_cached_input_rate=payg_cached_input
                if payg_cached_input is not None
                else payg_input
                if payg_input is not None
                else fb.payg_cached_input_rate,
                cached_input_source="live"
                if payg_cached_input is not None
                else "conservative"
                if payg_input is not None
                else fb.cached_input_source,
                ptu_hourly_rate=ptu_hourly if ptu_hourly is not None else fb.ptu_hourly_rate,
                ptu_pricing_source="live" if ptu_hourly is not None else fb.ptu_pricing_source,
                source="live" if token_rates_complete else "fallback",
                as_of=now,
                model_name=model_key,
                region=region,
                deployment_type=deployment_type,
            )

        return None

    def _fetch_payg_rates(
        self,
        model_key: str,
        meter_patterns: List[str],
        region: str,
        deployment_type: str,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Fetch PAYG input/output rates, trying each meter pattern in order."""
        # Map deployment type to the region qualifier used in meter names
        scope_tokens = {
            "global": ("glbl", " global", " gl "),
            "data_zone": ("data zone", "dzone", " dz "),
            "regional": ("regnl", "regional", " rgnl"),
        }.get(deployment_type, ("glbl", " global", " gl "))

        resolved_input: Optional[float] = None
        resolved_cached_input: Optional[float] = None
        resolved_output: Optional[float] = None

        for svc_name in API_SERVICE_NAMES:
            for pattern in meter_patterns:
                product_name = MODEL_PRODUCT_NAMES.get(
                    model_key,
                    "Azure OpenAI GPT5" if model_key.startswith("gpt-5") else "Azure OpenAI",
                )
                payg_filter = (
                    f"serviceName eq '{svc_name}' "
                    f"and productName eq '{product_name}' "
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

                for item in items:
                    meter = item.get("meterName", "")
                    sku_name = item.get("skuName", "")
                    unit_price = float(item.get("unitPrice", 0))
                    unit_of_measure = item.get("unitOfMeasure", "")
                    meter_lower = meter.lower()
                    sku_lower = sku_name.lower()
                    classifier_text = f" {meter_lower} {sku_lower} "

                    # Skip non-standard meters (batch, cached, fine-tuned,
                    # audio, realtime, transcribe, tts)
                    if any(
                        kw in meter_lower
                        for kw in (
                            "batch",
                            " pp ",
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
                    if not any(token in classifier_text for token in scope_tokens):
                        continue
                    if not self._meter_matches_model(classifier_text, pattern):
                        continue

                    rate_per_1m = self._normalize_rate(unit_price, unit_of_measure)

                    # Classify as input or output
                    is_cached = self._is_cached_input_meter(classifier_text)
                    if is_cached:
                        if resolved_cached_input is None:
                            resolved_cached_input = rate_per_1m
                    elif self._is_input_meter(classifier_text) and resolved_input is None:
                        resolved_input = rate_per_1m
                    elif self._is_output_meter(classifier_text) and resolved_output is None:
                        resolved_output = rate_per_1m

                if (
                    resolved_input is not None
                    and resolved_cached_input is not None
                    and resolved_output is not None
                ):
                    return resolved_input, resolved_cached_input, resolved_output

        return resolved_input, resolved_cached_input, resolved_output

    def _fetch_ptu_rate(self, region: str, deployment_type: str) -> Optional[float]:
        """Fetch PTU hourly rate for the given region and deployment type."""
        ptu_keywords = PTU_METER_KEYWORDS.get(
            deployment_type,
            ("Provisioned Managed Regional", "Regional Provisioned Managed"),
        )

        for svc_name in API_SERVICE_NAMES:
            for ptu_keyword in ptu_keywords:
                ptu_filter = (
                    f"serviceName eq '{svc_name}' "
                    f"and productName eq 'Azure OpenAI' "
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
                    product_name = item.get("productName", "")
                    unit_price = float(item.get("unitPrice", 0))
                    uom = item.get("unitOfMeasure", "")
                    meter_lower = meter.lower()

                    if product_name and product_name != "Azure OpenAI":
                        continue
                    if "provisioned" not in meter_lower or unit_price <= 0:
                        continue
                    if "month" in uom.lower() or unit_price > 10:
                        continue
                    if ptu_keyword.lower() in meter_lower:
                        return unit_price

        return None

    @staticmethod
    def _is_input_meter(meter_lower: str) -> bool:
        """Return True if the meter name indicates an input token meter."""
        return any(kw in meter_lower for kw in ("inp", "input", "inpt"))

    @staticmethod
    def _is_output_meter(meter_lower: str) -> bool:
        """Return True if the meter name indicates an output token meter."""
        return any(kw in meter_lower for kw in ("outp", "output", "outpt", " opt "))

    @staticmethod
    def _is_cached_input_meter(meter_lower: str) -> bool:
        """Return True for cached-input meter naming variants."""
        return (
            "cached" in meter_lower
            or "cchd" in meter_lower
            or " cched " in meter_lower
            or " cd inp" in meter_lower
        ) and PricingResolver._is_input_meter(meter_lower)

    @staticmethod
    def _meter_matches_model(classifier_text: str, primary_pattern: str) -> bool:
        """Reject sibling model variants returned by broad Retail API filters."""
        pattern = primary_pattern.lower()
        if pattern in classifier_text:
            if pattern == "gpt 4.1" and any(
                sibling in classifier_text for sibling in ("gpt 4.1 mini", "gpt 4.1 nano")
            ):
                return False
            if pattern == "5.4" and "5.4 mini" in classifier_text:
                return False
            if pattern == "5.4" and any(
                sibling in classifier_text for sibling in ("5.4 nano", "5.4 pro", "5.4 longco")
            ):
                return False
            if pattern == "5.1 codex" and any(
                sibling in classifier_text for sibling in ("codex mini", "codex max")
            ):
                return False
            if pattern == "gpt 5.2" and any(
                sibling in classifier_text for sibling in ("5.2 chat", "5.2 codex", "5.2 pro")
            ):
                return False
            if pattern == "gpt 5.1" and any(
                sibling in classifier_text for sibling in ("5.1 chat", "5.1 codex")
            ):
                return False
            return True
        return False

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
        scoped_rates = (
            STATIC_REGIONAL_TOKEN_RATES.get((model_key, region))
            if deployment_type == "regional"
            else STATIC_TOKEN_RATES.get((model_key, deployment_type))
        )
        if scoped_rates is not None:
            input_rate, cached_input_rate, output_rate = scoped_rates
        else:
            input_rate, output_rate = STATIC_PAYG_RATES.get(
                model_key, (DEFAULT_PAYG_INPUT, DEFAULT_PAYG_OUTPUT)
            )
            cached_input_rate = input_rate
        has_verified_cached_fallback = scoped_rates is not None and cached_input_rate < input_rate
        cached_input_source: Literal["fallback", "conservative"] = (
            "fallback" if has_verified_cached_fallback else "conservative"
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
            payg_cached_input_rate=cached_input_rate,
            cached_input_source=cached_input_source,
            ptu_hourly_rate=ptu_hourly,
            ptu_pricing_source="fallback",
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
            (live.payg_cached_input_rate, fallback.payg_cached_input_rate),
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
        interval = max(1, interval_seconds or WARMUP_INTERVAL_SECONDS)

        with self._warmup_lock:
            if self._warmup_thread is not None and self._warmup_thread.is_alive():
                return self._warmup_thread

            self._warmup_stop.clear()

            def _loop() -> None:
                while not self._warmup_stop.is_set():
                    try:
                        self.warm_cache()
                    except Exception:
                        logger.warning("Background cache warm-up cycle failed.", exc_info=True)
                    if self._warmup_stop.wait(interval):
                        break

            thread = threading.Thread(
                target=_loop,
                name="pricing-cache-warmup",
                daemon=True,
            )
            self._warmup_thread = thread
            thread.start()
        logger.info("pricing_background_warmup started interval_s=%d", interval)
        return thread

    def stop_background_warmup(self, timeout_seconds: float = 5.0) -> None:
        """Stop the owned warm-up worker and wait briefly for it to exit."""
        with self._warmup_lock:
            thread = self._warmup_thread
            if thread is None:
                return
            self._warmup_stop.set()

        if thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout_seconds))

        with self._warmup_lock:
            if self._warmup_thread is thread and not thread.is_alive():
                self._warmup_thread = None


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
