# PRD: Multi-Deployment Consolidation Analysis

> **Version**: 1.2  
> **Date**: March 30, 2026  
> **Author**: PTU Advisor Team  
> **Priority**: P1 — High customer value  
> **Status**: Phase 3 Complete

---

## 1. Executive Summary

### Problem Statement

Many Azure OpenAI customers run **multiple PAYG deployments of the same model** across different use cases — for example, a `gpt-4o-customer-chat` deployment and a `gpt-4o-doc-processing` deployment in the same account. Each deployment individually may not justify PTU (low volume, low throttling), but **combined**, their aggregate TPM may cross the break-even point where a single shared PTU allocation becomes significantly cheaper.

Today, PTU Advisor only analyzes **one deployment at a time**. There is no way to answer the question:

> "If I merge these 3 gpt-4o deployments onto a single PTU reservation, would it be worth it?"

This forces Solution Engineers to manually export metrics from multiple runs and do the math in Excel — error-prone, time-consuming, and not repeatable.

### Proposed Solution

Add a **"Consolidation Analysis"** mode to the Deployment Advisor panel. After selecting an AI account, the user sees all deployments grouped by model. They select 2+ deployments **of the same model and deployment type** and click **"Analyze Consolidation."** The tool:

1. Fetches metrics for each selected deployment independently.
2. Aggregates the time-series data into a combined "virtual deployment."
3. Runs the full analysis engine (4-dimension scoring, cost modeling, break-even) on the combined workload.
4. Presents a **side-by-side comparison**: the sum of individual PAYG costs vs. one consolidated PTU+Spillover cost.
5. Clearly attributes which traffic, throttling, and latency signals come from which deployment throughout the results.

The user walks away with a clear answer: *"Consolidating these deployments onto PTU saves $X/month"* — or *"It doesn't make sense yet."*

### Success Criteria

| KPI | Target |
|---|---|
| User can select multiple deployments and see consolidated recommendation | End-to-end in < 30 seconds (demo mode) |
| Consolidation correctly sums TPM time series across deployments | Sum matches individual totals ± 1% |
| Break-even calculation on combined workload matches manual verification | ± 3% tolerance |
| User can tell which metrics come from which deployment | 100% — every chart and table labels the source |
| Model/type mismatch is prevented at the UI level | Cannot mix different models or deployment types |

---

## 2. User Experience & Functionality

### 2.1 User Personas

| Persona | Description | Key Need |
|---|---|---|
| **Platform Team Lead** | Manages 5–15 deployments of the same model across product teams | "Can I consolidate 4 gpt-4o deployments into one PTU to save money?" |
| **FinOps Engineer** | Optimizes cloud spend across the organization | Side-by-side cost comparison: separated PAYG vs. consolidated PTU |
| **Solution Engineer / CSA** | Advises customers during capacity planning reviews | Quick consolidation analysis to recommend PTU during engagements |

### 2.2 User Flow

The consolidation flow extends the existing Deployment Advisor panel. It is **not** a separate page — it's a mode within the same flow.

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Focus Topic + Data Source (unchanged)                  │
│  ┌─ [Cost Reduction] [Throttling] ... ─┐                       │
│  ┌─ ( ) Demo    (●) Connect to Azure  ─┐                       │
│                                                                 │
│  Step 2: Subscription → Account (unchanged)                     │
│  ┌─ [Contoso Prod (abc123…)] ▼ ─┐                              │
│  ┌─ [my-openai-account] ▼ ──────┐                              │
│                                                                 │
│  Step 3: Deployment Selection ← ENHANCED                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  Analysis Mode:                                          │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────┐  │   │
│  │  │  ● Single           │  │  ○ Consolidation         │  │   │
│  │  │    Deployment        │  │    (Multi-Deployment)    │  │   │
│  │  └─────────────────────┘  └──────────────────────────┘  │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────── Single Mode (current behavior) ──────────────┐  │
│  │  Select one deployment:                                    │  │
│  │  ○ gpt-4o-customer-chat       gpt-4o  · Standard          │  │
│  │  ● gpt-4o-doc-processing      gpt-4o  · Standard          │  │
│  │  ○ gpt-4o-mini-internal       gpt-4o-mini  · Standard     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [ ▶ Analyze ]                                                  │
└─────────────────────────────────────────────────────────────────┘
```

When the user switches to **Consolidation mode**, the deployment list changes to a **grouped multi-select with checkboxes**, filtered to compatible groups:

```
┌──────────── Consolidation Mode ─────────────────────────────────┐
│                                                                  │
│  Select 2 or more deployments of the same model to consolidate. │
│  Deployments are grouped by model — you can only select within  │
│  one group.                                                      │
│                                                                  │
│  ┌─ gpt-4o · Standard (3 deployments) ─────────────────────┐   │
│  │  ☑ gpt-4o-customer-chat       12,400 TPM avg · 3.2% 429 │   │
│  │  ☑ gpt-4o-doc-processing       8,700 TPM avg · 1.1% 429 │   │
│  │  ☐ gpt-4o-batch-nightly        2,100 TPM avg · 0.0% 429 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ gpt-4o-mini · Standard (2 deployments) ────────────────┐   │
│  │  ☐ gpt-4o-mini-internal         1,200 TPM avg · 0.0% 429│   │
│  │  ☐ gpt-4o-mini-reports          3,400 TPM avg · 0.1% 429│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ text-embedding-3-large · Standard (1 deployment) ──────┐   │
│  │  ☐ embeddings-prod              (only 1 — cannot consolidate)│
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Selected: 2 of 3 gpt-4o deployments                            │
│  Combined estimated TPM: ~21,100 avg                            │
│                                                                  │
│  [ ▶ Analyze Consolidation (2 deployments) ]                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Key UI rules:**

