# PRD: Cache-Aware PTU Analysis, Visualization, and Reporting

> **Version:** 1.1
>
> **Date:** July 14, 2026
>
> **Author:** PTU Advisor Team
>
> **Status:** Engineering complete; production validation pending
>
> **Priority:** P1 - Recommendation and cost accuracy
>
> **Target release:** v1.3
>
> **Parent PRD:** [`docs/PRD.md`](../PRD.md)

---

## 1. Executive Summary

Before this feature, PTU Advisor collected Azure Monitor's **Prompt Token Cache Match Rate** (`AzureOpenAIContextTokensCacheMatchRate`) but used it only as an at-a-glance metric. It was not charted over time, did not affect PTU sizing or spillover calculations, was absent from paired economics, and was omitted from customer-facing and CLI reports. That gap could overstate required PTU capacity for workloads with reusable prompt prefixes.

The implemented feature adds an end-to-end **Prompt Cache Benefit** capability. PTU Advisor collects and normalizes cache metrics, visualizes cache match rate and estimated cached versus active prompt tokens, applies cache-aware formulas to PTU capacity and cost calculations, explains the impact in plain language, and includes the same evidence in exported reports. Where Azure Monitor does not provide trustworthy cache metrics, the application remains conservative by assuming no cache benefit unless the user explicitly supplies a what-if cache-rate override.

The core value proposition is a more accurate and defensible PTU recommendation: users can see that cached prompt tokens are deducted from provisioned utilization, understand the PTU capacity potentially avoided, and distinguish this capacity benefit from the fixed PTU commitment charge. The feature MVP is successful when cache-aware sizing matches documented Foundry sizing examples within one PTU increment, all adjusted values are traceable to observed or explicit assumptions, and the cache benefit appears consistently in the dashboard and both report paths.

### Important Billing and Capacity Clarification

The UI and reports must not use the unqualified statement **"cached tokens are free."** The accurate customer-facing explanation is:

> For provisioned deployments, cached prompt tokens are deducted from PTU utilization and can receive up to a 100% input-token discount. They do not reduce the fixed price of PTUs already deployed or reserved. For Standard/PAYG deployments, cached input tokens use the applicable discounted cached-input rate rather than automatically being free.

### MVP Goal

Deliver a cache-aware analysis path that uses reliable cache telemetry when available, clearly labels assumptions when it is not, and makes cache-driven capacity and cost effects visible in the dashboard, API response, and exported reports without changing the product's four-dimension recommendation model.

---

## 2. Mission

### Mission Statement

Make prompt caching a visible, measurable, and auditable part of every PTU decision so customers neither over-provision capacity nor mistake a utilization benefit for a reduction in fixed commitment cost.

### Core Principles

1. **Observed data before assumptions:** Prefer Azure Monitor metrics; use inferred or manual values only when clearly labeled.
2. **Conservative by default:** Missing cache data means zero modeled cache benefit, not an estimated industry average.
3. **Capacity and billing are separate:** Explain PTU utilization reduction, fixed PTU cost, PAYG cached-input pricing, and spillover independently.
4. **One calculation across every surface:** Dashboard, API, consolidation, demo mode, and reports must use the same cache-aware formulas.
5. **Full explainability:** Every cache-adjusted recommendation must show the source, coverage, formula, and difference from the no-cache baseline.

---

## 3. Target Users

| Persona | Technical comfort | Key needs | Current pain point |
|---|---|---|---|
| **Solution Engineer / CSA** | High Azure and architecture knowledge | Defensible PTU sizing and a customer-ready explanation | Cache benefit is visible only as one percentage and is absent from sizing and reports |
| **Cloud Architect** | High | Capacity planning grounded in request shape, output ratio, and cache rate | Raw TPM produces a conservative estimate that can overstate provisioned capacity |
| **FinOps Engineer** | Medium to high | Accurate PAYG versus PTU comparison with transparent assumptions | Cached input pricing and avoided PTU capacity are not separated |
| **Platform / AI Operations Lead** | High | Detect cache-rate changes, regressions, and workload differences over time | An average hides periods where prompt reuse succeeds or collapses |
| **Customer decision-maker** | Low to medium | Plain-language benefit, monthly impact, and next steps | Exported reports do not explain why prompt reuse affects the recommendation |

### User Needs

- Understand whether a workload is receiving a meaningful prompt-cache benefit.
- See cache behavior over the same analysis window as throughput and cost.
- Know whether the cache value is observed, inferred, manually overridden, or unavailable.
- Compare cache-aware PTU requirements against a no-cache baseline.
- Avoid treating cached input tokens as reducing the fixed cost of an existing PTU reservation.
- Receive actionable guidance when cache performance is low or unstable.

---

## 4. MVP Scope

> In this section, ✅ means included in feature scope. It does not indicate implementation is complete.

All in-scope items below are implemented as of July 14, 2026. The legend is retained to distinguish included and excluded product scope.

### 4.1 In Scope - Core Functionality

- ✅ Collect `AzureOpenAIContextTokensCacheMatchRate` at the selected Azure Monitor granularity.
- ✅ Collect `ActiveTokens` when exposed by the selected resource and deployment.
- ✅ Normalize all internal cache ratios to `0.0-1.0` at the collector boundary.
- ✅ Derive cached prompt tokens, active prompt tokens, and cache-adjusted normalized TPM.
- ✅ Add a **Prompt Cache Benefit** chart showing cache ratio and cached versus active prompt-token volume.
- ✅ Add observed, inferred, override, partial, and unavailable data-quality states.
- ✅ Apply cache-aware PTU sizing, hybrid spillover, break-even, commitment-safety, and PAYG calculations.
- ✅ Preserve a no-cache baseline so users can see the incremental cache benefit.
- ✅ Add a manual cache-rate what-if assumption for deployments where Azure Monitor does not expose the metric.
- ✅ Include cache evidence, chart, assumptions, and impact in customer-facing HTML/PDF export.
- ✅ Include cache evidence and chart in the CLI-generated Jinja2/Matplotlib report.
- ✅ Support demo and same-model consolidation workflows.

### 4.2 In Scope - Technical

- ✅ Add cache-aware domain fields to `DeploymentMetrics` and API response types.
- ✅ Extend `PricingResult` with a cached-input PAYG rate and source metadata.
- ✅ Use Azure Retail Prices API cached-input meters when available, with conservative fallback behavior.
- ✅ Add cache-specific formulas in reusable backend business logic rather than React.
- ✅ Add ECharts visualization using the existing theme, zoom, expand, and tooltip patterns.
- ✅ Add static SVG rendering for the client-side export report.
- ✅ Add Matplotlib rendering for the CLI report.
- ✅ Add backend, frontend, API, export, and Playwright coverage.
- ✅ Emit telemetry without prompt content, cache keys, or customer text.

