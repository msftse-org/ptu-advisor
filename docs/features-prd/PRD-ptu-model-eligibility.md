# PRD: PTU Model Eligibility — Deployment Gate & Visual Indicators

> **Version**: 1.0  
> **Date**: March 17, 2026  
> **Author**: PTU Advisor Team  
> **Status**: 📋 Proposed

---

## 1. Executive Summary

### Problem Statement

PTU (Provisioned Throughput Units) is only supported for a specific subset of Azure OpenAI models — primarily the GPT and o-series families. However, PTU Advisor currently allows users to select **any** deployment for analysis, including deployments running models that have no PTU offering (e.g., embedding models like `text-embedding-ada-002`, image generation models like `dall-e-3`, or third-party models served via Azure AI like Llama, Mistral, Phi, etc.).

When a user runs PTU Advisor analysis on a non-PTU-eligible deployment, the results are meaningless: the cost comparison has no valid PTU pricing baseline, the PTU sizing calculator cannot compute units, and the recommendation is misleading. This wastes the user's time and erodes trust in the tool.

### Core Assumption (Validated)

**PTU is only available for specific Azure OpenAI chat/completion models.** This is confirmed by:

1. **Azure documentation**: The [Provisioned Throughput Units (PTU) documentation](https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput) lists specific models with PTU capacity rates (tokens-per-minute per PTU).
2. **Our own config**: `MODEL_CAPACITY_CONFIGS` in `ptu_advisor/config.py` enumerates the PTU-eligible models with their capacity specs:
   - `gpt-5` | `gpt-4.1` | `gpt-4.1-mini` | `gpt-4.1-nano`
   - `gpt-4o` | `gpt-4o-mini`
   - `o1` | `o3-mini` | `o4-mini`
3. **Models NOT eligible for PTU** include:
   - Embedding models (`text-embedding-ada-002`, `text-embedding-3-small/large`)
   - Image generation models (`dall-e-3`)
   - Audio/speech models (`whisper`, `tts`)
   - Third-party models served on Azure AI (`Llama`, `Mistral`, `Phi`, `Cohere`, etc.)
   - Legacy models (`gpt-3.5-turbo` — retired from PTU)

### Proposed Solution

Add a **PTU eligibility gate** to the deployment selection step that:

1. Cross-references each discovered deployment's `model` field against the known PTU-eligible model list
2. Visually distinguishes eligible vs ineligible deployments with clear badges and styling
3. **Grays out and disables** ineligible deployments so they cannot be selected for analysis
4. Provides a clear, informative message explaining why a deployment is ineligible
5. Keeps the list complete (users still see all their deployments) while guiding them to actionable choices

### Success Criteria

| KPI | Target |
|-----|--------|
| Non-PTU deployments cannot trigger analysis | 100% — radio button disabled, "Analyze" blocked |
| User comprehension | ≥ 90% of users understand why a deployment is grayed out (message clarity) |
| False negatives | 0% — no PTU-eligible model is incorrectly marked ineligible |
| False positives | 0% — no ineligible model can bypass the gate |
| New model onboarding | Adding a new PTU-eligible model requires editing only `MODEL_CAPACITY_CONFIGS` |

---

## 2. User Stories

### US-1: User sees mixed deployments in live mode
> **As a** platform engineer with diverse Azure OpenAI deployments,  
> **I want to** see which of my deployments are eligible for PTU analysis,  
> **so that** I don't waste time analyzing deployments where PTU isn't an option.

### US-2: User tries to select a non-eligible deployment
> **As a** developer unfamiliar with PTU model restrictions,  
> **I want to** see a clear explanation when a deployment is grayed out,  
> **so that** I understand the restriction and can focus on eligible deployments.

### US-3: User has only ineligible deployments
> **As a** user whose account only contains embedding or third-party model deployments,  
> **I want to** see a helpful empty state message,  
> **so that** I understand why no analysis is available and what models would be needed.

### US-4: User sees eligibility at a glance
> **As a** platform engineer scanning 10+ deployments,  
> **I want to** quickly distinguish eligible from ineligible deployments visually,  
> **so that** I can select the right deployment in seconds.

### US-5: Demo mode unaffected
> **As a** user exploring PTU Advisor in demo mode,  
> **I want** demo scenarios to use PTU-eligible models,  
> **so that** the full analysis flow works without eligibility issues.

---

## 3. Detailed Design

### 3.1 Eligibility Check Logic

#### Single Source of Truth

The PTU-eligible model list is already defined in `MODEL_CAPACITY_CONFIGS` (in `ptu_advisor/config.py`). The eligibility check reuses the existing `get_model_config()` function — if it returns a config, the model is eligible; if `None`, it's not.

