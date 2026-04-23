# PRD: Live Model Pricing Fetch

> **Version**: 1.1  
> **Date**: April 1, 2026  
> **Author**: PTU Advisor Team  
> **Status**: ✅ Phase 1 Complete (12/12 items done)  
> **Changelog**: v1.1 — corrected 6 drift items to match actual implementation (implementation is source of truth)

---

## 1. Executive Summary

### Problem Statement

PTU Advisor currently uses **hardcoded pricing constants** scattered across 4 files:

| File | Hardcoded Values |
|------|-----------------|
| `api/server.py` | `payg_input_rate = 2.50`, `payg_output_rate = 10.0` |
| `cost/pricing.py` | `base_hourly_rate = 1.00 / 1.10 / 2.00` per deployment type |
| `report/generator.py` | Model-specific PAYG rates dict (gpt-5: $10/$30, gpt-4o: $2.50/$10, etc.) |
| `dashboard/app.py` | `payg_input_rate = 2.50`, `ptu_hourly = 1.00` |

Azure OpenAI pricing changes with new model releases, regional adjustments, and promotional offers. When prices change (e.g., gpt-4o-mini launched at 60% lower rates than gpt-4o), PTU Advisor continues to use stale rates, producing **inaccurate cost comparisons** that erode user trust. Users have no visibility into which pricing version the tool is using, nor any way to override it.

### Proposed Solution

Implement a **pricing resolution pipeline** that, for every analysis run, resolves current model-specific rates through a layered strategy:

1. **Azure Retail Prices API** (primary) — live query against `https://prices.azure.com/api/retail/prices` filtered by service name (tries `"Foundry Models"` first, then `"Azure OpenAI Service"` for backwards compatibility — Azure rebranded in early 2026), model, and region
2. **Cached pricing layer** — TTL-based cache (24h) to avoid redundant API calls
3. **Static fallback** — current hardcoded rates as the last-resort default, ensuring the tool never breaks

The frontend will display the **pricing source** (live / cached / fallback) and **effective date** alongside cost figures, giving users full transparency.

### Success Criteria

| KPI | Target |
|-----|--------|
| Pricing accuracy vs Azure pricing calculator | ≥ 99% match (within 1% tolerance) for all supported models |
| Pricing resolution latency | < 500ms for cached hits, < 2s for live API calls |
| Fallback reliability | 100% — analysis never fails due to pricing fetch errors |
| Pricing source transparency | Every analysis response includes `pricing_source` and `pricing_as_of` fields |
| Model coverage | All 9 models in `MODEL_CAPACITY_CONFIGS` have live-resolvable rates |
| Cache hit rate (steady state) | > 90% of requests served from cache after warm-up |

---

## 2. User Experience & Functionality

### User Personas

| Persona | Pain Point | Need |
|---------|-----------|------|
| **FinOps Engineer** | Presents cost projections to CFO; stale rates undermine credibility | Confidence that cost figures match the rates on the Azure invoice |
| **Cloud Architect** | Evaluating a newly released model (e.g., gpt-4.1-nano) that isn't in the hardcoded list | Automatic pickup of new model pricing without waiting for a code update |
| **Solution Engineer** | Running demos for customers who cross-reference with Azure pricing page | Numbers must match what the customer sees on azure.microsoft.com/pricing |

### User Stories

#### US-1: Automatic Live Pricing Resolution

> As a **FinOps Engineer**, I want PTU Advisor to automatically fetch the current Azure OpenAI pricing for the model I'm analyzing, so that my cost projections are always accurate.

**Acceptance Criteria:**
- [x] On every analysis request, the backend resolves PAYG input/output rates and PTU hourly rates for the detected model + region + deployment type
- [x] Resolution follows the priority chain: live API → cache → static fallback
- [x] The resolved rates are used in all downstream calculations (PAYG cost, hybrid cost, break-even, spillover, cost curves, formula blocks)
- [x] No user action required — pricing resolution is transparent and automatic

#### US-2: Pricing Source Transparency

> As a **Cloud Architect**, I want to see where the pricing data came from and when it was last updated, so I can assess the reliability of the cost comparison.