1. Deployments are grouped by **(model name, SKU type)** — e.g. all `gpt-4o · Standard` deployments form one group, all `gpt-4o · ProvisionedManaged` form another.
2. User can only check boxes **within one group**. Selecting in a different group unchecks the previous selection (radio-group behavior across groups, checkbox behavior within a group).
3. Groups with only 1 deployment are shown but disabled for consolidation (grayed out, tooltip: "Only 1 deployment — nothing to consolidate").
4. Mini-preview of avg TPM and throttling rate per deployment is shown inline to help the user decide which ones to include.
5. A live counter at the bottom shows "Selected: N of M" and the combined estimated TPM.

### 2.3 Consolidation Results View

The results view keeps the same structure as today (At a Glance → Evidence → Financial → Scoring → Rationale) but adds **two enhancements**:

#### Enhancement A: "Consolidation Summary" header card

A new card appears at the top of the results, before At a Glance:

```
┌──────────────────────────────────────────────────────────────────┐
│  🔗 Consolidation Analysis — 2 gpt-4o deployments               │
│                                                                  │
│  Deployments analyzed:                                           │
│  ┌────────────────────────────┬────────────────────────────────┐ │
│  │ gpt-4o-customer-chat       │ gpt-4o-doc-processing          │ │
│  │ Avg TPM: 12,400            │ Avg TPM: 8,700                 │ │
│  │ Peak TPM: 18,200           │ Peak TPM: 14,100               │ │
│  │ Throttling: 3.2%           │ Throttling: 1.1%               │ │
│  │ Requests: 842K             │ Requests: 523K                 │ │
│  └────────────────────────────┴────────────────────────────────┘ │
│                                                                  │
│  Combined workload:                                              │
│  Avg TPM: 21,100  ·  Peak TPM: 29,800  ·  Throttling: 2.4%    │
│                                                                  │
│  💰 Consolidation verdict:                                       │
│  Merging these deployments onto a single PTU saves               │
│  estimated $3,200/month (28%) vs running both on PAYG.           │
│                                                                  │
│  Individual PAYG total: $11,400/mo                               │
│  Consolidated PTU + Spillover: $8,200/mo                         │
│  Break-even TPM: 15,600 (combined is 35% above)                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### Enhancement B: Per-deployment attribution in charts

Every time-series chart (Tokens, Requests, Latency, TPM, Throttling) shows **stacked or layered traces**, color-coded by deployment:

```
  TPM over time
  ┌──────────────────────────────────────────┐
  │                                          │
  │  ████████████████████████  ← Combined    │
  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓████████  ← customer-chat │
  │  ░░░░░░░░░░░░░░░░░░░░░░░  ← doc-process  │
  │                                          │
  └──────────────────────────────────────────┘
  Legend: ██ Combined  ▓▓ customer-chat  ░░ doc-processing