### 4.3 In Scope - Integrations

- ✅ Azure Monitor metrics API for cache ratio, active tokens, prompt tokens, and completion tokens.
- ✅ Azure Retail Prices API for standard input, cached input, output, and PTU rates.
- ✅ Existing live Azure credential chain and read-only resource discovery.
- ✅ Existing token-snapshot JSON export, augmented with cache-impact metadata where appropriate.

### 4.4 In Scope - Deployment

- ✅ No database or schema migration.
- ✅ No additional service or container.
- ✅ Continue serving FastAPI and React from the current single Docker image.
- ✅ Preserve demo mode when Azure credentials or cache metrics are unavailable.

### 4.5 Out of Scope

- ❌ Reading, storing, or displaying prompt text, cache entries, `prompt_cache_key`, or response payload content.
- ❌ Application-level request instrumentation to ingest `usage.prompt_tokens_details.cached_tokens`.
- ❌ Automatically rewriting prompts to improve prefix reuse.
- ❌ Automatically configuring `prompt_cache_retention` or `prompt_cache_key` on customer applications.
- ❌ Guaranteeing invoice parity; all cost output remains an estimate based on current rates and observed metrics.
- ❌ Reducing the fixed PTU deployment or reservation charge based on cache hits.
- ❌ Assuming the source deployment's cache survives routing to a separate spillover deployment.
- ❌ Automatic PTU purchase, reservation purchase, deployment mutation, or traffic migration.
- ❌ Historical cached-token price reconstruction.
- ❌ Cross-model consolidation or comparison of incompatible cache semantics.

---

## 5. User Stories

### US-1: View Prompt Cache Performance

> As a **Platform Lead**, I want to see cache match rate over time, so that I can identify when repeated prompt prefixes are benefiting my workload.

**Example:** A deployment averages 62% cache match over 14 days but drops below 10% after a prompt-template release. The chart makes the regression visible instead of presenting only a period average.

**Acceptance Criteria:**

- The Evidence section contains a chart titled **Prompt Cache Benefit**.
- The chart uses the same time axis, zoom window, expansion behavior, and selected timestamp as other time-series charts.
- The tooltip shows cache match rate, total prompt tokens, estimated cached prompt tokens, and active prompt tokens for the interval.
- Missing intervals render as gaps and are not silently forward-filled.

### US-2: Receive Cache-Aware PTU Sizing

> As a **Cloud Architect**, I want cached prompt tokens excluded from provisioned utilization, so that the proposed PTU baseline reflects the capacity my workload actually consumes.

**Example:** At 1,000 RPM, 200 prompt tokens, 20 output tokens, and a 50% cache rate, the normalized input load is reduced before the model's output multiplier is applied. The recommended PTU count should reflect that reduction and be rounded to the deployment's minimum and scale increment.

**Acceptance Criteria:**

- The calculation uses active prompt tokens rather than total prompt tokens when cache data quality permits.
- Output tokens continue to use the configured model-specific output-to-input ratio.
- The result includes both no-cache and cache-aware PTU estimates.
- The UI shows the estimated PTUs avoided; it shows `0 PTU avoided` when minimum or increment rounding prevents a lower deployment size.

### US-3: Understand Cost Impact Without Misleading Claims

> As a **FinOps Engineer**, I want cached-input pricing and fixed PTU cost shown separately, so that I can explain the true financial impact.

**Example:** The report states that cache hits reduce modeled active load and PAYG input cost, while a 30-PTU monthly commitment remains the same fixed charge until the user selects a smaller valid PTU baseline.

**Acceptance Criteria:**

- PAYG cost separates uncached input, cached input, and output-token charges.
- PTU fixed cost is unchanged for a fixed selected PTU count.
- Hybrid spillover is calculated from active normalized load and conservatively prices spillover input as uncached unless target-deployment cache evidence exists.
- The UI never labels the entire workload, reservation, or PTU deployment as free.

### US-4: Use a Conservative Fallback

> As a **Solution Engineer**, I want missing cache metrics to produce a conservative recommendation, so that the tool never invents savings.

**Example:** A Standard deployment has prompt caching enabled, but the Azure Monitor cache-match metric is not exposed for that SKU. PTU Advisor uses 0% in the primary analysis and offers an optional what-if override rather than assuming a rate.

**Acceptance Criteria:**

- `unavailable` cache data produces zero cache adjustment.
- The dashboard states that the estimate is conservative.
- The result is not displayed as a measured 0% cache rate.
- A manual override is never enabled implicitly.

### US-5: Model a Cache What-If Scenario

> As a **Cloud Architect**, I want to enter an expected cache rate when telemetry is unavailable, so that I can compare conservative and optimized designs.

**Example:** The user enters a 40% cache-rate assumption after validating repeated prefixes in a load test. The graph renders a dashed assumption line, calculations update, and the report labels the source as **User assumption: 40%**.

**Acceptance Criteria:**

- Advanced assumptions offer `Auto`, `No cache benefit`, and `Manual override` modes.
- Manual rate accepts `0-100%` and rejects values outside that range.
- Override values are included in formula blocks, telemetry, and reports.
- The no-cache baseline remains visible for comparison.

### US-6: Export Cache Evidence

> As a **Solution Engineer**, I want the exported report to include the cache graph and impact summary, so that the customer sees the same evidence used by the recommendation.

**Example:** An HTML report includes a compact cache chart, 58% observed average match rate, 8.4 billion estimated cached prompt tokens per month, and 10 PTUs avoided after rounding.

**Acceptance Criteria:**

- Client-side HTML/PDF export contains a compact static cache chart.
- CLI report contains a Matplotlib cache chart.
- Both reports identify data source, coverage, time window, and whether the value is observed or assumed.
- Both reports contain the fixed-cost clarification.

### US-7: Consolidate Cache-Aware Workloads

> As a **Platform Lead**, I want cache effects consolidated across same-model deployments, so that shared PTU analysis reflects each deployment's active load.

**Example:** Three GPT-4.1 deployments have 20%, 55%, and unavailable cache rates. Their active token series are computed independently before being summed; the unavailable deployment receives no modeled cache benefit.

**Acceptance Criteria:**

- Cache-aware normalized load is computed per deployment before aggregation.
- The combined cache rate is prompt-token-weighted, not a simple average of percentages.
- Per-deployment chart attribution remains available.
- Missing cache data in one deployment does not erase valid data from other deployments and is disclosed in consolidation warnings.

### US-8: Diagnose Cache Optimization Opportunities

> As an **AI Operations Lead**, I want actionable interpretation of low or unstable cache rates, so that I can improve workload efficiency before committing to PTU.

**Example:** The tool suggests moving stable system instructions and tool definitions to the beginning of the prompt when the match rate is consistently low, without exposing or inspecting prompt content.