```python
# ptu_advisor/config.py — existing function, no changes needed
def get_model_config(model_name: str) -> Optional[ModelCapacityConfig]:
    model_lower = model_name.lower()
    for key in sorted(MODEL_CAPACITY_CONFIGS, key=len, reverse=True):
        if key in model_lower:
            return MODEL_CAPACITY_CONFIGS[key]
    return None
```

This fuzzy-match approach already handles version suffixes (e.g., `gpt-4o (2024-11-20)` correctly matches `gpt-4o`).

#### Backend Enrichment

Extend the `DeploymentInfo` dataclass and API response to include a `ptu_eligible` boolean:

```python
# ptu_advisor/metrics/models.py
@dataclass
class DeploymentInfo:
    name: str
    model: str
    sku_type: str
    sku_capacity: Optional[int] = None
    created_date: Optional[datetime] = None
    ptu_eligible: bool = False  # NEW — set by discovery layer
```

The discovery layer (`ptu_advisor/discovery.py` → `list_deployments`) or the API server enriches each `DeploymentInfo` with the eligibility flag before returning to the frontend:

```python
from ptu_advisor.config import get_model_config

for deployment in deployments:
    deployment.ptu_eligible = get_model_config(deployment.model) is not None
```

#### Frontend Type

```typescript
// types.ts
export type DeploymentInfo = {
  name: string
  model: string
  sku_type: string
  sku_capacity: number | null
  ptu_eligible: boolean  // NEW
}
```

### 3.2 Frontend UX — Deployment List

#### Visual Design

Each deployment card in the deployment selection fieldset gets updated styling:

| State | Visual Treatment |
|-------|-----------------|
| **PTU Eligible** (default) | Normal styling, radio button enabled, green "PTU Eligible" chip |
| **PTU Eligible** (selected) | Existing `is-selected` blue highlight + green chip |
| **Not Eligible** | Entire card has `opacity: 0.5`, subtle gray overlay. Radio button `disabled`. Red/amber "PTU Not Available" chip. Cursor shows `not-allowed` |

#### Card Layout (Eligible)

```
┌─────────────────────────────────────────────────┐
│ ○  gpt-4o-deployment · gpt-4o                   │
│    SKU: Standard  │  Capacity: 120              │
│    ✓ PTU Eligible                                │
└─────────────────────────────────────────────────┘
```

#### Card Layout (Not Eligible)

```
┌────────────────────────────────────────────────── ┐ (grayed out)
│ ○  embeddings-prod · text-embedding-3-large       │
│    SKU: Standard  │  Capacity: 350               │
│    ⊘ PTU Not Available for this model             │
└───────────────────────────────────────────────────┘
```

#### Tooltip / Hover Message (Not Eligible)

On hover or via an info icon next to the "PTU Not Available" chip:

> **PTU is not available for `text-embedding-3-large`.**  
> Provisioned Throughput Units (PTU) are only supported for select Azure OpenAI chat and reasoning models: GPT-4o, GPT-4.1, GPT-5, o1, o3-mini, o4-mini, and their variants.  
> [Learn more →](https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput)

#### Sorting

Eligible deployments appear **first** in the list, followed by ineligible ones. Within each group, maintain alphabetical order by deployment name.

### 3.3 Edge Case: No Eligible Deployments

If the selected account has deployments but **none** are PTU-eligible, show a dedicated empty state:

```
┌─────────────────────────────────────────────────────────┐
│  ⓘ  No PTU-Eligible Deployments                        │
│                                                         │
│  This account has {N} deployment(s), but none use       │
│  models that support Provisioned Throughput Units.       │
│                                                         │
│  PTU-eligible models: GPT-4o, GPT-4.1, GPT-5,          │
│  o1, o3-mini, o4-mini (and their variants).             │
│                                                         │
│  Deploy a supported model to use PTU Advisor analysis.  │
│  Or switch to Demo Mode to explore the tool.            │
└─────────────────────────────────────────────────────────┘
```

### 3.4 "Analyze" Button Guard

Even if the frontend is manipulated (e.g., via browser DevTools), the backend should also reject analysis requests for non-PTU-eligible models:

- The API `/api/analyze` endpoint validates the deployment model against `get_model_config()` in live mode
- Returns HTTP 422 with a clear error: `"Model '{model}' does not support PTU. Analysis requires a PTU-eligible model."`
- Demo mode is unaffected (demo scenarios always use eligible models)

### 3.5 Demo Mode Behavior

No changes needed for demo mode:
- Demo scenarios already use PTU-eligible models (e.g., `gpt-4o`, `gpt-5`)
- The deployment selector is hidden in demo mode (replaced by "Focus Topic" dropdown)
- The eligibility gate only applies to the live mode deployment list

### 3.6 CSS Additions