```

- **Token charts**: Stacked area showing each deployment's contribution.
- **Request charts**: Stacked bar for successful/throttled per deployment.
- **Latency charts**: Overlaid lines (not stacked) — latency doesn't aggregate additively. Each deployment's P50/P95/P99 is shown as a separate trace.
- **TPM chart**: Stacked area showing how each deployment contributes to the combined TPM.
- **Cost curve chart**: Shows the combined workload's break-even analysis (single set of cost curves for the merged traffic).

#### Enhancement C: Individual vs. consolidated cost comparison table

In the Financial section, replace the simple PAYG-vs-Hybrid comparison with a 3-column layout:

```
┌──────────────────────────────────────────────────────────────────┐
│  💰 Cost Comparison                                              │
│                                                                  │
│  ┌── Individual ───────┐  ┌── Consolidated ──┐  ┌── Savings ──┐ │
│  │ (PAYG, separate)    │  │ (PTU + Spillover)│  │             │ │
│  │                     │  │                  │  │             │ │
│  │ customer-chat:      │  │ 25 PTU baseline  │  │  $3,200/mo  │ │
│  │   $6,800/mo         │  │ $8,200/mo total  │  │  (28%)      │ │
│  │ doc-processing:     │  │                  │  │             │ │
│  │   $4,600/mo         │  │ Spillover: 12%   │  │  $38,400/yr │ │
│  │ ─────────────       │  │                  │  │             │ │
│  │ Total: $11,400/mo   │  │                  │  │             │ │
│  └─────────────────────┘  └──────────────────┘  └─────────────┘ │
│                                                                  │
│  Break-even: 15,600 TPM combined                                 │
│  Your combined avg TPM (21,100) is 35% above break-even  ✅     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4 User Stories

#### US-1: Select multiple deployments for consolidation

> **As a** Platform Team Lead,  
> **I want** to select 2+ deployments of the same model and see them analyzed together,  
> **so that** I can determine if consolidating onto PTU saves money.

**Acceptance Criteria:**
- [x] "Consolidation" mode toggle is visible in the deployment selection step
- [x] Deployments are grouped by (model name, SKU type)
- [x] Checkboxes allow multi-select within a single group
- [x] Selecting across groups is prevented (with toast notification and tooltip)
- [x] "Analyze Consolidation" button is enabled only when ≥2 deployments are selected
- [x] Groups with only 1 deployment show a "nothing to consolidate" label

#### US-2: See combined workload analysis

> **As a** FinOps Engineer,  
> **I want** to see the 4-dimension scoring and cost analysis on the combined workload,  
> **so that** I can make a data-driven decision about PTU consolidation.

**Acceptance Criteria:**
- [x] Combined TPM time-series is the element-wise sum of individual deployment TPM series
- [x] Combined throttled requests is the element-wise sum across deployments
- [x] 4-dimension analysis runs on the combined `DeploymentMetrics` object
- [x] Cost analysis (break-even, spillover, cost curves) uses the combined workload
- [x] Recommendation reflects the consolidated picture, not any individual deployment

#### US-3: Understand per-deployment contribution