**Acceptance Criteria:**

- Guidance is rule-based and grounded in aggregate metrics.
- Guidance can mention common-prefix structure, workload separation, and retention behavior.
- The product does not claim that a specific prompt change will achieve a guaranteed cache rate.

---

## 6. Core Architecture & Patterns

### 6.1 Architecture Approach

The feature extends the current stateless, layered architecture. Cache data remains an in-memory part of each analysis request and is never persisted.

```text
Azure Monitor or Demo Data
    |
    |-- ProcessedPromptTokens
    |-- GeneratedTokens
    |-- AzureOpenAIContextTokensCacheMatchRate
    `-- ActiveTokens
    v
MetricsCollector
    |-- normalize Azure Percent -> internal ratio (0.0-1.0)
    |-- align cache and token timestamps without forward-fill
    `-- classify source and coverage
    v
DeploymentMetrics
    v
Cache Impact Calculator
    |-- cached / active prompt tokens
    |-- cache-adjusted normalized TPM
    |-- no-cache baseline
    `-- data-quality metadata
    v
DecisionEngine + Cost Calculator + PricingResolver
    |-- four dimensions remain intact
    |-- cache-adjusted capacity and cost inputs
    |-- PAYG cached-input rate
    `-- hybrid spillover calculation
    v
FastAPI AnalyzeResponse
    |-- dashboard cards and ECharts graph
    |-- client-side HTML/PDF report
    `-- CLI Matplotlib/Jinja2 report
```

### 6.2 Proposed Directory Changes

```text
ptu_advisor/
├── metrics/
│   ├── models.py                 # ActiveTokens and cache metadata
│   ├── collector.py              # Fetch and normalize cache metrics
│   └── merge.py                  # Prompt-token-weighted consolidation
├── cost/
│   ├── cache.py                  # New cache-impact formulas and quality policy
│   ├── calculator.py             # Cache-aware PTU/spillover integration
│   └── price_resolver.py         # Cached-input PAYG rate
├── api/server.py                 # Request options and response serialization
├── demo.py                       # Deterministic cache scenarios
├── visualization/charts.py       # CLI cache chart
└── report/templates/report.html  # CLI report section

frontend/src/
├── charts/PromptCacheChart.tsx   # New ECharts component
├── charts/echarts-setup.ts       # Register required series/components
├── charts/index.ts               # Export PromptCacheChart
├── App.tsx                       # Card, assumptions, graph, explanations
├── types.ts                      # Additive API contract types
├── ExportReport.tsx              # Static SVG cache chart and evidence
└── export-report.css             # Print layout
```

### 6.3 Design Patterns

- **Collector-boundary normalization:** Azure Monitor reports this metric as Percent; live values are converted to a `0.0-1.0` ratio before entering domain models. Demo values already use the domain representation.
- **Observed-over-derived precedence:** Observed cache match is preferred; `ActiveTokens` can infer missing cache volume; manual override applies only when explicitly selected.
- **Paired scenarios:** Every cache-aware output is accompanied by a no-cache baseline.
- **Conservative null handling:** Missing intervals receive no modeled cache benefit for calculations and remain gaps in charts.
- **Additive API evolution:** Existing response fields remain valid; cache fields are added without removing current contracts.
- **Shared calculation service:** React displays backend calculations and does not duplicate cache capacity formulas.
- **No persistence:** No database, ORM, Drizzle schema, or migration is introduced.

### 6.4 Cache Data Precedence

| Priority | Source | Classification | Use |
|---|---|---|---|
| 1 | Explicit manual override | `override` | Constant what-if rate for all intervals; clearly labeled |
| 2 | Cache match metric | `observed` | Primary chart and calculation source |
| 3 | `ActiveTokens` plus prompt/output tokens | `inferred` | Derive cached prompt volume and ratio when direct rate is absent |
| 4 | No reliable data | `unavailable` | Use 0% benefit in calculations |

Selecting **No cache benefit** sets classification to `disabled` and intentionally uses 0%, even if observed data exists.

### 6.5 Data Quality Policy

| Valid interval coverage | Classification | Calculation behavior | UI behavior |
|---|---|---|---|
| `>= 80%` | Good | Apply cache adjustment; missing intervals use 0% | Normal benefit presentation |
| `50-79.99%` | Partial | Apply observed intervals; missing intervals use 0% | Amber partial-data warning |
| `< 50%` | Limited | Do not change primary sizing or recommendation | Show contextual graph only; offer override |
| No data | Unavailable | 0% cache benefit | Empty state, not a measured zero |

---

## 7. Tools and Features

### 7.1 Metric Acquisition and Normalization

#### Required Metrics

| Display name | REST API name | Aggregation | Purpose |
|---|---|---|---|
| Processed Prompt Tokens | `ProcessedPromptTokens` | Total | Total input token volume |
| Generated Completion Tokens | `GeneratedTokens` | Total | Output volume and weighted capacity |
| Prompt Token Cache Match Rate | `AzureOpenAIContextTokensCacheMatchRate` | Average | Fraction of prompt tokens served from cache |
| Active Tokens | `ActiveTokens` | Total | Validation/fallback for total minus cached tokens |

#### Normalization Rules

```python
# Azure Monitor's cache metric unit is Percent (0-100).
live_cache_ratio = clamp(azure_percent / 100.0, 0.0, 1.0)

# Domain and demo representation is always a ratio (0.0-1.0).
api_cache_percent = cache_ratio * 100.0

# ActiveTokens is total inference tokens minus cached prompt tokens.
inferred_cached_prompt = clamp(
    prompt_tokens + completion_tokens - active_tokens,
    0.0,
    prompt_tokens,
)
inferred_cache_ratio = (
    inferred_cached_prompt / prompt_tokens if prompt_tokens > 0 else 0.0
)
```

- Live data must be divided by 100 at collection time, not guessed from magnitude.
- Demo data must not be divided again.
- Values outside documented bounds are rejected and recorded as invalid diagnostics.
- Cache timestamps are joined to prompt-token timestamps; missing values remain null for charting.
- `ActiveTokens` inference is accepted only when prompt, completion, and active token series align for the interval; otherwise the interval remains unavailable.

### 7.2 Cache Impact Calculation

For interval `i`:

```text
P_i = prompt tokens per minute
O_i = output tokens per minute
r_i = cache match ratio, 0.0-1.0
w   = model output-to-input utilization ratio

cached_prompt_i = P_i * r_i
active_prompt_i = P_i * (1 - r_i)

raw_normalized_tpm_i   = P_i + (O_i * w)
cache_normalized_tpm_i = active_prompt_i + (O_i * w)

utilization_avoided_i = raw_normalized_tpm_i - cache_normalized_tpm_i
                      = cached_prompt_i