```css
/* Ineligible deployment card */
.deployment-option.is-ineligible {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;         /* prevent click-through */
}
.deployment-option.is-ineligible input[type="radio"] {
  pointer-events: none;
}

/* Eligibility chips */
.eligibility-chip {
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.eligibility-chip.eligible {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}
.eligibility-chip.ineligible {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}
```

---

## 4. Data Flow

```
Azure Cognitive Services API
        │
        ▼
list_deployments()  ──►  DeploymentInfo[]
        │                    │
        ▼                    ▼
  get_model_config()   sets .ptu_eligible = True/False
        │
        ▼
  API response: /api/deployments → [{ name, model, ..., ptu_eligible }]
        │
        ▼
  Frontend: sorts eligible first, renders chips, disables ineligible radio buttons
        │
        ▼
  User selects eligible deployment → "Analyze" → /api/analyze (backend re-validates)
```

---

## 5. Files to Modify

| File | Change |
|------|--------|
| `ptu_advisor/metrics/models.py` | Add `ptu_eligible: bool = False` to `DeploymentInfo` |
| `ptu_advisor/api/server.py` | Enrich deployments with eligibility flag in `/api/deployments` endpoint; add guard in `/api/analyze` for live mode |
| `ptu_advisor/discovery.py` | Optionally enrich in `list_deployments()` (alternative to server-side) |
| `frontend/src/types.ts` | Add `ptu_eligible: boolean` to `DeploymentInfo` type |
| `frontend/src/App.tsx` | Sort deployments, add eligibility chips, disable ineligible cards, add empty state for no-eligible case |
| `frontend/src/styles.css` | Add `.is-ineligible`, `.eligibility-chip` styles |
| `tests/test_api_server.py` | Add test for eligibility enrichment and analysis rejection |
| `tests/test_config.py` | Verify `get_model_config()` returns `None` for non-PTU models |

---

## 6. PTU-Eligible Model Reference

Current PTU-eligible models (from `MODEL_CAPACITY_CONFIGS`, as of March 2026):

| Model | Input TPM/PTU | Output Ratio | Global Min PTU | Regional Min PTU |
|-------|--------------|--------------|----------------|------------------|
| gpt-5 | 3,400 | 8x | 15 | 50 |
| gpt-4.1 | 4,750 | 4x | 15 | 50 |
| gpt-4.1-mini | 23,750 | 4x | 15 | 25 |
| gpt-4.1-nano | 59,400 | 4x | 15 | 25 |
| gpt-4o | 2,500 | 3x | 15 | 50 |
| gpt-4o-mini | 37,000 | 3x | 15 | 25 |
| o1 | 3,000 | 4x | 15 | 50 |
| o3-mini | 14,900 | 4x | 15 | 25 |
| o4-mini | 5,400 | 4x | 15 | 25 |

When new models gain PTU support, only `MODEL_CAPACITY_CONFIGS` in `ptu_advisor/config.py` needs updating — the eligibility logic propagates automatically.

---

## 7. Out of Scope

- **Auto-refreshing the eligible model list** from Azure APIs (future: PRD-live-pricing-fetch could extend to model catalog)
- **Converting non-eligible deployments** to eligible models (outside our tool's scope)
- **PTU availability by region** (a deployment may use an eligible model but PTU capacity might not be available in that region — this is a separate feature)
- **Streamlit dashboard** (`ptu_advisor/dashboard/app.py`) — eligibility UX in the legacy dashboard is not in scope; the React frontend is the primary interface

---

## 8. Rollout Plan

### Phase 1 — Backend Enrichment + Frontend Gate (this PR)
- Add `ptu_eligible` to `DeploymentInfo`
- Enrich in API server's deployment endpoint
- Frontend: sort, gray out, disable, chips, empty state
- Backend: validate in `/api/analyze`
- Tests for all paths

### Phase 2 — Refinements (follow-up)
- Add model family grouping in the deployment list (e.g., "GPT-4o family", "Embedding models")
- Consider a "Why?" expandable detail panel for ineligible deployments
- Telemetry: track how often users encounter ineligible-only accounts

---

## 9. Open Questions

| # | Question | Proposed Answer |
|---|----------|----------------|
| 1 | Should we show ineligible deployments at all, or hide them entirely? | Show but grayed out — hiding them is confusing ("where's my deployment?"); showing them with explanation teaches the user about PTU scope |
| 2 | Should the model list be hardcoded or fetched from an API? | Hardcoded in `MODEL_CAPACITY_CONFIGS` for now; fetching from Azure APIs is Phase 2 (PRD-live-pricing-fetch) |
| 3 | What if `get_model_config()` fuzzy match produces a false positive? | The sorted longest-match-first approach minimizes this; edge cases can be reported as bugs |
| 4 | Should we surface PTU-eligible status in the analysis results page too? | Not needed — if the user got to results, the deployment was already validated |