> **As a** Solution Engineer,  
> **I want** to see which deployment contributes how much traffic, throttling, and latency,  
> **so that** I can explain to the customer why consolidation helps (or doesn't).

**Acceptance Criteria:**
- [x] Consolidation Summary card shows per-deployment metrics side-by-side
- [x] Charts use color-coded traces with deployment name in the legend *(Phase 2 — per-deployment chart attribution)*
- [x] Cost comparison shows each deployment's individual PAYG cost alongside the consolidated total
- [x] Hovering over a chart point shows the per-deployment breakdown in the tooltip *(Phase 3 — tooltip enhancement)*

#### US-4: Prevent mismatched consolidation

> **As a** user,  
> **I want** the tool to prevent me from combining gpt-4o and gpt-4o-mini deployments,  
> **so that** the analysis is valid (you can't share a PTU allocation across different models).

**Acceptance Criteria:**
- [x] Deployments are grouped by (model base name, deployment type)
- [x] Checkbox selection is constrained to one group at a time
- [x] If user tries to check a deployment in a different group, previous selection is cleared with a toast notification
- [x] Tooltip on group headers explains: "PTU capacity is model-specific — only same-model deployments can share a PTU allocation"

#### US-5: Demo mode consolidation

> **As a** user without Azure credentials,  
> **I want** to try consolidation in demo mode,  
> **so that** I can evaluate the feature without a live connection.

**Acceptance Criteria:**
- [x] Demo mode generates 2–3 same-model deployments per scenario group
- [x] User can multi-select among demo deployments and run consolidation
- [ ] Results clearly show "Demo Data" watermark *(existing demo mode watermark; consolidation inherits it)*

---

## 3. Technical Specifications

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React)                                                │
│                                                                  │
│  ┌── Deployment Picker ───────────────────────────────────┐     │
│  │  Mode toggle: Single | Consolidation                    │     │
│  │  Consolidation: grouped checkboxes by (model, sku_type) │     │
│  │  Mini-preview: avg TPM + throttle %                     │     │
│  └───────────────────────────────┬─────────────────────────┘     │
│                                  │                               │
│                    POST /api/analyze-consolidation               │
│                    { deployments: ["dep-a", "dep-b"], ... }      │
│                                  │                               │
└──────────────────────────────────┼───────────────────────────────┘
                                   │
┌──────────────────────────────────┼───────────────────────────────┐
│  Backend (FastAPI)               ▼                               │
│                                                                  │
│  ┌── /api/analyze-consolidation ───────────────────────────┐    │
│  │                                                          │    │
│  │  1. Validate: all deployments share same model + type    │    │
│  │                                                          │    │
│  │  2. For each deployment:                                 │    │
│  │     ├─ Collect metrics (MetricsCollector.collect())      │    │
│  │     └─ Store as individual DeploymentMetrics             │    │
│  │                                                          │    │
│  │  3. Merge:                                               │    │
│  │     ├─ Align timestamps across deployments               │    │
│  │     ├─ Sum: TPM, requests, prompt/completion tokens      │    │
│  │     ├─ Sum: throttled requests, successful requests      │    │
│  │     ├─ Weighted avg: latency P50/P95/P99 (by req count) │    │
│  │     └─ Produce combined DeploymentMetrics                │    │
│  │                                                          │    │
│  │  4. Analyze combined metrics (DecisionEngine.analyze())  │    │
│  │                                                          │    │
│  │  5. Cost analysis:                                       │    │
│  │     ├─ Individual PAYG cost per deployment               │    │
│  │     ├─ Consolidated PTU+Spillover cost                   │    │
│  │     ├─ Break-even on combined workload                   │    │
│  │     └─ Cost curves for combined traffic                  │    │
│  │                                                          │    │
│  │  6. Return ConsolidationResponse                         │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 New API Endpoint

#### `POST /api/analyze-consolidation`

**Request:**

```json
{
  "mode": "live",
  "deployments": ["gpt-4o-customer-chat", "gpt-4o-doc-processing"],
  "subscription_id": "...",
  "resource_group": "...",
  "workspace": "...",
  "focus_topic": "Cost Reduction",
  "lookback_days": 14,
  "reservation_type": "Monthly Commitment (Estimated 64% off)",
  "region": "eastus",
  "deployment_type": "global"
}
```

**Validation rules:**
- `deployments` must contain ≥ 2 entries
- All deployments must exist in the specified account
- All deployments must share the same model name (base, e.g. `gpt-4o`)
- All deployments must share the same SKU type (`Standard` or `ProvisionedManaged`)
- Return HTTP 422 with clear error message if validation fails

**Response:**

```json
{
  "consolidation_summary": {
    "deployment_count": 2,
    "model_name": "gpt-4o",
    "deployment_type": "global",
    "individual_deployments": [
      {
        "name": "gpt-4o-customer-chat",
        "avg_tpm": 12400,
        "peak_tpm": 18200,
        "throttling_rate_pct": 3.2,
        "total_requests": 842000,
        "latency_p50": 350,
        "latency_p95": 1800,
        "payg_monthly_cost": 6800
      },
      {
        "name": "gpt-4o-doc-processing",
        "avg_tpm": 8700,
        "peak_tpm": 14100,
        "throttling_rate_pct": 1.1,
        "total_requests": 523000,
        "latency_p50": 280,
        "latency_p95": 1200,
        "payg_monthly_cost": 4600
      }
    ],
    "combined_avg_tpm": 21100,
    "combined_peak_tpm": 29800,
    "combined_throttling_rate_pct": 2.4,
    "individual_payg_total": 11400,
    "consolidated_hybrid_cost": 8200,
    "savings": 3200,
    "savings_pct": 28.1
  },
  "recommendation": "ptu_recommended",
  "confidence": 0.82,
  "summary": "...",
  "explanation": "...",
  "dimensions": [ ... ],
  "metrics": { ... },
  "charts": {
    "tokens": {
      "timestamps": ["..."],
      "per_deployment": {
        "gpt-4o-customer-chat": { "prompt": [...], "completion": [...] },
        "gpt-4o-doc-processing": { "prompt": [...], "completion": [...] }
      },
      "combined": { "prompt": [...], "completion": [...], "total": [...] }
    },
    "requests": {
      "timestamps": ["..."],
      "per_deployment": {
        "gpt-4o-customer-chat": { "successful": [...], "throttled": [...] },
        "gpt-4o-doc-processing": { "successful": [...], "throttled": [...] }
      },
      "combined": { "successful": [...], "throttled": [...], "total": [...] }
    },
    "latency": {
      "timestamps": ["..."],
      "per_deployment": {
        "gpt-4o-customer-chat": { "p50": [...], "p95": [...], "p99": [...] },
        "gpt-4o-doc-processing": { "p50": [...], "p95": [...], "p99": [...] }
      }
    },
    "tpm": {
      "timestamps": ["..."],
      "per_deployment": {
        "gpt-4o-customer-chat": [...],
        "gpt-4o-doc-processing": [...]
      },
      "combined": [...]
    },
    "cost_curves": { "...same structure as single-deployment..." }
  },
  "cost_analysis": { "...same structure, plus individual_payg breakdown..." },
  "insights": { "..." }
}
```

### 3.3 Time-Series Merging Logic

The core merging logic aligns and combines per-minute metrics:

```python
def merge_deployment_metrics(
    deployments: List[DeploymentMetrics],
) -> DeploymentMetrics:
    """
    Merge multiple same-model DeploymentMetrics into a combined view.

    Additive metrics (TPM, requests, tokens): element-wise sum.
    Latency metrics: request-weighted average (not summed).
    """
```

**Timestamp alignment strategy:**
- Use the **union** of all timestamps across deployments.
- For each deployment, forward-fill missing timestamps with the previous value (or 0 if no prior value).
- This handles deployments with slightly different collection windows or granularity.

**Merging rules by metric type:**

| Metric | Merge Strategy | Rationale |
|---|---|---|
| `tokens_per_minute` | Element-wise sum | Total TPM is the sum of all deployments |
| `prompt_tokens` | Element-wise sum | Total prompt tokens = sum |
| `completion_tokens` | Element-wise sum | Total completion tokens = sum |
| `requests_per_minute` | Element-wise sum | Total requests = sum |
| `successful_requests` | Element-wise sum | Total successes = sum |
| `throttled_requests` | Element-wise sum | Total 429s = sum |
| `time_to_first_byte_p50` | Weighted average by request count | Latency doesn't sum; heavier deployments dominate |
| `time_to_first_byte_p95` | Weighted average by request count | Same reasoning |
| `time_to_first_byte_p99` | Max across deployments | P99 should reflect worst-case |

### 3.4 Demo Mode Extension

Add a new demo scenario group for consolidation:

```python
class DemoScenario(str, Enum):
    # ... existing scenarios ...
    
    # Consolidation scenarios
    CONSOLIDATE_WORTH_IT = "consolidate-worth-it"
    CONSOLIDATE_NOT_WORTH_IT = "consolidate-not-worth-it"
```

Each consolidation demo scenario generates **3 sibling deployments** of the same model:

| Scenario | Model | Deployment A (base) | Deployment B (scale) | Deployment C (scale) | Combined Verdict |
|---|---|---|---|---|---|
| `consolidate-worth-it` | gpt-4o (2024-11-20) | 15K TPM, 2% throttle | 80% of base TPM, 75% throttle scale | 53% of base TPM, 25% throttle scale | PTU Recommended |
| `consolidate-not-worth-it` | gpt-4o-mini (2024-07-18) | 3K TPM, 0% throttle | 50% of base TPM, 0% throttle | 27% of base TPM, 0% throttle | Not Recommended |

### 3.5 Frontend Changes

#### 3.5.1 State additions (App.tsx)

```typescript
type AnalysisMode = 'single' | 'consolidation'

// New state
const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('single')
const [selectedDeployments, setSelectedDeployments] = useState<string[]>([])
const [selectedModelGroup, setSelectedModelGroup] = useState<string | null>(null)

// Derived: group deployments by (model, sku_type)
const deploymentGroups = useMemo(() => {
  return groupBy(deployments, d => `${d.model}::${d.sku_type}`)
}, [deployments])
```

#### 3.5.2 New components

| Component | Purpose |
|---|---|
| `AnalysisModeToggle` | Radio toggle between "Single Deployment" and "Consolidation" |
| `DeploymentGroupPicker` | Grouped checkbox list with model group headers |
| `ConsolidationSummaryCard` | Header card showing per-deployment stats + combined |
| `StackedDeploymentChart` | Wrapper around Recharts that renders stacked/layered traces |
| `ConsolidationCostTable` | 3-column Individual vs Consolidated vs Savings layout |

#### 3.5.3 Chart color assignment

Each deployment gets a consistent color from a deterministic palette:

```typescript
const DEPLOYMENT_COLORS = [
  '#5B7FFF',  // blue
  '#2F9E77',  // green
  '#C58A2A',  // amber
  '#A78BFA',  // purple
  '#B35252',  // red
] as const
```

Colors are assigned by index within the selected group. The "Combined" trace always uses white (`#e8ecf2`) with higher opacity.

### 3.6 Types (types.ts)

```typescript
export type ConsolidationSummary = {
  deployment_count: number
  model_name: string
  deployment_type: string
  individual_deployments: Array<{
    name: string
    avg_tpm: number
    peak_tpm: number
    throttling_rate_pct: number
    total_requests: number
    latency_p50: number
    latency_p95: number
    payg_monthly_cost: number
  }>
  combined_avg_tpm: number
  combined_peak_tpm: number
  combined_throttling_rate_pct: number
  individual_payg_total: number
  consolidated_hybrid_cost: number
  savings: number
  savings_pct: number
}

export type ConsolidationResponse = AnalysisResponse & {
  consolidation_summary: ConsolidationSummary
  charts: AnalysisResponse['charts'] & {
    tokens: AnalysisResponse['charts']['tokens'] & {
      per_deployment: Record<string, { prompt: number[]; completion: number[] }>
    }
    requests: AnalysisResponse['charts']['requests'] & {
      per_deployment: Record<string, { successful: number[]; throttled: number[] }>
    }
    latency: AnalysisResponse['charts']['latency'] & {
      per_deployment: Record<string, { p50: number[]; p95: number[]; p99: number[] }>
    }
    tpm: AnalysisResponse['charts']['tpm'] & {
      per_deployment: Record<string, number[]>
    }
  }
}
```

---

## 4. Non-Goals

| Out of Scope | Reason |
|---|---|
| Cross-model consolidation (e.g. gpt-4o + gpt-4o-mini) | PTU allocations are model-specific; this is technically impossible |
| Cross-account consolidation | Different Azure accounts can't share PTU; adds complexity for v1 |
| Automatic "best grouping" optimizer | Would need to evaluate all deployment combinations; defer to v2 |
| Consolidation within the PTU Calculator | Calculator is for manual estimation; consolidation needs real metrics |
| Consolidation in the CLI | CLI workflow is single-deployment; add if there's demand |

---

## 5. Edge Cases & Error Handling

| Scenario | Handling |
|---|---|
| User selects deployments with non-overlapping time windows | Warn: "Deployment X has no data for days Y–Z. Consolidation will treat missing periods as 0 TPM." |
| One deployment has no traffic in the lookback window | Include in the selection list but show "0 TPM avg" preview. Analysis proceeds with zero-filled series for that deployment. |
| User selects 6+ deployments | Allow up to 10. Beyond 10, show warning: "Analyzing many deployments may take longer. Consider narrowing your selection." |
| All selected deployments are already on PTU (ProvisionedManaged) | Show different messaging: "These deployments already use PTU. This analysis shows what their combined PAYG cost would be vs the current PTU spend." |
| Deployments have different granularity intervals | Resample to the coarsest interval before merging |

---

## 6. UX Copy & Clarity Principles

The consolidation feature must be **immediately understandable**. Key copy guidelines:

1. **Verb: "Consolidate"** — not "merge," "combine," or "aggregate." Consolidate is the Azure-native term for bringing deployments onto shared PTU capacity.
2. **Always name deployments** — never say "Deployment 1" or "Deployment A." Use the full deployment name throughout.
3. **Color-code consistently** — every chart, table, and tooltip uses the same color for the same deployment.
4. **Show the math** — the Financial section must show: `$X (chat) + $Y (docs) = $Z total PAYG → $W consolidated PTU → saves $S/mo (P%)`.
5. **Status labels on every data point** — tooltips always include `[deployment-name]: value` rather than just the value.
6. **Explain why consolidation helps** — include a one-sentence explanation: *"Consolidating multiple low-volume deployments into shared PTU capacity increases utilization, which is what makes PTU cost-effective."*

---

## 7. Implementation Phases

### Phase 1: Core consolidation (MVP) — COMPLETE

**Scope:** Backend merging + API endpoint + basic frontend multi-select + consolidation summary card + cost comparison table.

| Item | Effort | Status |
|---|---|---|
| `merge_deployment_metrics()` function | S | Done |
| `POST /api/analyze-consolidation` endpoint | M | Done |
| Validation logic (same model + SKU type) | S | Done |
| Frontend: analysis mode toggle | S | Done |
| Frontend: grouped deployment picker with checkboxes | M | Done |
| Frontend: consolidation summary card | M | Done |
| Frontend: cost comparison table (Individual vs Consolidated vs Savings) | M | Done |
| Demo mode: consolidation scenarios (2) | S | Done |
| Toast notification on cross-group selection clear | S | Done |
| Tooltip on group headers explaining PTU model constraint | S | Done |
| Enriched cost table (per-deployment PAYG, spillover %, break-even, annual savings) | M | Done |
| Inline TPM/throttle preview per deployment in picker (post-analysis) | S | Done |
| Combined estimated TPM in selection counter | S | Done |

**Implementation Notes (Phase 1):**
- Mini-preview TPM/throttle data in the picker (§2.2 rule 4) is shown **post-analysis** from `consolidationSummary.individual_deployments` rather than pre-fetched. A lightweight `GET /api/deployments/preview` endpoint was added in Phase 3 to provide pre-analysis preview data.
- Demo scenarios use **scaling factors** for sibling deployment generation rather than exact TPM values from the PRD table. The CONSOLIDATE_WORTH_IT scenario uses gpt-4o (15K base TPM, siblings at 80%/53% scale); the CONSOLIDATE_NOT_WORTH_IT scenario uses gpt-4o-mini (3K base TPM, siblings at 50%/27% scale).
- Latency P99 merge uses **element-wise max** (worst-case) instead of weighted average, matching the PRD spec.
- Max 10 deployments enforced at Pydantic validation level (`max_length=10`).
- Default granularity is 1 minute (changed from original 5-minute default).
- SKU type validation added to both `merge_deployment_metrics()` and the API endpoint.

**Test Coverage:**
- 33 backend unit tests: 30 in `tests/test_merge.py` (merge logic) + 3 new SKU/max validation tests
- 30 backend API tests: `tests/test_consolidation_api.py` (demo mode, validation, request params, per-deployment chart data)
- 52 frontend tests pass (TypeScript type-checks clean)

### Phase 2: Per-deployment chart attribution — COMPLETE

**Scope:** Stacked/layered charts showing per-deployment contribution.

| Item | Status |
|---|---|
| Backend: `serialize_per_deployment_charts()` in merge.py returns `per_deployment` chart series | Done |
| Backend: consolidation endpoint enriches response with per-deployment data + latency section | Done |
| Frontend: `DEPLOYMENT_COLORS` palette + `getDeploymentColor()` + `hexToRgba()` in theme.ts | Done |
| Frontend: `ConsolidationCharts` type + per-deployment sub-types in types.ts | Done |
| Frontend: `TokenVolumeChart` — stacked areas per deployment + combined dashed line | Done |
| Frontend: `RequestOutcomesChart` — stacked areas per deployment + combined dashed line | Done |
| Frontend: `ThrottleChart` — stacked areas per deployment + combined dashed line | Done |
| Frontend: `TpmBandChart` — stacked areas per deployment + combined dashed line (preserves Avg/refLabel) | Done |
| Frontend: `LatencyOverlayChart` — NEW component for per-deployment P95 lines + combined P50/P95 | Done |
| Frontend: App.tsx integration — `perDepCharts` useMemo + props passed to all charts + LatencyOverlayChart card | Done |
| Backend tests: 12 new tests covering per-deployment data shape, alignment, latency section | Done |
| Full regression: 641 backend tests pass, 52 frontend tests pass, TypeScript clean | Done |

### Phase 3: Polish & edge cases — COMPLETE

**Scope:** Export support, error handling, UX refinements.

| Item | Effort | Status |
|---|---|---|
| Export Report support for consolidation results | M | Done |
| Per-deployment tooltip breakdown on chart hover | S | Done |
| Time window mismatch warnings | S | Done |
| "Already on PTU" messaging variant | S | Done |
| Limit enforcement (max 10 deployments) | ~~S~~ Done in Phase 1 | Done |
| Lightweight `GET /api/deployments/preview` for pre-analysis TPM/throttle | S | Done |

**Phase 3 Implementation Log (Tooltips):**
- `fmtPct(part, total)` utility added to `frontend/src/charts/theme.ts`
- All 5 consolidation charts enhanced with per-deployment tooltip breakdowns:
  - `TokenVolumeChart` — combined total + per-dep total with prompt/completion + % contribution
  - `RequestOutcomesChart` — combined OK+429 + per-dep grouped OK/429 + % contribution
  - `ThrottleChart` — combined total + per-dep with % contribution
  - `TpmBandChart` — combined total + per-dep with % contribution + avg/refLine footer
  - `LatencyOverlayChart` — combined P95+P50 + per-dep P95+P50 from raw data

**Phase 3 Implementation Log (Export Report):**
- `ExportReport.tsx` — added `consolidationSummary` optional prop, consolidation header, section 2 consolidation summary table, per-deployment metrics table, consolidation cost comparison, shifted section numbering, CSS for `.report-consolidation-table` and `.consolidation-total-row`
- `App.tsx` — wired `consolidationSummary` prop to `<ExportReport>`
- Export filename: `ptu-consolidation-{model}-{count}deps-{date}.html` in consolidation mode, `ptu-assessment-{deployment}-{date}.html` in single mode
- HTML `<title>` dynamically set to "Consolidation Assessment" vs "Deployment Assessment"
- 10 new tests in `ExportReport.test.tsx` covering consolidation content, section numbering, savings messaging, filename prefixes
- Full regression: 641 backend tests pass, 62 frontend tests pass, TypeScript clean, Docker builds

**Phase 3 Implementation Log (Time Window Mismatch Warnings):**
- Backend: Added `warnings: List[str]` field to `ConsolidationSummary` model (server.py)
- Backend: Time-window mismatch detection — if a deployment's data span covers < 80% of the global analysis window, a warning is generated identifying the missing date ranges
- Frontend: `warnings: string[]` added to `ConsolidationSummary` type (types.ts)
- Frontend: Amber warning banner with ⚠ SVG icon displayed above consolidation summary card when warnings are present (App.tsx)
- Frontend: Warnings rendered in export report (ExportReport.tsx)
- 6 backend tests in `TestTimeWindowMismatchWarnings` class (test_consolidation_api.py)
- 5 frontend tests in "Consolidation export — warnings and all_on_ptu" describe block (ExportReport.test.tsx)

**Phase 3 Implementation Log ("Already on PTU" Messaging):**
- Backend: Added `all_on_ptu: bool` field to `ConsolidationSummary` model (server.py)
- Backend: Detection logic — checks if all selected deployments have `sku_type == "ProvisionedManaged"`, adds warning message
- Frontend: 3-branch verdict messaging in consolidation summary card: (1) all_on_ptu + savings, (2) all_on_ptu + no savings, (3) standard PAYG→PTU message (App.tsx)
- Frontend: `all_on_ptu` flag rendered in export report with appropriate messaging (ExportReport.tsx)
- 7 backend tests in `TestAllOnPtuDetection` class (test_consolidation_api.py)
- Full regression: 654 backend tests pass, 67 frontend tests pass, TypeScript clean

**Phase 3 Implementation Log (Lightweight Preview Endpoint):**
- Backend: `DeploymentPreview(BaseModel)` class with `name`, `avg_tpm`, `throttling_rate_pct` fields (server.py line ~1564)
- Backend: `GET /api/deployments/preview` endpoint — demo mode generates metrics from consolidation demo scenario and extracts summary stats; live mode creates `MetricsCollector` per deployment with 5-minute granularity for speed (server.py lines ~1572-1654)
- Backend: Endpoint uses `focus_topic` query param to select demo scenario (e.g. "Cost Reduction" → CONSOLIDATE_WORTH_IT)
- Frontend: `DeploymentPreview` type added to types.ts; `api.deploymentPreview()` method added to api.ts
- Frontend: `deploymentPreviews` state + `useEffect` in App.tsx fetches preview data when `analysisMode === 'consolidation'` in demo mode
- Frontend: Preview chips in deployment picker show dashed border styling (`.deployment-chip-preview` CSS class) when pre-analysis data is available; post-analysis data from `consolidationSummary` takes precedence with solid `deployment-chip-metric` styling
- 15 backend tests: 8 in `TestDeploymentPreviewDemoMode` + 7 in `TestDeploymentPreviewLiveMode` (test_consolidation_api.py)
- Full regression: 669 backend tests pass, 67 frontend tests pass, TypeScript clean

---

## 8. Open Questions

| # | Question | Status |
|---|---|---|
| 1 | Should the mini-preview TPM/throttle in the deployment picker be fetched live (slow) or use cached/estimated values? | **Resolved (Phase 3)**: Lightweight `GET /api/deployments/preview` endpoint fetches summary stats pre-analysis. Demo mode uses generated metrics; live mode uses 5-minute granularity for speed. Post-analysis data from `consolidationSummary` takes precedence. |
| 2 | Should we show a "what if you added deployment X" suggestion after consolidation results? | Defer to v2. Interesting but adds complexity. |
| 3 | For consolidation, should the PTU baseline slider still be interactive? | **Yes — Implemented.** The slider operates on the merged TPM series. |
| 4 | Should consolidation analysis support the time-window zoom feature? | **Yes — Implemented.** Zoom works identically to single-deployment mode. |