```

The model output multiplier remains unchanged. Cache benefit applies to prompt/input tokens, not generated output tokens.

#### PTU Sizing

```text
required_ptu_raw = selected_percentile(cache_normalized_tpm) / input_tpm_per_ptu
required_ptu     = round_up_to_deployment_increment(
                     max(required_ptu_raw, deployment_minimum)
                   )

no_cache_ptu     = same calculation using raw_normalized_tpm
ptu_avoided      = max(0, no_cache_ptu - required_ptu)
```

PTU counts must always respect model, deployment-type minimums, and increments. A high cache rate can improve headroom without changing the rounded PTU count.

#### PAYG Cost

```text
uncached_input_cost = sum(active_prompt) / 1M * standard_input_rate
cached_input_cost   = sum(cached_prompt) / 1M * cached_input_rate
output_cost         = sum(output_tokens) / 1M * output_rate

cache_aware_payg = uncached_input_cost + cached_input_cost + output_cost
no_cache_payg    = sum(prompt_tokens) / 1M * standard_input_rate + output_cost
payg_cache_savings = no_cache_payg - cache_aware_payg
```

If no verified cached-input price is available, `cached_input_rate` falls back to the standard input rate. This produces zero monetary cache savings rather than overstating benefit.

#### PTU and Hybrid Cost

- Fixed PTU cost remains `selected_ptu * hourly_rate * hours * term_factor`.
- Cache can lower the PTU units required when the user accepts the cache-aware recommended baseline.
- For a fixed selected PTU count, cache improves capacity headroom but does not lower fixed cost.
- Spillover is based on active normalized load above selected PTU capacity.
- Spillover input is priced conservatively as uncached input in MVP because a separate Standard spillover deployment can have different cache locality.

Approximate interval spillover:

```text
A_i = active_prompt_i + (O_i * w)
K   = selected_ptu * input_tpm_per_ptu
f_i = max(0, A_i - K) / A_i, or 0 when A_i = 0