**Acceptance Criteria:**
- [x] The API response `cost_analysis.pricing` section includes:
  - `pricing_source`: `"live"` | `"cached"` | `"fallback"`
  - `pricing_as_of`: ISO 8601 timestamp of when the pricing was fetched or last confirmed
  - `pricing_currency`: `"USD"` (default)
- [x] The frontend displays a subtle indicator next to cost figures showing pricing source (e.g., a badge: "Live pricing as of Mar 16, 2026")
- [x] If using fallback rates, a warning banner is shown: "Using default pricing — live pricing unavailable"

#### US-3: Pricing Override

> As a **Solution Engineer**, I want to manually override any rate (PAYG or PTU) so I can model custom pricing agreements or EAs.

**Acceptance Criteria:**
- [x] The `AnalyzeRequest` accepts optional fields: `payg_input_rate_override`, `payg_output_rate_override`, `ptu_hourly_rate_override`
- [x] When overrides are provided, they take highest priority (above live API)
- [x] `pricing_source` is set to `"manual"` when any override is active
- [x] Formula blocks reflect the overridden values with a "(custom)" annotation

#### US-4: New Model Support Without Code Changes

> As a **Platform Team Lead**, I want PTU Advisor to automatically support pricing for new Azure OpenAI models as they become available, without requiring a code deployment.

**Acceptance Criteria:**
- [x] The pricing resolution uses the Azure Retail Prices API `armSkuName` / `skuName` / `meterName` fields to match models dynamically
- [x] If a model is not in `MODEL_CAPACITY_CONFIGS` but exists in the Retail API, pricing is still resolved (capacity defaults apply)
- [x] A log entry is emitted when a model is resolved from live API but has no local capacity config

### Non-Goals

- **Currency conversion** — all pricing is USD. Multi-currency support is out of scope.
- **Commitment/reservation pricing from API** — reservation discounts (monthly, 1-year) remain local multipliers; the Retail API does not expose all commitment tiers.
- **Automatic PTU hourly rate from API** — the Azure Retail Prices API provides PTU rates inconsistently across meters. PTU hourly rate resolution is best-effort; the base rates in `pricing.py` remain authoritative with region multipliers applied on top.
- **Historical pricing** — we fetch current rates only, not pricing history.

---

## 3. Technical Specifications

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Analysis Request                          │
│  (model, region, deployment_type, rate overrides?)              │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│      PricingResolver            │
│  resolve(model, region, type)   │
│  → PricingResult                │
│                                 │
│  Priority chain:                │
│  1. Manual overrides            │
│  2. In-memory cache (TTL: 24h)  │
│  3. Azure Retail Prices API     │
│  4. Static fallback (current)   │
└──────┬──────────────────────────┘
       │
       ├──► Cache hit? → return cached PricingResult
       │
       ├──► Azure Retail Prices API
       │    GET https://prices.azure.com/api/retail/prices
│    ?$filter=serviceName eq '{svc_name}'
│           and armRegionName eq '{region}'
│           and contains(meterName, '{model}')
│    (tries "Foundry Models" first, then "Azure OpenAI Service")
       │    → parse PAYG input/output rates from meter names
       │    → cache result (TTL 24h)
       │    → return PricingResult(source="live")
       │
       └──► On error → return static fallback
            PricingResult(source="fallback")
```

### 3.2 New Module: `ptu_advisor/cost/price_resolver.py`

```python
@dataclass(frozen=True)
class PricingResult:
    """Resolved pricing for a model + region + deployment type."""
    payg_input_rate: float          # $ per 1M input tokens
    payg_output_rate: float         # $ per 1M output tokens
    ptu_hourly_rate: float          # $ per PTU-hour (after region multiplier)
    source: Literal["live", "cached", "fallback", "manual"]
    as_of: datetime                 # When pricing was fetched/confirmed
    currency: str = "USD"
    model_name: str = ""
    region: str = ""
    deployment_type: str = ""       # "global", "data_zone", or "regional"
```

### 3.3 Azure Retail Prices API Integration

**Endpoint**: `https://prices.azure.com/api/retail/prices` (public, no auth required)

**Query Strategy**:

| Filter | Purpose |
|--------|---------|
| `serviceName eq '{svc_name}'` | Scope to Azure OpenAI (tries `"Foundry Models"` first, then `"Azure OpenAI Service"` for backwards compatibility) |
| `armRegionName eq '{region}'` | Region-specific rates |
| `priceType eq 'Consumption'` | PAYG rates only |
| `contains(meterName, '{model_pattern}')` | Model-specific meters |

**Meter Name Parsing**:

Azure OpenAI meters follow patterns like:
- `GPT-4o Input Tokens` → PAYG input rate
- `GPT-4o Output Tokens` → PAYG output rate  
- `GPT-4o-mini Input Tokens` → model-specific PAYG input rate
- `Provisioned Managed Base Unit` → PTU hourly rate (global)

The resolver must:
1. Map `model_name` from deployment metadata (e.g., `"gpt-4o-2024-11-20"`) to API meter patterns (e.g., `"GPT-4o"`)
2. Parse `unitPrice` from matching meters
3. Normalize to per-1M-token rates (API returns per-1K or per-1 token depending on meter)

**Model-to-Meter Mapping**:

Each model maps to a *list* of candidate search patterns (tried in order). The first pattern that returns results from the API is used. This accounts for inconsistent Azure meter naming across models and versions.

```python
MODEL_METER_PATTERNS: Dict[str, List[str]] = {
    "gpt-5":        ["GPT 5 Chat", "GPT 5 Inpt"],
    "gpt-4.1":      ["gpt 4.1 Inp", "gpt-4.1 Inp"],
    "gpt-4.1-mini": ["gpt 4.1 mini Inp", "gpt-4.1-mini Inp"],
    "gpt-4.1-nano": ["gpt 4.1 nano Inp", "gpt-4.1-nano Inp"],
    "gpt-4o":       ["gpt 4o 1120", "gpt 4o 0806", "gpt 4o 0513"],
    "gpt-4o-mini":  ["gpt-4o-mini-0718"],
    "o1":           ["o1 1217"],
    "o3-mini":      ["o3 mini 0131", "o3-mini"],
    "o4-mini":      ["o4-mini 0416", "o4-mini"],
}
```

**Rate Extraction Logic**:

```
For each API result item:
  if "Input" in meterName and "Token" in meterName:
      payg_input_rate = unitPrice × unit_multiplier  (normalize to per-1M)
  elif "Output" in meterName and "Token" in meterName:
      payg_output_rate = unitPrice × unit_multiplier
  elif "Provisioned" in meterName:
      ptu_hourly_rate = unitPrice
```

### 3.4 Caching Strategy

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Cache key | `f"{model}:{region}:{deployment_type}"` | Unique per pricing context |
| TTL | 24 hours | Azure pricing changes infrequently (typically monthly) |
| Storage | In-memory dict | Simple, no external dependencies; cache warms per-process |
| Eviction | Lazy (check TTL on read) | No background threads |
| Cold start | First analysis per model/region hits the API | Subsequent requests are cached |

### 3.5 Static Fallback Strategy

When the Retail API is unreachable or returns unexpected data:

1. Log a warning: `"Live pricing fetch failed for {model}/{region}: {error}. Using fallback rates."`
2. Use current hardcoded rates as the default:
   - PAYG: Use `STATIC_PAYG_RATES` dict (migrate existing rates from `server.py` and `report/generator.py`)
   - PTU: Use `DEPLOYMENT_TYPE_CONFIGS[type].base_hourly_rate × region_multiplier` (current behavior)
3. Set `source="fallback"` so the frontend can display a warning

### 3.6 Integration Points

#### `_serialize_analysis()` in `api/server.py`

**Before** (current):
```python
payg_input_rate = 2.50        # hardcoded
payg_output_rate = 10.0       # hardcoded
...
ptu_hourly = deployment_cfg.base_hourly_rate * region_cfg.multiplier  # config-based
```

**After**:
```python
pricing = resolver.resolve(
    model_name=metrics.model_name,
    region=region,
    deployment_type=deployment_type,
    payg_input_override=payload.payg_input_rate_override,
    payg_output_override=payload.payg_output_rate_override,
    ptu_hourly_override=payload.ptu_hourly_rate_override,
)
payg_input_rate = pricing.payg_input_rate
payg_output_rate = pricing.payg_output_rate
ptu_hourly = pricing.ptu_hourly_rate
```

