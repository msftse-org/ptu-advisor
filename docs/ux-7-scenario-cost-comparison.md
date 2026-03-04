# UX Design: 7-Scenario Cost Comparison

> **Feature**: Priority 1, Item #1 — Full Cost Comparison Engine  
> **Date**: February 2026  
> **Status**: Proposal

---

## Current State

Today, the dashboard "The Math" section shows:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  PAYG Monthly    │  │ PTU + Spillover  │  │   Difference    │
│  $12,450         │  │ $8,200           │  │   $4,250/mo     │
│                  │  │                  │  │   Saving w/ PTU  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Problems:**
- Only 2 scenarios compared (PAYG vs 1 hybrid variant)
- Reservation term is a dropdown that recalculates a single number — no side-by-side
- User can't see all commitment options at once
- No break-even point
- No "cheapest option" highlight

---

## Proposed UX: "The Economics" Section

Replace the current "The Math" section with a progressive-disclosure design that shows the right amount of detail at each level.

### Layer 1: Hero Summary (Always visible)

A single-glance answer: "Which option is cheapest for your workload?"

```
┌─────────────────────────────────────────────────────────────┐
│  ⚡ PTU + Spillover (1-Year) saves you $4,250/mo (34%)     │
│     vs Pay-As-You-Go                          [Best for you]│
└─────────────────────────────────────────────────────────────┘
```

**Design Notes:**
- Green accent glow when savings are significant (>10%)
- Yellow for marginal (5-10%)
- Neutral when PAYG wins
- One sentence, no jargon. The rest lives below.

### Layer 2: The Comparison Strip (Always visible)

Three summary cards for the three *categories*. NOT 7 individual cards — that overwhelms.

```
┌──── PAYG ─────────┐  ┌── Full PTU ────────┐  ┌── Hybrid ──────────┐
│  $12,450/mo        │  │  $10,950/mo         │  │  $8,200/mo ✦ BEST  │
│  pay per token     │  │  reserved capacity  │  │  PTU base + overflow│
│  no commitment     │  │  best: 3Y @ $6,025  │  │  best: 1Y @ $8,200 │
│                    │  │                     │  │                     │
│  ● Simple          │  │  ● No throttling    │  │  ● Cost optimized   │
│  ● Scales to zero  │  │  ● Guaranteed SLA   │  │  ● Handles spikes   │
│  ● Higher per-unit │  │  ● Commitment req'd │  │  ● Balanced          │
└────────────────────┘  └─────────────────────┘  └─────────────────────┘
           ↓                      ↓                        ↓
       1 scenario            3 terms                   3 terms
```

**Design Notes:**
- Cards use the existing dark theme (`--bg-card: #1a1a24`)
- "✦ BEST" badge is the accent green (`#00d4aa`) only on the cheapest category
- "best: 3Y @ $6,025" shows the cheapest term *within* that category as a micro-preview
- Clicking a card scrolls to or expands the detail row for that category

### Layer 3: Full 7-Scenario Breakdown (Expandable)

An expander or tab row below the cards with the full side-by-side bar chart + table.