spillover_input_i  = active_prompt_i * f_i
spillover_output_i = O_i * f_i
```

The UI must label this as a workload-shape estimate and recommend a benchmark before purchase.

### 7.3 Prompt Cache Benefit Chart

#### Visual Specification

- **Title:** Prompt Cache Benefit
- **Chart type:** ECharts stacked area/bar plus line on a secondary axis.
- **Left axis:** Prompt tokens per interval.
- **Right axis:** Cache match rate, fixed `0-100%`.
- **Series:** Active Prompt Tokens, Cached Prompt Tokens, Cache Match Rate.
- **Observed rate:** Solid line.
- **Inferred rate:** Dotted line.
- **Manual override:** Dashed line with `Assumed` badge.
- **Average reference:** Horizontal line labeled `Avg cache match: X%`.
- **Zoom:** Existing linked `dataZoom` and `time-sync` group.
- **Accessibility:** Text summary and table values remain available without interpreting color.

#### Tooltip Example

```text
Jul 12 14:30
Cache match rate       58.4%
Prompt tokens         124,200
Cached prompt tokens   72,533
Active prompt tokens   51,667
Source               Observed
```

#### Summary Cards

The existing Prompt Cache Hit Rate card is expanded to show:

- Average cache match rate.
- P95 cache match rate.
- Valid interval coverage.
- Estimated monthly cached prompt tokens.
- Cache-aware normalized TPM reduction.
- Estimated PTUs avoided after rounding.
- Source badge: Observed, Inferred, Assumed, Disabled, or Unavailable.

### 7.4 Recommendation Integration

Prompt caching does not become a fifth decision dimension. It modifies the evidence supplied to the existing framework:

| Existing area | Cache-aware behavior |
|---|---|
| Workload Shape | Report cache stability and whether repeatable prefixes improve effective load stability |
| Capacity Pressure | Use cache-adjusted normalized load for modeled PTU pressure; observed 429 and utilization metrics remain authoritative |
| Latency Sensitivity | Explain that higher cache hits can reduce time to response, but do not claim causality without paired evidence |
| Load Predictability | Include cache-rate stability as supporting evidence, not an independent positive score |
| Cost recommendation | Use cache-aware PAYG, PTU baseline, spillover, break-even, and commitment-safety values |

When cache adjustment changes the economic recommendation, the response must say so explicitly:

```text
With no cache benefit, PAYG is estimated to be cheaper by $1,200/month.
Using the observed 61% prompt-cache match rate, a 20-PTU hybrid baseline is
estimated to be cheaper by $850/month. Cache coverage was 94% of intervals.
```

### 7.5 Pricing Resolution

`PricingResult` gains:

```python
cached_input_rate: float
cached_input_source: Literal["live", "cached", "fallback", "manual", "conservative"]
```

Resolution order:

1. Manual cached-input price override, if provided.
2. In-memory pricing cache.
3. Azure Retail Prices API cached-input meter.
4. Verified static cached-input rate for the canonical model and deployment type.
5. Standard input rate as a conservative fallback.

The pricing source shown to the user must cover standard input, cached input, output, and PTU rates.

#### Implemented Pricing Verification

As of July 14, 2026, the resolver is verified against the public Azure Retail Prices API using `productName`, `skuName`, region, model, and deployment-scope qualifiers. It recognizes cached-input naming variants including `cached Inp`, `cchd Inpt`, and `cd inp`; excludes Batch, Priority Processing, fine-tuned, audio, and sibling model meters; and combines rates across multiple naming patterns only when they belong to the exact requested model and scope.

The static fallback is keyed by model and deployment type for verified Global and Data Zone meters. Regional Standard fallback is region-specific only where an exact meter was verified; otherwise cached input is conservatively priced at the resolved standard-input rate. Representative verified Global rates include GPT-4o `$2.50/$1.25/$10.00`, GPT-4.1 `$2.00/$0.50/$8.00`, GPT-5 `$1.25/$0.125/$10.00`, GPT-5.2 `$1.75/$0.175/$14.00`, GPT-5.4-mini `$0.75/$0.075/$4.50`, o1 `$15.00/$7.50/$60.00`, o3-mini `$1.10/$0.55/$4.40`, and o4-mini `$1.10/$0.275/$4.40` for standard input, cached input, and output respectively.

### 7.6 Demo Mode

Demo generation must include deterministic cache profiles instead of deriving every scenario only from TPM scale:

| Scenario type | Expected average | Pattern |
|---|---:|---|
| Stable production / PTU recommended | `55-75%` | Stable business-hour reuse |
| Low-volume or highly varied prompts | `5-20%` | Sparse, volatile matches |
| Borderline | `25-45%` | Moderate periodic reuse |
| Cache regression | Starts `60%`, falls below `15%` | Validates chart and guidance |
| Consolidation | Different rate per sibling | Validates weighted aggregation |

Random generation must use a fixed seed in tests.

### 7.7 Consolidation

For deployment `d` and interval `i`, calculate active load before merging. Combined cache rate is prompt-token weighted:

```text
combined_cache_rate_i = sum(cached_prompt_d_i) / sum(prompt_tokens_d_i)
```

It must not be calculated as `mean(deployment_cache_rates)`. Deployments with unavailable cache data use 0% for modeled benefit and contribute a warning.

### 7.8 Report Requirements

#### Customer-Facing Export (`frontend/src/ExportReport.tsx`)

Add a **Prompt Cache Benefit** subsection containing:

- Compact static SVG chart with active/cached prompt volume and cache-rate line.
- Average rate, coverage, source, cached prompt volume, active-load reduction, and PTUs avoided.
- Cache-aware versus no-cache monthly comparison.
- Statement that fixed PTU charges do not fall unless the selected PTU count is reduced.
- Data-quality warning when partial, limited, overridden, or unavailable.

The complete report must remain within two printed pages for standard single-deployment analysis. If necessary, combine cache evidence with the existing Key Evidence section rather than adding a full page.

#### CLI Report (`report/generator.py` and Jinja2 template)

- Add a Matplotlib cache chart to `ChartGenerator`.
- Add cache metrics to the report context.
- Add the same source and fixed-cost wording used by the frontend export.
- Preserve report generation when cache data is absent.

#### Token Snapshot Export

The existing `/api/export/token-snapshot` output already includes cache-match data. Add `_meta.cache_analysis` with source, coverage, effective rate, active prompt total, cached prompt total, and whether an override was used. Do not remove the Azure CLI-compatible metric array.

### 7.9 Guidance Rules

| Condition | Guidance |
|---|---|
| High and stable cache rate | Preserve shared prompt prefixes and validate PTU sizing with a representative benchmark |
| Low cache rate with large prompts | Place stable instructions, examples, tools, and schemas before variable content where application design permits |
| Sudden cache-rate drop | Review recent prompt-template, tool-definition, model-version, deployment, and workload-mixing changes |
| High workload diversity | Consider separating materially different workloads to reduce cache competition and improve latency isolation |
| Metric unavailable | Use a load test or request-level usage logs to establish a defensible manual assumption; primary result remains conservative |

---

## 8. Technology Stack

### Backend

| Technology | Current version/constraint | Feature use |
|---|---|---|
| Python | `>=3.9`; Docker runtime 3.11 | Metrics and calculation logic |
| FastAPI | `>=0.116.0` | Additive request/response contract |
| Pydantic | `>=2.5.0` | Cache assumption validation |
| NumPy | `>=1.26.0` | Time-series derivation and percentiles |
| Pandas | `>=2.1.0` | Existing cost-curve processing; optional daily grouping |
| Azure Monitor SDK | `azure-mgmt-monitor>=6.0.0` | Cache and active-token metrics |
| httpx | `>=0.27.0` | Azure Retail Prices API |
| Matplotlib | `>=3.8.0` | CLI cache chart |
| Jinja2 | `>=3.1.0` | CLI HTML report |

### Frontend

| Technology | Current version | Feature use |
|---|---|---|
| React | `19.2.x` | Assumptions, cards, report integration |
| TypeScript | `5.9.x`, strict | Additive cache contract types |
| Vite | `7.x` | Build and development |
| ECharts | `6.x` | Prompt Cache Benefit chart |
| echarts-for-react | `3.x` | React chart wrapper |

### Testing and Tooling

- pytest and FastAPI `TestClient` for backend formulas and API contracts.
- Vitest and React Testing Library for component and export behavior.
- Playwright for visual and interaction validation.
- Ruff, MyPy, ESLint, and TypeScript strict checking as quality gates.

### Third-Party Integrations

- Azure Monitor Metrics API.
- Azure Retail Prices API.
- Optional Azure OpenAI/OpenAI provider remains unrelated to deterministic cache math.

No new runtime dependency, database, queue, or hosted service is required.

---

## 9. Security and Configuration

### 9.1 Authentication and Authorization

- Continue using the existing Azure credential chain (`DefaultAzureCredential`, Azure CLI, managed identity, or service principal).
- Live analysis remains read-only.
- The identity requires permissions sufficient to read the Cognitive Services resource and Azure Monitor metrics.
- The Azure Retail Prices API remains public and unauthenticated.

### 9.2 Data Privacy

- Collect aggregate token counts and percentages only.
- Do not collect prompt text, completion text, system instructions, tool definitions, prompt cache keys, or cached content.
- Do not emit subscription IDs, deployment names, tenant IDs, or raw metric arrays in product telemetry unless existing privacy controls explicitly permit them.
- Reports may contain deployment metadata already present in current exports but must not contain credentials or auth context.

### 9.3 Configuration

No new environment variable is required for MVP. Request-level options control the calculation:

```text
cache_mode = auto | disabled | override
cache_match_rate_override_pct = 0-100, required only for override
cached_input_rate_override = optional USD per 1M cached input tokens
```

Optional future organization-level defaults may be introduced only after user research.

### 9.4 Deployment Considerations

- No infrastructure change is required.
- Pricing and discovery caches remain process-local and unrelated to model prompt caching.
- Startup must not fail if the cached-input price or cache metrics cannot be resolved.
- Static frontend serving and single-port Docker behavior remain unchanged.

### 9.5 Security Scope

**In scope:** input validation, read-only access, aggregate telemetry, report redaction, fixed outbound pricing endpoint.

**Out of scope:** application prompt security, cache-content lifecycle management, customer retention-policy configuration, and cross-subscription cache behavior.

---

## 10. API Specification

### 10.1 Existing Endpoints Affected

| Method | Endpoint | Change |
|---|---|---|
| `POST` | `/api/analyze` | Accept cache mode/overrides; return cache chart and impact |
| `POST` | `/api/analyze-consolidation` | Apply per-deployment cache-aware merge |
| `GET` | `/api/pricing/rates` | Return cached-input rate and source |
| `POST` | `/api/export/token-snapshot` | Add cache-analysis metadata |
| `GET` | `/api/deployments/preview` | No MVP change |

No new endpoint is required.

### 10.2 Analyze Request Additions

```json
{
  "mode": "live",
  "subscription_id": "00000000-0000-0000-0000-000000000000",
  "resource_group": "rg-ai",
  "workspace": "foundry-account",
  "deployment": "gpt-4.1-prod",
  "lookback_days": 14,
  "region": "eastus",
  "deployment_type": "global",
  "cache_mode": "auto",
  "cache_match_rate_override_pct": null,
  "cached_input_rate_override": null
}
```

Validation:

- `cache_mode` defaults to `auto`.
- `cache_match_rate_override_pct` must be between `0` and `100`.
- `cache_match_rate_override_pct` is required when `cache_mode="override"` and ignored otherwise.
- `cached_input_rate_override` must be non-negative.

### 10.3 Analyze Response Additions

Existing `metrics.cache_match_rate` remains and is extended additively:

```json
{
  "metrics": {
    "cache_match_rate": {
      "available": true,
      "source": "observed",
      "quality": "good",
      "avg_pct": 58.4,
      "p95_pct": 72.1,
      "coverage_pct": 94.6,
      "cached_prompt_tokens": 821004012,
      "active_prompt_tokens": 584233611,
      "active_tokens_observed": 731202344
    }
  },
  "charts": {
    "prompt_cache": {
      "timestamps": ["2026-07-01T00:00:00+00:00"],
      "match_rate_pct": [58.4],
      "prompt_tokens": [124200],
      "cached_prompt_tokens": [72533],
      "active_prompt_tokens": [51667],
      "source": "observed"
    }
  },
  "cost_analysis": {
    "pricing": {
      "cached_input_rate_per_million": 0.5,
      "cached_input_pricing_source": "live"
    },
    "cache_impact": {
      "applied": true,
      "source": "observed",
      "no_cache_normalized_avg_tpm": 94500,
      "cache_adjusted_normalized_avg_tpm": 65300,
      "normalized_tpm_reduction_pct": 30.9,
      "no_cache_recommended_ptu": 30,
      "cache_aware_recommended_ptu": 20,
      "ptu_avoided": 10,
      "no_cache_payg_monthly": 8200,
      "cache_aware_payg_monthly": 7010,
      "payg_cache_savings": 1190,
      "fixed_ptu_cost_changed": false,
      "calculation_note": "Cached prompt tokens reduce modeled utilization; fixed PTU cost changes only when the selected PTU count changes."
    }
  }
}
```

Chart arrays can contain `null` cache-rate values for missing intervals. Frontend types must represent this explicitly.

### 10.4 Pricing Rates Response Addition

```json
{
  "model": "gpt-4.1",
  "region": "eastus",
  "deployment_type": "global",
  "payg_input_rate_per_million": 2.0,
  "payg_cached_input_rate_per_million": 0.5,
  "payg_output_rate_per_million": 8.0,
  "ptu_hourly_rate": 1.0,
  "pricing_source": "live",
  "cached_input_pricing_source": "live",
  "pricing_as_of": "2026-07-13T09:00:00Z",
  "pricing_currency": "USD"
}
```

### 10.5 Authentication Requirements

- Demo mode: no Azure authentication.
- Live cache metrics: existing Azure authentication and read permissions.
- Pricing endpoint: no additional authentication beyond the current API deployment boundary.

### 10.6 Compatibility

- Changes are additive and correspond to a minor version increase of the documented analysis contract.
- Existing clients that ignore unknown fields continue to work.
- Existing `cache_match_rate.avg_pct`, `p95_pct`, and `available` fields remain available.

---

## 11. Success Criteria

### 11.1 MVP Success Definition

The feature is ready when a user can run demo or live analysis, see a correctly sourced cache-benefit chart, receive cache-aware PTU and cost outputs, and export the same evidence without any unsupported "free PTU" claim.

### 11.2 Functional Requirements

- ✅ Direct cache metric values are normalized correctly from Azure Percent to internal ratio.
- ✅ `ActiveTokens` is collected and used for validation or inference when available.
- ✅ Cache data source and coverage are included in every applicable response.
- ✅ Missing data never creates positive cache savings by default.
- ✅ PTU sizing subtracts cached prompt tokens before applying output weighting.
- ✅ PAYG separates uncached input, cached input, and output pricing.
- ✅ Fixed PTU cost remains unchanged for a fixed PTU count.
- ✅ Prompt Cache Benefit chart supports zoom, expand, tooltip, mobile layout, and empty state.
- ✅ Single and consolidation analyses use the same cache-aware formulas.
- ✅ Frontend and CLI reports include cache chart, impact, source, and disclaimer.
- ✅ Demo mode includes stable, low, regression, and consolidation cache patterns.

### 11.3 Quantitative Quality Indicators

| Indicator | Target |
|---|---:|
| Cache formula unit-test accuracy | Within `0.1%` for deterministic fixtures |
| PTU sizing parity with documented Foundry examples | Same rounded PTU count or within one valid deployment increment |
| PAYG cost fixture accuracy | Within `1%` of independently calculated expected value |
| Invalid cache values accepted | `0` |
| Missing-data false savings | `0` |
| Cache chart render time after data arrives | `< 200ms` for a 14-day, 1-minute dataset |
| Cache recalculation after override | `< 500ms p95` end to end |
| Export generation | `< 2s p95` for HTML; print view ready `< 3s` |
| Report inclusion | `100%` when cache evidence or override exists |
| Accessibility | Keyboard-reachable controls and non-color text summary |

Engineering verification covers deterministic formula, invalid-data, missing-data, report, API, frontend, and browser interaction cases. The runtime percentile targets for render, recalculation, and export latency require production-like telemetry and are not claimed as measured outcomes in this implementation pass.

### 11.4 User Experience Goals

- A user can answer **"How much cache benefit am I getting?"** within 10 seconds of opening results.
- A user can distinguish **observed** from **assumed** cache rates without opening formula details.
- A customer can understand why fixed PTU cost does not automatically fall when cache rate rises.
- The chart and report use the same terminology and values.

### 11.5 Definition of Done

- ✅ Requirement traceability table is complete.
- ✅ Unit, API, frontend, export, and E2E tests pass.
- ✅ Targeted Ruff, MyPy, Python compilation, ESLint, and TypeScript checks pass for modified feature paths. ESLint reports four pre-existing React hook warnings and zero errors.
- ✅ Official documentation links, pricing fallbacks, sizing fixtures, and user-facing wording received technical review.
- ✅ No prompt content or credentials appear in cache telemetry or reports.
- ✅ Rollback consists of disabling cache adjustment while retaining raw metrics and paired no-cache calculations.
- ⏳ Production performance percentiles and target-user usability outcomes remain rollout validation tasks.

### 11.6 Verified Implementation Snapshot

Verified on July 14, 2026:

| Check | Result |
|---|---:|
| Backend pytest suite | `844 passed`, `11 deselected` integration tests |
| Frontend Vitest suite | `103 passed` |
| Playwright E2E | `3 passed` |
| TypeScript production build | Passed |
| ESLint | `0 errors`, `4 pre-existing warnings` |
| Targeted MyPy / Ruff / Python compile | Passed |
| Independent correctness reviews | Completed; reported cache, consolidation, pricing, break-even, report, and UI defects resolved |

---

## 12. Implementation Phases

### Phase 1: Metric Foundation and Quality Model

**Goal:** Establish trustworthy, normalized cache data in the domain model.

**Estimated effort:** 3-4 engineering days.

**Deliverables:**

- ✅ Add `ACTIVE_TOKENS` metric and `active_tokens` model field.
- ✅ Normalize live cache Percent values at collection time.
- ✅ Add timestamp alignment without forward-fill.
- ✅ Add source, coverage, quality, and diagnostics metadata.
- ✅ Expand deterministic demo cache scenarios.
- ✅ Add collector/model tests for valid, missing, malformed, and partial data.

**Validation:**

- Live fixture `58.4` Percent becomes internal `0.584` and API `58.4%`.
- A live 0.5% value becomes `0.005`, not `0.5`.
- Demo ratio `0.584` remains `0.584`.
- Missing intervals remain null in chart payload and use 0% in conservative math.

### Phase 2: Cache-Aware Calculation and API Contract

**Goal:** Apply cache behavior consistently to sizing and economics.

**Estimated effort:** 5-7 engineering days.

**Deliverables:**

- ✅ Add reusable cache-impact calculation module.
- ✅ Extend pricing resolution with cached-input rate.
- ✅ Add cache mode and overrides to analysis requests.
- ✅ Add no-cache and cache-aware PTU, PAYG, hybrid, break-even, and safety outputs.
- ✅ Update consolidation to compute active load per deployment before merge.
- ✅ Add API response and formula-block fields.
- ✅ Add requirement-traced unit and API tests.

**Validation:**

- Documented Foundry sizing examples produce expected rounded PTU counts.
- A fixed PTU selection has identical fixed cost with and without cache.
- An unavailable metric produces no cache adjustment.
- Weighted consolidation results match hand-calculated fixtures.

### Phase 3: Dashboard and Reports

**Goal:** Make cache benefit understandable and shareable.

**Estimated effort:** 5-7 engineering days.

**Deliverables:**

- ✅ Add `PromptCacheChart.tsx` and ECharts registration.
- ✅ Expand the at-a-glance cache card and source badge.
- ✅ Add Advanced Assumptions cache controls.
- ✅ Add cache comparison and guidance copy.
- ✅ Add compact static SVG to `ExportReport.tsx`.
- ✅ Add Matplotlib/Jinja2 chart and section to CLI reports.
- ✅ Add responsive, accessibility, component, and export tests.

**Validation:**

- ✅ Observed, inferred, mixed, override, disabled, partial, limited, and unavailable states are explicitly labeled.
- ✅ Dashboard and reports use the same response values and paired economics.
- ⏳ Confirm the standard single-deployment export remains within two printed pages across supported browsers.
- ⏳ Complete a dedicated 375px visual-readability walkthrough.

### Phase 4: Verification and Controlled Rollout

**Goal:** Validate correctness against Azure guidance and production-like workloads.

**Estimated effort:** 3-5 engineering days.

**Deliverables:**

- ✅ Run benchmark fixtures across supported model families and deployment types.
- ✅ Compare cache-aware sizing with Foundry provisioned-throughput sizing examples.
- ✅ Run Playwright interaction tests.
- ✅ Validate telemetry payload privacy requirements in implementation and tests.
- ✅ Document operational guidance and rollback through `cache_mode="disabled"`.
- ⏳ Validate production-like latency percentiles.
- ⏳ Conduct usability walkthroughs with target users.

**Validation:**

- Deterministic calculation, missing-data, export, and interaction criteria pass.
- No known severity-1 or severity-2 calculation defect remains open after independent review.
- Production performance percentiles and the 80% walkthrough-comprehension target remain rollout gates.

### Overall Timeline

One engineer: approximately 3-4 weeks including review and stabilization. Two engineers working across backend and frontend/report tracks: approximately 2-3 weeks.

---

## 13. Future Considerations

- Ingest request-level `cached_tokens` usage through an optional customer telemetry file or Log Analytics integration.
- Compare in-memory and extended retention policies when model and region support are known.
- Add cache-rate anomaly detection and release-marker overlays.
- Add workload-separation recommendations based on cache competition and latency.
- Support spillover-target cache telemetry when the Standard target deployment is selected explicitly.
- Add historical cached-input pricing and invoice reconciliation.
- Add alerting when cache match falls below a user-defined threshold.
- Add a what-if optimizer showing the PTU and cost effect at `0%, 25%, 50%, 75%` cache rates.
- Include cache behavior in multi-model routing and model migration comparisons.
- Add a prompt-design checklist without collecting prompt contents.
- Surface `prompt_cache_retention` and `prompt_cache_key` education for supported APIs, without mutating customer applications.

---

## 14. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---:|---|
| Cache metric availability differs by SKU, model, or region | Users may expect observed data where Azure exposes none | High | Conservative unavailable state, `ActiveTokens` fallback, explicit what-if override |
| Percent-versus-ratio unit error | 100x calculation error | Medium | Normalize at collector boundary from documented Percent unit; dedicated 0.5% and 58.4% tests |
| Cached-input meter names change | Incorrect PAYG savings | Medium | Defensive parser, verified static rates, standard-rate conservative fallback, visible source |
| Users interpret cache as reducing fixed reservation cost | Misleading business decision | High | Mandatory fixed-cost copy in dashboard, formulas, tooltips, and reports |
| Applying source cache rate to spillover overstates savings | Hybrid estimate too optimistic | Medium | Price MVP spillover input as uncached and disclose approximation |
| Partial metric coverage biases average upward | Overstated capacity reduction | Medium | Coverage thresholds, prompt-token weighting, and zero benefit for missing evidence; single-deployment evidence below 50% remains contextual, while consolidation applies only attributable deployment evidence conservatively |
| `ActiveTokens` and derived values disagree | Conflicting evidence undermines trust | Medium | Show validation warning, use direct cache metric as primary, retain both raw diagnostics |
| Cache rate changes after deployment sizing | Purchased PTUs become insufficient | Medium | Keep no-cache baseline, show sensitivity, recommend benchmark and post-deployment monitoring |
| Chart increases bundle or render cost | Slower dashboard | Low | Reuse tree-shaken ECharts modules and LTTB sampling; enforce render budget |
| Reports exceed two pages | Customer-facing output loses clarity | Medium | Compact chart and evidence layout; omit chart only when unavailable and state why |

---

## 15. Appendix

### 15.1 Implemented Foundation

The repository now contains the following implemented cache-aware capabilities:

| Capability | Location | Current behavior |
|---|---|---|
| Cache metric model | `ptu_advisor/metrics/models.py` | Includes `ActiveTokens`, source, coverage, and conservative aggregation metadata |
| Cache collection and validation | `ptu_advisor/metrics/collector.py` | Normalizes Percent values, rejects malformed evidence, and validates aligned ActiveTokens bounds |
| Cache impact engine | `ptu_advisor/cost/cache.py` | Applies source precedence, gap inference, coverage policy, PTU sizing, spillover, and exact dual break-even math |
| Demo cache profiles | `ptu_advisor/demo.py` | Deterministic stable, low, regression, and consolidation scenarios |
| API economics | `ptu_advisor/api/server.py` | Returns cache-aware and paired no-cache PAYG, hybrid, break-even, safety, and recommendation outputs |
| Dashboard | `frontend/src/App.tsx` | Shows chart, source/quality, assumptions, fixed-cost clarification, paired ranges, and conservative warnings |
| Token snapshot export | `/api/export/token-snapshot` | Preserves CLI-compatible metrics and adds `_meta.cache_analysis` |
| Frontend report | `frontend/src/ExportReport.tsx` | Includes cache chart with missing-data gaps, paired economics, source, coverage, and warnings |
| CLI report | `report/generator.py` | Includes cache chart, sizing/cost comparison, source, quality, and fixed-cost wording |

### 15.2 Requirement Traceability

| Requirement | Description | Primary files | Required tests | KPI |
|---|---|---|---|---|
| `REQ-DATA-301` | Collect and normalize cache ratio and ActiveTokens | `metrics/models.py`, `metrics/collector.py` | `test_collector.py::test_cache_*`, `test_models.py::test_cache_*` | Data accuracy |
| `REQ-DATA-302` | Classify source, coverage, and quality conservatively | `cost/cache.py`, `api/server.py` | `test_cache_impact.py::test_quality_*` | Zero false savings |
| `REQ-COST-303` | Deduct cached prompt tokens from normalized PTU load | `cost/cache.py`, `cost/calculator.py` | `test_cache_impact.py::test_ptu_sizing_*` | Sizing parity |
| `REQ-COST-304` | Price cached PAYG input separately | `cost/price_resolver.py`, `api/server.py` | `test_price_resolver.py::test_cached_input_*` | Cost accuracy |
| `REQ-COST-305` | Preserve fixed PTU cost for fixed selected units | `cost/calculator.py`, `api/server.py` | `test_cache_impact.py::test_fixed_cost_unchanged` | Explanation accuracy |
| `REQ-UX-306` | Render Prompt Cache Benefit chart | `charts/PromptCacheChart.tsx`, `App.tsx` | `prompt-cache.test.tsx`, Playwright screenshot | Time-to-understand |
| `REQ-UX-307` | Expose explicit cache assumptions | `App.tsx`, `types.ts`, `api/server.py` | `prompt-cache.test.tsx::override_*` | Assumption clarity |
| `REQ-DATA-308` | Consolidate rates using prompt-token weighting | `metrics/merge.py` | `test_merge.py::test_cache_weighted_*` | Consolidation accuracy |
| `REQ-UX-309` | Include cache chart and impact in both report paths | `ExportReport.tsx`, `visualization/charts.py`, report template | `ExportReport.test.tsx`, `test_report_generator.py` | Report inclusion |
| `REQ-OBS-310` | Emit privacy-safe cache telemetry | `frontend/src/telemetry.ts` | telemetry payload tests | Adoption and quality |
| `REQ-SEC-311` | Never collect prompt contents or cache keys | collector, API, export paths | static scan and payload assertions | Security compliance |

### 15.3 Telemetry

Add events or dimensions:

```text
cache_metric_loaded
cache_adjustment_applied
cache_override_changed
cache_chart_rendered
cache_data_limited
```

Allowed dimensions:

```text
mode: demo | live
cache_source: observed | inferred | mixed | override | disabled | unavailable
cache_quality: good | partial | limited | unavailable
coverage_bucket: 0 | 1-49 | 50-79 | 80-100
ptu_avoided_bucket: 0 | 1-5 | 6-15 | 16+
recommendation_changed_by_cache: true | false
policy_version
```

Do not emit raw token arrays, exact deployment names, subscription identifiers, prompt content, or cache keys.

### 15.4 Test Matrix

| Case | Cache source | Coverage | Expected behavior |
|---|---|---:|---|
| High observed cache | Observed | 100% | Full adjustment and positive chart |
| Low observed cache | Observed | 100% | Small adjustment; no exaggerated savings |
| Partial data | Observed | 65% | Missing intervals use 0%; warning displayed |
| Limited data | Observed | 30% | Context chart only; primary math unchanged |
| ActiveTokens fallback | Inferred | 90% | Derived ratio and explicit inferred badge |
| No metrics | Unavailable | 0% | Conservative no-cache calculation |
| Manual override | Override | 100% assumed | Dashed line and report assumption |
| Disabled | Disabled | N/A | No adjustment despite observed metric |
| Fixed PTU slider | Any valid | Any applicable | Same fixed PTU cost; headroom changes |
| Consolidation | Mixed | Mixed | Per-deployment adjustment and weighted combined rate |
| Cached price unresolved | Any | Any | Standard input rate fallback; zero invented PAYG savings |

### 15.5 Official References

- [Prompt caching](https://learn.microsoft.com/azure/foundry/openai/how-to/prompt-caching)
- [Azure OpenAI monitoring data reference](https://learn.microsoft.com/azure/foundry/openai/monitor-openai-reference)
- [Determine PTU sizing for a workload](https://learn.microsoft.com/azure/foundry/openai/how-to/provisioned-throughput-sizing)
- [What is provisioned throughput?](https://learn.microsoft.com/azure/foundry/openai/concepts/provisioned-throughput)
- [Performance and latency](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/latency)
- [Azure OpenAI pricing](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/)

### 15.6 Related Product Documents

- [`docs/PRD.md`](../PRD.md)
- [`PRD-breakeven-cost-explorer.md`](PRD-breakeven-cost-explorer.md)
- [`PRD-live-pricing-fetch.md`](PRD-live-pricing-fetch.md)
- [`PRD-chart-overhaul-timeframe-selection.md`](PRD-chart-overhaul-timeframe-selection.md)
- [`PRD-daily-cost-chart.md`](PRD-daily-cost-chart.md)
- [`PRD-export-report.md`](PRD-export-report.md)
- [`PRD-multi-deployment-consolidation.md`](PRD-multi-deployment-consolidation.md)

### 15.7 Assumptions Requiring Validation

1. Azure Monitor may not expose cache match or ActiveTokens for every Standard/PAYG deployment; unavailable data must be expected behavior.
2. Cached-input Retail API meter naming and availability vary by model and deployment type.
3. The direct cache match metric is the preferred source when it and `ActiveTokens` disagree; disagreement must be disclosed and reviewed.
4. Spillover-target cache locality cannot be inferred from the source deployment in MVP.
5. Cache-aware formulas improve planning but do not replace a representative benchmark or the Foundry capacity calculator before purchase.