#### API Response Schema Changes

Add to `cost_analysis.pricing`:

```json
{
  "pricing": {
    "payg_input_rate_per_million": 2.50,
    "payg_output_rate_per_million": 10.00,
    "ptu_hourly_rate": 1.00,
    "pricing_source": "live",
    "pricing_as_of": "2026-03-16T08:30:00Z",
    "pricing_currency": "USD",
    ...existing fields...
  }
}
```

#### `AnalyzeRequest` Schema Changes

Add optional override fields:

```python
payg_input_rate_override: Optional[float] = Field(default=None, ge=0, description="Custom PAYG input rate ($ per 1M tokens)")
payg_output_rate_override: Optional[float] = Field(default=None, ge=0, description="Custom PAYG output rate ($ per 1M tokens)")
ptu_hourly_rate_override: Optional[float] = Field(default=None, ge=0, description="Custom PTU hourly rate")
```

#### Frontend Changes

- Display pricing source badge in the cost section header
- Show warning banner when `pricing_source === "fallback"`
- Add optional rate override inputs in an "Advanced" collapsible section (future phase)

---

## 4. Data Flow

```
User clicks "Run Analysis"
        │
        ▼
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐
│ AnalyzeRequest│────▶│ PricingResolver   │────▶│ Azure Retail API │
│ (model,region │     │ .resolve()        │◁───│ prices.azure.com │
│  overrides?)  │     │                   │     └──────────────────┘
└──────────────┘     │ Returns:          │
                     │ PricingResult     │
                     │ {rates, source,   │
                     │  as_of}           │
                     └────────┬──────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ _serialize_      │
                     │ analysis()       │
                     │ Uses resolved    │
                     │ rates for all    │
                     │ cost math        │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ AnalyzeResponse  │
                     │ cost_analysis:   │
                     │   pricing_source │
                     │   pricing_as_of  │
                     │   all cost figs  │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ Frontend         │
                     │ Shows pricing    │
                     │ source badge +   │
                     │ cost comparison  │
                     └──────────────────┘
```

---

## 5. Security & Privacy

| Concern | Mitigation |
|---------|-----------|
| API abuse / rate limiting | Azure Retail Prices API is public and unauthenticated; 24h cache minimizes call volume |
| SSRF risk | The resolver only calls the hardcoded `https://prices.azure.com` base URL; region/model parameters are used as OData `$filter` values, never as URL segments |
| Data sensitivity | Pricing data is public; no PII involved |
| Input validation | Override rates are validated (`ge=0`, reasonable upper bounds) to prevent injection of absurd values into calculations |

---

## 6. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| Azure Retail API schema changes | Meter parsing breaks → fallback to static | Low | Defensive parsing with fallback; structured logging for unmatched meters |
| API rate limiting or outages | Unable to fetch live pricing | Low | 24h cache + static fallback ensures zero downtime |
| Meter name format changes for new models | New model pricing not resolved | Medium | Fuzzy matching on model names; `MODEL_METER_PATTERNS` mapping is configurable |
| Unit price normalization errors | Incorrect rates (e.g., 1000× off) | Medium | Sanity checks: if resolved rate is >100× or <0.01× of fallback rate, log warning and use fallback |
| Network latency in restricted environments | Analysis response time increases | Medium | Cache hit path adds 0ms; only cold start has API latency. Timeout of 5s on API call. |

---

## 7. Phased Rollout

### Phase 1: Core Pricing Resolution (MVP)

**Scope**: Backend-only pricing resolver with cache + API + fallback