```
┌─ Expand: All 7 Pricing Scenarios ──────────────────────────┐
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  [Grouped Bar Chart]                                 │   │
│  │                                                      │   │
│  │  ████ $12,450   PAYG                                 │   │
│  │  ████████ $10,950   PTU (On-Demand)                  │   │
│  │  ██████ $8,213    PTU (1-Year)                       │   │
│  │  █████ $6,025     PTU (3-Year)                       │   │
│  │  ████████ $9,800    Spillover (On-Demand)            │   │
│  │  ██████ $8,200    Spillover (1-Year) ← BEST          │   │
│  │  █████ $6,850     Spillover (3-Year)                 │   │
│  │                                                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─ Detail Table ─────────────────────────────────────────┐ │
│  │ Scenario          Monthly    Annual    Savings  Commit │ │
│  │ PAYG              $12,450   $149,400    —       None   │ │
│  │ PTU On-Demand     $10,950   $131,400    12%     None   │ │
│  │ PTU 1-Year        $8,213    $98,550     34%     1 yr   │ │
│  │ PTU 3-Year        $6,025    $72,300     52%     3 yr   │ │
│  │ Spillover OD      $9,800    $117,600    21%     None   │ │
│  │ Spillover 1Y ✦    $8,200    $98,400     34%     1 yr   │ │
│  │ Spillover 3Y      $6,850    $82,200     45%     3 yr   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ Break-Even Point ──────────────────────────────────────┐│
│  │ "At your current usage of 45,000 avg TPM, PTU becomes  ││
│  │  cheaper than PAYG above ~32,000 TPM sustained. You     ││
│  │  are 40% above the break-even point."                   ││
│  │                                                         ││
│  │  [Break-even indicator line on a mini chart]            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Interaction Design

### Controls (above the chart)

Keep the existing two dropdowns but **move them into the expander** — the summary cards should work without any user input (defaulting to auto-detected best options).

```
┌─ Configuration ────────────────────────────────────────────┐
│  [Deployment Type ▼]     [Region ▼]     [Custom Pricing ▼] │
│  Global ● DataZone ●     East US        ☐ Override rates    │
│  Regional ●                                                 │
└─────────────────────────────────────────────────────────────┘
```

**Defaults**: Global deployment, East US (multiplier 1.0x). Users change only when needed.

### Baseline Slider (for spillover scenarios)

```
┌─ Spillover Baseline ───────────────────────────────────────┐
│                                                             │
│  PTU covers: ═══════════●════════ 75% of traffic (P75)     │
│              Min(15)   P50      P75      P95    Peak        │
│                                                             │
│  Higher baseline = more PTU cost, less spillover            │
│  Lower baseline  = less PTU cost, more spillover            │
└─────────────────────────────────────────────────────────────┘
```

Currently a dropdown with 3 options. Change to a **slider with 5 stops**: Min, P50, P65, P75, P85. The bar chart updates in real-time as the user slides.

---

## Data Architecture

### New: `CostScenario` dataclass

```python
@dataclass
class CostScenario:
    name: str                    # "PTU (1-Year)"
    category: str                # "ptu" | "payg" | "spillover"
    monthly_cost: float
    annual_cost: float
    commitment_term: str         # "None" | "1 Year" | "3 Years"
    savings_vs_payg_pct: float   # 0.34 = 34%
    ptu_count: Optional[int]
    spillover_pct: Optional[float]
    is_cheapest: bool = False

@dataclass  
class CostComparison:
    scenarios: List[CostScenario]  # All 7
    cheapest: CostScenario
    break_even_tpm: float          # TPM where PTU < PAYG
    current_tpm_vs_breakeven: float  # How far above/below break-even
```

### New: `calculate_all_scenarios()` function

```python
def calculate_all_scenarios(
    tpm_values: List[float],
    model: str,
    deployment_type: str = "global",       # NEW
    region: str = "eastus",                # NEW
    baseline_percentile: float = 75,
    completion_ratio: float = 0.3,
    custom_pricing: Optional[Dict] = None, # NEW
) -> CostComparison:
    """Calculate all 7 pricing scenarios."""
    ...
```

This replaces the current separate `calculate_spillover_cost()` and `calculate_ptu_costs()` functions, which duplicate logic.

---

## Break-Even Visualization

A small inline chart showing the crossover point:

```
Cost ↑
  $  │         ╱ PAYG (linear)
     │        ╱
     │       ╱
     │   ───────── PTU (flat line)
     │  ╱ ← break-even here
     │ ╱      
     │╱       
     └──────────────────→ TPM
          32K   45K(you)
```

- Mark the user's current avg TPM with a vertical dashed line
- Mark the break-even TPM with a crossover point
- Color the area where PTU is cheaper in green

---

## Implementation Approach

### Step 1: Backend — New cost engine module
Create `ptu_advisor/cost/engine.py` with:
- `CostScenario` and `CostComparison` dataclasses
- `calculate_all_scenarios()` that computes all 7 scenarios
- `calculate_break_even()` that finds the crossover TPM
- Region multiplier lookup table
- Deployment type multiplier table

### Step 2: Dashboard — Replace "The Math" section
1. Replace the 3-metric summary with the hero bar + 3 category cards
2. Add the expander with grouped bar chart + detail table
3. Integrate break-even mini chart
4. Move controls (deployment type, region) into the expander

### Step 3: Integrate into HTML report
The `report/generator.py` already has `_estimate_ptu_sizing()` — extend it to produce all 7 scenarios and embed the comparison table in the HTML report.

---

## Why NOT Copy ptucalc.com's Flat Layout

ptucalc.com shows all 7 scenarios at once in a single bar chart with no hierarchy. This has problems:
1. **Cognitive overload** — 7 bars of dollar amounts with no grouping
2. **No quick answer** — user has to mentally compare all bars
3. **No progressive disclosure** — same detail level for first-time and expert users

Our approach: **Hero → Cards → Details** gives every user the answer at their comfort level.

---

## Mobile / Narrow Viewport Considerations

- Hero summary: full width, single line → wraps to two lines on mobile
- 3 category cards: `st.columns(3)` → stack vertically on mobile (Streamlit handles this)
- Bar chart: horizontal bars (not vertical) to avoid x-axis label truncation
- Detail table: scrollable horizontally on narrow screens