- [x] Create `ptu_advisor/cost/price_resolver.py` with `PricingResolver` class
- [x] Implement Azure Retail Prices API client with OData filter construction
- [x] Implement in-memory TTL cache
- [x] Implement static fallback with consolidated rate table
- [x] Integrate into `_serialize_analysis()` in `api/server.py` — replace hardcoded rates
- [x] Add `pricing_source`, `pricing_as_of`, `pricing_currency` to API response
- [x] Add `payg_input_rate_override`, `payg_output_rate_override`, `ptu_hourly_rate_override` to `AnalyzeRequest`
- [x] Add sanity check: reject rates that are >100× different from fallback
- [x] Update `report/generator.py` to use resolved rates instead of its own hardcoded dict
- [x] Update `dashboard/app.py` to use resolved rates instead of hardcoded constants
- [x] Unit tests: mock API responses, cache hit/miss, fallback paths (69 tests, 97% coverage)
- [x] Integration test: verify resolved rates match Azure pricing page for gpt-4o in eastus (11 tests, all passing)

### Phase 2: Transparency & Overrides

**Scope**: Frontend indicators + manual override support

- [x] Frontend: pricing source badge (live ✓ / cached ⏱ / fallback ⚠ / manual ✎)
- [x] Frontend: warning banner when `pricing_source === "fallback"`
- [x] Frontend: "Advanced Pricing" collapsible with rate override inputs
- [x] Formula blocks show "(custom rate)" annotation when overrides are active

### Phase 3: Monitoring & Expansion

**Scope**: Observability and broader coverage

- [x] Structured logging for pricing resolution events (source, latency, model)
- [x] `/api/pricing/rates` endpoint to expose resolved rates without running a full analysis
- [x] Periodic background cache warm-up for popular model/region combos
- [x] Documentation: pricing accuracy validation runbook

---

## 8. Testing Strategy

| Layer | What | Tool |
|-------|------|------|
| Unit | `PricingResolver.resolve()` with mocked API responses | `pytest` + `responses` or `httpx_mock` |
| Unit | Cache TTL expiry, eviction, key format | `pytest` with `freezegun` for time manipulation |
| Unit | Meter name parsing for all 9 models | `pytest` parametrize |
| Unit | Sanity check rejects absurd rates | `pytest` |
| Integration | End-to-end analysis with mock pricing API | `pytest` + `TestClient` |
| Manual | Compare resolved rates for gpt-4o/eastus against [Azure pricing page](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/) | Manual validation |

---

## 9. Appendix

### A. Azure Retail Prices API Reference

- **Docs**: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
- **Endpoint**: `https://prices.azure.com/api/retail/prices`
- **Auth**: None required (public API)
- **Rate limit**: 100 requests per 10 seconds (generous for our use case with caching)
- **Response format**: JSON with `Items[]` array of price records

### B. Example API Response (truncated)

```json
{
  "Items": [
    {
      "currencyCode": "USD",
      "unitPrice": 0.0000025,
      "armRegionName": "eastus",
      "meterName": "GPT-4o Input Tokens",
      "serviceName": "Azure OpenAI Service",
      "unitOfMeasure": "1 Token",
      "type": "Consumption",
      "effectiveStartDate": "2025-11-01T00:00:00Z"
    },
    {
      "currencyCode": "USD",
      "unitPrice": 0.00001,
      "armRegionName": "eastus",
      "meterName": "GPT-4o Output Tokens",
      "serviceName": "Azure OpenAI Service",
      "unitOfMeasure": "1 Token",
      "type": "Consumption",
      "effectiveStartDate": "2025-11-01T00:00:00Z"
    }
  ]
}
```

### C. Current Hardcoded Rates (static fallback — `STATIC_PAYG_RATES` in `price_resolver.py`)

| Model | Input ($/1M) | Output ($/1M) | Notes |
|-------|-------------|---------------|-------|
| gpt-5 | $1.25 | $10.00 | Corrected from earlier draft ($10/$30 was wrong by 8x/3x) |
| gpt-4.1 | $2.00 | $8.00 | |
| gpt-4.1-mini | $0.40 | $1.60 | |
| gpt-4.1-nano | $0.10 | $0.40 | |
| gpt-4o | $2.50 | $10.00 | |
| gpt-4o-mini | $0.15 | $0.60 | |
| gpt-3.5-turbo | $0.50 | $1.50 | Legacy model — included for completeness |
| o1 | $15.00 | $60.00 | |
| o3-mini | $1.10 | $4.40 | |
| o4-mini | $1.10 | $4.40 | |

> All 10 supported models now have local PAYG rates. The live pricing fetch provides an additional accuracy layer on top of these fallbacks.
