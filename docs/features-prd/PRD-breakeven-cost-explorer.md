# PRD: Break-Even Cost Explorer

> **Version**: 3.4 (Final Audit Fixes)  
> **Date**: March 28, 2026  
> **Author**: PTU Advisor Team  
> **Status**: ✅ Implemented  
> **Replaces**: v1.0 break-even slider, v2.0 interactive break-even slider  
> **Key change (v3.4)**: Distinct "PTU always cheaper" / "always more expensive" break-even messages, break-even annotation shows monthly cost, `max_search_tpm` param, avg TPM visual reference help text, CV > 1.5 spiky usage warning

---

## 1. Executive Summary

### Problem Statement

The v1.0 break-even chart answers "how much PTU should I buy?" by sliding PTU size along the X-axis. But once a user selects a PTU amount (e.g., 15 PTU), the real question becomes:

> **"Given I'm committing to 15 PTU, how much traffic do I need to justify that commitment?"**

The current chart varies PTU size on X while keeping traffic implicit. This inverts the real-world decision: you commit to a fixed PTU amount, and then traffic happens. Users cannot see whether their actual (or projected) traffic level makes their selected PTU commitment worthwhile.

### Proposed Solution

Flip the chart's semantics: **X-axis = actual sustained TPM (traffic), PTU commitment = fixed (from slider)**. The chart shows:

- **PAYG line**: cost if all traffic at that TPM goes through PAYG (rises linearly).
- **PTU + Spillover line**: fixed PTU cost for the selected slider value + PAYG overflow for traffic above PTU capacity (flat then rising).
- **Break-even marker**: the traffic level where PTU pays for itself.
- **"Your avg TPM" marker**: where the user's actual traffic sits relative to break-even.
- **Commitment safety signal**: an operational-fit summary based on full time-series behavior, not only average TPM. It captures how often traffic fits inside PTU capacity, how much workload spills to PAYG, and whether the monthly savings margin is large enough to justify commitment risk.

When the user moves the PTU slider, the PTU+Spillover line shifts (higher fixed cost, but later onset of spillover), and break-even moves right. This gives an intuitive, interactive answer to: "If I buy X PTU, do I have enough traffic to justify it?"

The recommendation should therefore be read in **two layers**:

1. **Economic break-even** — does the selected PTU save money versus PAYG?
2. **Operational fit** — is that saving robust enough given spillover, burstiness, and margin above break-even?

### Success Criteria

| KPI | Target |
|---|---|
| User can identify the traffic level that justifies their selected PTU | 100% of test users in usability review |
| Cost figures update within 200ms of slider movement | Measured via frontend re-render |
| Break-even TPM matches manual calculation | ± 2% tolerance |
| Time to answer "does my traffic justify this PTU commitment?" | < 10 seconds (usability target) |
| Users correctly interpret the flat→rising PTU+Spillover shape | ≥ 90% in usability review |
| Users can distinguish "PTU saves money" from "PTU is a safe commitment" | ≥ 90% in usability review |

---

## 2. User Experience & Functionality

### 2.1 What It Replaces

**v1.0 Break-Even Chart** — X-axis was "Baseline TPM" (effectively varying PTU size). The user couldn't answer: "I've picked 15 PTU — does my traffic justify it?"

### 2.2 Core Concept: Fixed PTU, Varying Traffic

The mental model flips from **"how much PTU?"** to **"is my traffic enough?"**

| Aspect | v1.0 (Old) | v2.0 (New) |
|---|---|---|
| **X-axis** | Baseline TPM (varies PTU size) | Sustained TPM (actual traffic level) |
| **PAYG line** | PAYG cost at that baseline | PAYG cost at that traffic level |
| **PTU line** | PTU sized to X + spillover | **Fixed** PTU (from slider) + spillover at that traffic |
| **Break-even** | "Buy PTU above this size" | "Your 15 PTU pays for itself when traffic exceeds X TPM" |
| **Slider controls** | What % of traffic PTU covers | How many PTU units you're committing to |

This matches the real-world decision flow: you commit to a fixed PTU amount, then traffic varies over time.

### 2.3 What It Looks Like

```
┌──────────────────────────────────────────────────────────────────────┐
│  Cost Explorer — "Does my traffic justify 15 PTU?"          [?] help │
│                                                                      │
│  Cost/mo                                                             │
│  $15K ┤                              ╱ PAYG                          │
│       │                            ╱                                 │
│  $12K ┤                          ╱                                   │
│       │                        ╱          PTU+Spill                  │
│  $9K  ┤                      ╱          ╱ (rising: spillover)        │
│       │                    ╱          ╱                               │
│  $6K  ┤                  ╱        ╳ ← BREAK-EVEN (38K TPM)          │
│       │                ╱      ╱                                      │
│  $3K  ┤──────────────╱──────── (flat: all fits in PTU)               │
│       │  PTU fixed ╱                                                 │
│  $0   ┼──────────╱──────────────────────────────────→ Sustained TPM  │
│       0    15K   25K  38K      55K      75K     95K                  │
│                        ↑               ↑                             │
│                   break-even      your avg TPM                       │
│                                                                      │
│  PTU Commitment  ═══════●══════════════════════════                   │
│  Min(15)    25    50    75    100    150    200   PTU units           │
│                   ↑                                                  │
│              Currently: 50 PTU (125K TPM capacity)                   │
│                                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────────────┐  │
│  │ PAYG       │  │ PTU+Spill  │  │ Your avg TPM is 47% above     │  │
│  │ $12,450/mo │  │ $8,200/mo  │  │ break-even. ✓ PTU is saving   │  │
│  │ (at avg)   │  │ (at avg)   │  │ you $4,250/mo (34%).          │  │
│  └────────────┘  └────────────┘  └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.4 Component Breakdown

The control has **5 layers** stacked vertically:

#### Layer A: The Cost Curve Chart

Two lines plotted against **"Sustained TPM"** (actual traffic) on the X-axis:

1. **PAYG line** (blue, dashed) — Straight line rising linearly:  
   `PAYG cost = sustained_tpm × 43,200 / 1M × blended_rate`  
   Represents what you'd pay if all traffic at that level went through PAYG.

2. **PTU + Spillover line** (green, solid) — Has a **distinctive two-phase shape**:
   - **Flat phase** (left): When sustained TPM ≤ PTU capacity, all traffic fits within the committed PTU. Cost = PTU fixed cost only. The line is horizontal.
    - **Rising phase** (right): When sustained TPM > PTU capacity, excess traffic spills to PAYG. Cost = PTU fixed + overflow × PAYG rate. The line rises with the **same marginal slope as PAYG** because every incremental token above PTU capacity is charged at the same PAYG rate.
   - **Inflection point**: Where the line transitions from flat to rising = the PTU capacity in TPM.

3. **Break-even marker** — A vertical dashed line where the two lines cross. This answers: **"At what traffic level does my selected PTU commitment start saving money vs pure PAYG?"**

4. **"Your avg TPM" marker** — A vertical line at the user's actual average TPM, showing how far above or below break-even their real traffic is.

**Key visual insight**: Moving the PTU slider up shifts the flat portion higher (more fixed cost) but extends it further right (more capacity before spillover), and pushes break-even right. The user can visually explore the tradeoff between commitment size and required traffic.

#### Layer B: The PTU Commitment Slider

A slider below the chart controlling **PTU units** directly (not percentile):

- **Range**: min PTU (deployment type minimum) to a computed max (P99 × 1.3 worth of PTU)
- **Step**: deployment type increment (5 for Global/Data Zone, 50 for Regional)
- **Default**: the **lowest-cost viable** PTU level that still saves > 5%, so the first view starts from the clearest economic baseline
- **Display**: Shows PTU units and the corresponding TPM capacity  
  e.g., "50 PTU → 125,000 TPM capacity"
- **Headroom helper**: when a larger PTU level still clears the savings floor, show a compact secondary helper such as `Explore headroom: up to 45 PTU still saves > 5%`, with a one-click action to jump there. If the user is exploring a non-default baseline, show a `Reset to recommended` action.

When the slider moves:
1. PTU+Spillover line redraws (flat level shifts, inflection point moves)
2. Break-even marker shifts
3. Cost summary and verdict update
4. "Your avg TPM" marker stays fixed (traffic doesn't change)

#### Layer C: Cost Summary Strip

Three inline metrics evaluated **at the user's actual average TPM**:

| PAYG Monthly (at avg TPM) | PTU + Spillover (at avg TPM) | Verdict |
|---|---|---|
| $12,450 | $8,200 | ✓ 34% saving / PTU saves $4,250/mo |

These update immediately when the slider moves because the PTU component changes.

#### Layer D: Break-Even Callout

A contextual banner showing the user's position relative to break-even:

```
┌──────────────────────────────────────────────────────────┐
│ ⚡ Break-even for 50 PTU: 38,000 TPM                     │
│   Your avg traffic (56,000 TPM) is 47% above break-even.│
│   ✓ PTU is cost-effective at your current traffic level. │
└──────────────────────────────────────────────────────────┘
```

- **Green** when avg TPM > break-even TPM (PTU justified)
- **Yellow** when within ±10% of break-even (marginal — small traffic changes can flip the decision)
- **Blue** when avg TPM < break-even (PAYG is cheaper — user is over-committing PTU)

The callout explicitly names the selected PTU amount so the user sees the direct connection between their slider choice and the traffic threshold.

The callout is intentionally **directional**, not the whole recommendation. Average TPM is useful for orientation on the chart, but the final decision should be grounded in the full monthly workload shape, realized hybrid cost, and commitment-safety metrics. The banner should therefore use language like **"economic signal favors PTU"** or **"economic signal favors PAYG"**, not present itself as the final recommendation by itself.

#### Layer E: Commitment Safety Strip

Below the break-even callout, add a compact strip that answers: **"Even if PTU saves money, how safe is this commitment?"**

Recommended fields:

| Savings Margin | Spillover % | Capacity Coverage | Safety Verdict |
|---|---|---|---|
| 12% | 8% | 91% of intervals fit in PTU | Safe |

- **Savings Margin**: `(payg_monthly - hybrid_monthly) / payg_monthly`
- **Spillover %**: percent of intervals with traffic above PTU capacity, or percent of monthly tokens that spill over
- **Capacity Coverage**: percent of observed intervals where `tpm ≤ ptu_capacity_tpm`
- **Safety Verdict**:
    - **Safe**: strong savings and low spillover
    - **Efficient but Risky**: savings exist, but margin is thin or spillover is high
    - **Not Justified**: PTU does not save money at the selected commitment

This makes the explorer more profound than a pure break-even chart: it separates **"economically favorable"** from **"operationally robust."**

### 2.5 User Stories

#### US-1: Understand If Selected PTU Is Justified by Traffic

> As a **FinOps engineer**, I have already picked a PTU size using the slider. I want to see the minimum traffic level that justifies that commitment so that I know whether my real usage makes it worthwhile.

**Acceptance Criteria:**
- [ ] Break-even TPM is calculated for the selected PTU units and displayed as a vertical marker
- [ ] Break-even annotation shows the traffic TPM value and corresponding monthly cost
- [ ] Break-even recalculates when PTU slider moves or reservation term changes
- [ ] If break-even doesn't exist (PTU always cheaper or always more expensive at any traffic), a clear message explains why

#### US-2: Explore PTU Commitment Sizes Interactively

> As a **Cloud Architect**, I want to drag a slider to try different PTU commitment sizes so that I can see how the break-even traffic threshold and cost structure change.

**Acceptance Criteria:**
- [ ] Slider controls PTU units directly (not percentile), with correct increment per deployment type
- [ ] Chart redraws in < 300ms: flat portion shifts, inflection point moves, break-even moves
- [ ] PTU units, TPM capacity, spillover %, and monthly cost update in the summary strip
- [ ] The "Your avg TPM" marker stays fixed while the PTU+Spillover line moves around it

#### US-3: Assess Risk Relative to Break-Even

> As a **Platform Team Lead**, I want to see how far above or below the break-even traffic level my actual usage is so that I can assess the risk of over- or under-committing PTU.

**Acceptance Criteria:**
- [ ] "Your avg TPM" marker on the chart at the user's actual average TPM
- [ ] Callout shows distance from break-even as a percentage and names the selected PTU amount
- [ ] Color coding: green (traffic above break-even → PTU justified), yellow (near → marginal), blue (below → over-committed)
- [ ] If traffic is below break-even, callout explicitly says "PAYG is cheaper at your current traffic for X PTU"

#### US-4: Distinguish Savings From Commitment Safety

> As a **FinOps engineer or platform owner**, I want PTU Advisor to show not only whether PTU saves money, but also whether the commitment is operationally safe for my workload shape, so I can avoid over-committing based on a misleading monthly average.

**Acceptance Criteria:**
- [ ] Recommendation is based on full monthly hybrid cost, not solely on the avg TPM marker
- [ ] A separate safety strip shows savings margin, spillover %, and capacity coverage for the selected PTU
- [ ] The UI can express three distinct states: `Safe`, `Efficient but Risky`, `Not Justified`
- [ ] A workload can be shown as economically favorable but operationally risky when savings are positive but spillover or volatility remain high
- [ ] Help text explains that avg TPM is a visual reference, not the sole decision variable

#### US-5: Compare Reservation Terms Effect on Break-Even

> As a **FinOps engineer**, I want to see how break-even shifts between on-demand, monthly, and 1-year reservation terms so that I can evaluate commitment risk vs savings.

**Acceptance Criteria:**
- [ ] Reservation term selector above the chart
- [ ] When term changes, PTU+Spillover line redraws with updated fixed cost and break-even shifts
- [ ] Break-even annotation updates to show the new crossover traffic level
- [ ] Lower discount = higher PTU fixed cost = break-even moves right (need more traffic to justify)

#### US-6: Visual Understanding of the Flat→Rising PTU Shape

> As any user, I want to intuitively understand why the PTU+Spillover line has a flat portion and then rises so that the chart makes sense without reading documentation.

**Acceptance Criteria:**
- [ ] Tooltip on the flat portion explains "All traffic fits within your X PTU — no spillover"
- [ ] Tooltip on the rising portion explains "Traffic exceeds PTU capacity — overflow goes to PAYG"
- [ ] The inflection point (PTU capacity in TPM) is visually marked or annotated
- [ ] Help icon [?] links to a one-paragraph explanation of the hybrid model

### Non-Goals

- **Multiple models on one chart** — This view is for a single deployment/model
- **Varying PTU size on X-axis** — The old v1.0 approach; PTU is now fixed by the slider
- **Custom pricing overrides** — Deferred (Phase 2, item #11)

---

## 3. Technical Specifications

### 3.1 Economic Break-Even Calculation (v2 — Fixed PTU, Varying Traffic)

The break-even point is the sustained TPM where:  
`PAYG_cost(tpm) = PTU_fixed_cost(selected_ptu) + spillover_cost(tpm, selected_ptu)`

For traffic ≤ PTU capacity, spillover is zero, so:  
`PAYG_cost(tpm) = PTU_fixed_cost` (constant)

For traffic > PTU capacity:  
`PAYG_cost(tpm) = PTU_fixed_cost + (tpm - ptu_capacity) × 43,200 / 1M × blended_rate`

```python
def calculate_break_even_for_fixed_ptu(
    selected_ptu: int,
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,  # $/1M tokens
    reservation_discount: float = 1.0,
    max_search_tpm: float = 200_000,
) -> Optional[float]:
    """
    Find the sustained TPM where PTU+spillover cost equals PAYG cost,
    for a FIXED PTU commitment.

    PAYG cost   = tpm × 43,200 / 1M × blended_rate
    PTU+spill   = selected_ptu × hourly × 720 × discount
                  + max(0, tpm - ptu_capacity) × 43,200 / 1M × blended_rate

    The PTU+spillover line has two phases:
      - Flat (tpm ≤ capacity): cost = PTU fixed only
      - Rising (tpm > capacity): cost = PTU fixed + overflow PAYG

    Break-even is in the FLAT phase when PAYG line crosses the flat level.
    If PTU capacity is large enough, break-even may be within the flat zone.

    Returns the break-even TPM, or None if lines don't cross.
    """
    ptu_capacity_tpm = selected_ptu * ptu_capacity_per_unit
    discount = reservation_discount if reservation_discount < 1.0 else 1.0
    ptu_fixed = selected_ptu * ptu_hourly_rate * 720 * discount
    minutes_per_month = 43_200

    # In the flat phase: PAYG = tpm × 43200 / 1M × rate,  PTU = ptu_fixed
    # Cross when: tpm × 43200 / 1M × rate = ptu_fixed
    # → tpm = ptu_fixed × 1M / (43200 × rate)
    if payg_blended_rate > 0:
        flat_break_even = ptu_fixed * 1_000_000 / (minutes_per_month * payg_blended_rate)
    else:
        return None

    if flat_break_even <= ptu_capacity_tpm:
        # Break-even occurs while all traffic still fits in PTU (flat zone)
        return flat_break_even

    # In the rising phase (tpm > capacity):
    # PAYG = tpm × C  where C = 43200/1M × rate
    # PTU+spill = ptu_fixed + (tpm - cap) × C = ptu_fixed - cap×C + tpm×C
    # Cross: tpm×C = ptu_fixed - cap×C + tpm×C → never (same slope)
    #
    # Once in the rising phase, both lines have the SAME slope (blended_rate
    # per TPM) — they are parallel and never cross. If break-even wasn't
    # reached in the flat phase, PTU is always more expensive.
    return None
```

**Key insight (v2)**: Because the spillover phase has the same per-TPM rate as PAYG (both charge blended_rate for marginal tokens), the two lines are **parallel** once spillover begins. This means:

- **Break-even can only occur in the flat phase** — where PTU absorbs all traffic.
- **Break-even = PTU fixed cost ÷ PAYG marginal rate** — a simple division.
- If the break-even TPM exceeds PTU capacity, the lines never cross and PTU is always more expensive for that commitment level. The user should reduce PTU or the selected PTU is oversized.

This is much simpler than v1.0's step-function sweep and gives an **exact analytical solution**.

### 3.1.1 Operational Fit / Commitment Safety

The break-even formula above should remain the economic core. However, the final recommendation must not be reduced to:

> `avg_tpm > break_even_tpm`

That comparison is useful for orientation, but it hides workload volatility. The tool already computes hybrid cost from the full observed TPM series, so the recommendation layer should use additional metrics derived from the same series.

Suggested operational-fit metrics:

```python
capacity_coverage_pct = 100 * count(tpm <= ptu_capacity_tpm) / count(tpm_values)
spillover_interval_pct = 100 * count(tpm > ptu_capacity_tpm) / count(tpm_values)
savings_margin_pct = 100 * (payg_total - hybrid_total) / payg_total
```

Suggested safety classification:

```python
if savings_margin_pct <= 0:
    safety_verdict = "not_justified"
elif savings_margin_pct < 5 or spillover_interval_pct > 25 or capacity_coverage_pct < 75:
    safety_verdict = "efficient_but_risky"
else:
    safety_verdict = "safe"
```

These thresholds are product defaults, not hard finance rules. The important design point is that the explorer presents **two truths at once**:

- **Economic truth**: where fixed PTU breaks even versus PAYG
- **Operational truth**: how reliably the selected PTU covers the actual workload

This keeps the chart mathematically simple while making the recommendation materially stronger.

### 3.2 Cost Curve Data Generation (v2)

For the chart, pre-compute costs at sample traffic levels:

```python
def generate_cost_curves_fixed_ptu(
    selected_ptu: int,
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,
    reservation_discount: float = 1.0,
    max_tpm: float = 200_000,
    num_points: int = 200,
) -> pd.DataFrame:
    """
    Generate PAYG and PTU+Spillover cost curves for FIXED PTU charting.

    X-axis: sustained TPM (traffic level, NOT PTU size).
    PTU commitment is fixed by `selected_ptu`.

    Returns DataFrame with columns:
        sustained_tpm, payg_monthly, ptu_spill_monthly
    """
    discount = reservation_discount if reservation_discount < 1.0 else 1.0
    ptu_fixed = selected_ptu * ptu_hourly_rate * 720 * discount
    ptu_capacity_tpm = selected_ptu * ptu_capacity_per_unit
    minutes_per_month = 43_200
    rate_per_token = payg_blended_rate / 1_000_000

    sample_tpms = np.linspace(0, max_tpm, num_points)

    rows = []
    for tpm in sample_tpms:
        # PAYG: linear
        payg = tpm * minutes_per_month * rate_per_token

        # PTU+Spillover: flat then rising
        overflow_tpm = max(0.0, tpm - ptu_capacity_tpm)
        spillover = overflow_tpm * minutes_per_month * rate_per_token
        hybrid = ptu_fixed + spillover

        rows.append({
            "sustained_tpm": tpm,
            "payg_monthly": payg,
            "ptu_spill_monthly": hybrid,
        })

    return pd.DataFrame(rows)
```

**Shape of the PTU+Spillover line**:
- `tpm ≤ ptu_capacity_tpm` → `hybrid = ptu_fixed` (horizontal line)
- `tpm > ptu_capacity_tpm` → `hybrid = ptu_fixed + (tpm - cap) × rate` (rising, same slope as PAYG)

### 3.3 Chart Construction

```
The chart shows two lines against "Sustained TPM" on X:

1. PAYG (blue, dashed) — starts at origin, rises linearly.

2. PTU + Spillover (green, solid) — two-phase shape:
   - Flat segment from 0 to PTU capacity TPM (all traffic absorbed).
   - Rising segment from PTU capacity onward (parallel to PAYG, offset by PTU fixed cost).

3. Break-even marker (gold) — vertical line where PAYG crosses the flat PTU level.
   If break-even > PTU capacity, show "No break-even — reduce PTU or increase discount."

4. "Your avg TPM" marker (white) — user's actual avg TPM, stays fixed as slider moves.

5. PTU capacity marker (subtle) — vertical annotation at the inflection point
   where the PTU line goes from flat to rising, labeled "PTU capacity: X TPM".

6. Savings zone — filled area between PAYG and PTU lines where PTU is cheaper
   (from break-even rightward until spillover phase makes them parallel).
```

When the user moves the PTU slider:
- The flat level shifts up or down (more/fewer PTU = higher/lower fixed cost)
- The inflection point moves left or right (more PTU = later spillover onset)
- Break-even shifts (higher fixed cost = need more traffic to justify)
- The "Your avg TPM" marker does NOT move — traffic is fixed, commitment changes

### 3.4 Slider Integration

The slider controls PTU units directly:

```
PTU Commitment:  ═══════════●═══════════════════
                 15    50   75   100  150  200
                             ↑
                    Currently: 75 PTU (187,500 TPM)
```

- **Range**: min_ptu to max_ptu (P99 × 1.3 / capacity_per_ptu, rounded up)
- **Step**: deployment type increment (5 for Global/Data Zone, 50 for Regional)
- **Default**: **recommendation-aware** (see §3.5)
- **Display**: Shows both PTU units and the resulting TPM capacity

### 3.5 Recommendation-Aware Default PTU

The slider's initial position is designed to answer the user's most natural question based on the analysis outcome:

| Recommendation | Default PTU | Rationale |
|---|---|---|
| **PTU Recommended** | **Lowest-cost PTU baseline** that still saves > 5% | Shows the most economically defensible starting point before users explore larger commitments |
| **Borderline** | **Lowest-cost PTU baseline** that still saves > 5%, if one exists; otherwise minimum PTU | Starts at the clearest economic option rather than the largest still-viable commitment |
| **PTU NOT Recommended** | **Minimum** PTU (e.g., 15 for Global) | Shows the break-even threshold for the smallest commitment, so users see what traffic increase would justify PTU |

**Why "lowest-cost viable" not "maximum viable"?**  
The "maximum PTU that still saves > 5%" policy is useful for headroom exploration, but it is not the clearest first view. Users first need to understand the economically sensible baseline for their current workload. Starting from the **lowest-cost viable** commitment makes the initial explorer state easier to explain and keeps the chart, cost summary, and recommendation aligned. Users can still move the slider upward to explore headroom.

The backend should expose both the **recommended default baseline** and the **maximum viable baseline** so the UI can present this headroom helper without recomputing sweep logic client-side.

**Why min PTU when not recommended?**  
When PTU isn't justified, starting at min PTU produces the most useful break-even chart: the PAYG line and PTU+Spillover line with the smallest possible commitment. The break-even marker shows exactly how much more traffic is needed before even the cheapest PTU makes sense. This directly answers: "what would it take for PTU to be worth it?"

#### Algorithm

```python
# Sweep from min_ptu to P99 × 1.3 ceiling
default_baseline_ptu = min_ptu  # fallback (PTU not recommended)

if payg_total > 0 and tpm_values:
    sweep_ceiling = ceil(percentile(tpm_values, 99) * 1.3 / ptu_capacity)
    sweep_ceiling = snap_up(sweep_ceiling, ptu_increment)
    
    best_positive_ptu = None
    best_positive_hybrid = inf
    for candidate_ptu in range(min_ptu, sweep_ceiling + 1, ptu_increment):
        savings_pct = compute_savings(candidate_ptu, ...)
        hybrid_cost = compute_hybrid_cost(candidate_ptu, ...)
        if savings_pct > 5 and hybrid_cost < best_positive_hybrid:
            best_positive_ptu = candidate_ptu
            best_positive_hybrid = hybrid_cost
    
    if best_positive_ptu is not None:
        default_baseline_ptu = best_positive_ptu
    # else: no PTU saves > 5% → keep min_ptu
```

**Key properties:**
- Single linear sweep (no break-even dependency for the default)
- Always converges (bounded by P99 × 1.3)
- Monotonic: as PTU increases, savings % eventually drops below 5%, so the last > 5% candidate is the max viable PTU
- Works for all recommendation outcomes without branching on recommendation state

---

## 4. Architecture

### File Changes

| File | Change |
|---|---|
| `dashboard/app.py` | Replace baseline dropdown (lines ~1420-1456) with slider + Plotly chart. Add `create_breakeven_chart()` and `calculate_break_even()` calls. |
| `cost/engine.py` (NEW, from main PRD) | Add `calculate_break_even()` and `generate_cost_curves()` functions. If `cost/engine.py` isn't created yet, add to `dashboard/app.py` as local functions. |

**No new dependencies** — Plotly and numpy are already imported in the dashboard.

### Data Flow

```
tpm_values (from metrics)
    │
    ├──→ generate_cost_curves() ──→ Plotly chart (static, cached)
    │
    ├──→ calculate_break_even() ──→ break-even TPM marker
    │
    └──→ slider (baseline_pctl) ──→ calculate_spillover_cost() ──→ summary metrics
                                          │
                                          └──→ chart annotation (slider position indicator)
```

**Performance**: The cost curves and break-even are computed once (Streamlit caching). Only the spillover cost and annotations recalculate on slider move.

---

## 5. Edge Cases

| Scenario | Behavior |
|---|---|
| **Break-even doesn't exist** (PTU always more expensive) | No break-even marker. Callout shows "At your usage level, PAYG is more cost-effective for all baseline sizes." Chart still shows both cost lines. |
| **Break-even doesn't exist** (PTU always cheaper) | Callout shows "PTU is cheaper than PAYG at all usage levels." Green fill covers entire chart. |
| **Very low usage** (avg TPM < min PTU capacity) | Break-even will be very high. Callout: "Your usage is well below the minimum PTU capacity. PAYG is recommended." |
| **Very spiky usage** (CV > 1.5) | Spillover line will be steep. Add a note: "High usage variance means spillover costs remain significant even at high baselines." |
| **Slider at 0** (minimum PTU) | Use 15 PTU minimum. Show most tokens spilling to PAYG. |
| **Slider at 95** (near-peak) | Almost no spillover. Cost is nearly all PTU fixed. |
| **Reservation term change** | Entire chart redraws with new PTU line. Break-even shifts left (cheaper PTU = lower break-even). |

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Slider feels laggy** | Poor UX if costs take >500ms to update | Cache cost curves (static). Only recompute spillover cost on slide (fast). |
| **Break-even math is confusing** | Users don't understand what the crossover means | Add a plain-English callout (Layer D) and a tooltip on the marker itself. |
| **Chart is too complex** | Too many lines/markers overwhelm the user | Start with 2 lines + 2 markers only. Savings fill zone is optional enhancement. |
| **Plotly chart height on mobile** | Chart may be too small to read | Set `height=350` minimum, use horizontal orientation for mobile. |

---

## 7. Implementation Status

All core functionality is implemented in the React frontend + FastAPI backend.

### ✅ Implemented (v3.0)

| Feature | Location |
|---|---|
| `calculate_break_even_for_fixed_ptu()` — analytical break-even | `ptu_advisor/cost/calculator.py` |
| `generate_cost_curves_fixed_ptu()` — PAYG vs PTU+Spillover curve data | `ptu_advisor/cost/calculator.py` |
| ECharts `CostCurveChart` — 2-line chart + break-even + avg TPM markers | `frontend/src/charts/CostCurveChart.tsx` |
| PTU slider (range input, min/max/step from API) | `frontend/src/App.tsx` |
| Cost summary strip (PAYG / PTU+Spill / Verdict) | `frontend/src/App.tsx` |
| Break-even callout banner (green/yellow/blue) | `frontend/src/App.tsx` |
| Recommendation-aware default PTU selection | `ptu_advisor/api/server.py` |
| PTU Calculator (standalone, client-side) | `frontend/src/App.tsx` |

### ✅ Implemented (v3.2 — Gap Fixes)

| Feature | Location | Gap # |
|---|---|---|
| Unit tests for v2 fixed-PTU functions (26 tests with REQ-* traceability) | `tests/test_cost_calculator.py` | Gap 1 |
| Safety verdict thresholds aligned to PRD (`savings < 5%`, `spillover > 25%`, `coverage < 75%`) | `ptu_advisor/api/server.py:636-641` | Gap 2 |
| Safety verdict strings aligned to PRD snake_case format (`safe`, `efficient_but_risky`, `not_justified`) | `ptu_advisor/api/server.py`, `frontend/src/types.ts`, `frontend/src/App.tsx` | Audit Gap 2 |
| Savings fill zone (green shaded area between PAYG and PTU lines where PTU is cheaper) | `frontend/src/charts/CostCurveChart.tsx` (custom series), `frontend/src/charts/echarts-setup.ts` | Gap 3 |
| Help icon `[?]` with collapsible hybrid model explanation | `frontend/src/App.tsx` (WidgetHeader `helpContent` prop), `frontend/src/styles.css` | Gap 4 |
| Observability events (`assumption_changed`, `cost_recalculated`, `break_even_marker_rendered`, `break_even_unavailable`) | `frontend/src/telemetry.ts`, `frontend/src/App.tsx` | Gap 5 |

### ✅ Implemented (v3.4 — Final Audit Fixes)

| Feature | Location | Gap # |
|---|---|---|
| Avg TPM marker white (not purple) | `frontend/src/charts/CostCurveChart.tsx` | P1 |
| Cost summary savings % alongside amount | `frontend/src/App.tsx` (differenceSummary) | P2 |
| Break-even annotation shows monthly cost | `frontend/src/charts/CostCurveChart.tsx` (breakEvenCost prop), `frontend/src/App.tsx` | P3 |
| Rising-portion tooltip expanded to PRD US-6 wording | `frontend/src/charts/CostCurveChart.tsx` | P4 |
| Distinct "PTU always cheaper" vs "always more expensive" messages | `ptu_advisor/api/server.py`, `frontend/src/App.tsx`, `frontend/src/types.ts` (break_even_reason field) | P5/M2 |
| "Break-even doesn't exist" wording aligned to PRD §5 | `ptu_advisor/api/server.py`, `frontend/src/App.tsx` | P6 |
| `max_search_tpm` param added to `calculate_break_even_for_fixed_ptu()` | `ptu_advisor/cost/calculator.py` | P7 |
| 4 metric cards (PAYG, PTU+Spill, Difference with %, Break-even TPM) — extends PRD's 3-card spec with useful 4th card | `frontend/src/App.tsx` | P8 |
| "Avg TPM is a visual reference" added to help panel | `frontend/src/App.tsx` (WidgetHeader helpContent) | M1 |
| "Very spiky usage" (CV > 1.5) warning in break-even context | `ptu_advisor/api/server.py`, `frontend/src/App.tsx` | M3 |

### Future Enhancements

- Multi-reservation-term overlay (show all 3 terms as faded lines)
- Custom pricing overrides integration (from PRD-live-pricing-fetch)

---

## 8. Requirement IDs & Traceability

| Requirement ID | Description | Primary Files | Test Coverage | KPI |
|---|---|---|---|---|
| `REQ-UX-101` | Break-even marker visible and interpretable | `frontend/src/charts/CostCurveChart.tsx`, `frontend/src/App.tsx` | `tests/test_cost_calculator.py::TestBreakEvenForFixedPtu` | Time-to-understand |
| `REQ-COST-102` | Break-even TPM correctness within tolerance | `ptu_advisor/cost/calculator.py` | `tests/test_cost_calculator.py::TestBreakEvenForFixedPtu` (12 tests) | Accuracy |
| `REQ-UX-103` | Slider updates cost outputs in near real-time | `frontend/src/App.tsx` | `frontend/src/ui-enhancements.test.tsx` | Recalc latency |
| `REQ-OBS-104` | Slider interaction telemetry emitted | `frontend/src/telemetry.ts`, `frontend/src/App.tsx` | Telemetry events verified in test console output | Interaction analytics |
| `REQ-UX-105` | Position-vs-break-even callout clarity | `frontend/src/App.tsx` | `frontend/src/ui-enhancements.test.tsx::Break-even callout` | Usability |

## 9. Performance Budgets

| Interaction | Target | Measurement |
|---|---|---|
| Slider change to updated curve + summary | ≤ 250ms p95 | `ui.chart.interaction_ms` |
| Reservation term change to full redraw | ≤ 500ms p95 | `ui.cost.recalc_ms` |

## 10. Observability Plan

> **Status**: ✅ Implemented in `frontend/src/telemetry.ts` (v3.2)

Events are emitted as `ptu:telemetry` CustomEvents on `window` and logged to `console.debug` in dev mode. External analytics (Application Insights, PostHog, etc.) can subscribe via `window.addEventListener('ptu:telemetry', handler)`.

Required events (all implemented):

- `assumption_changed` — emitted when reservation term, PTU slider, region, deployment type, granularity, or throttle toggle changes. Includes `changed_field`, `old_value`, `new_value`, `reservation_term`, `baseline_ptu`.
- `cost_recalculated` — emitted after each analysis response. Includes `payg_monthly`, `hybrid_monthly`, `savings`, `savings_pct`, `baseline_ptu`, `reservation_term`.
- `break_even_marker_rendered` — emitted when break-even exists. Includes `break_even_tpm`, `avg_tpm`, `distance_pct`, `tone`.
- `break_even_unavailable` — emitted when break-even is null. Includes `selected_ptu`, `reason`.

Required dimensions (all attached to every event):

- `policy_version` — currently `"v3.1"` (cost model version)
- `recommendation` — `"ptu_recommended"` | `"ptu_not_recommended"` | `"borderline"`
- `model_name` — e.g. `"gpt-4o"`
- `deployment_type` — `"global"` | `"data_zone"` | `"regional"`

## 11. Definition of Done (Feature)

- [x] `REQ-*` requirements mapped to automated tests (Gap 1: 26 tests in `test_cost_calculator.py`)
- [x] Break-even correctness validated against manual baseline cases (12 unit tests with edge cases)
- [ ] Interaction latency budgets recorded (p50/p95)
- [x] Tooltip and copy reviewed for plain-language clarity (Gap 4: help panel added)
- [x] No markdown formatting artifacts in rendered narrative text
- [ ] Rollback path documented (fallback to static baseline mode)
- [x] Safety verdict thresholds match PRD spec: `savings < 5%`, `spillover > 25%`, `coverage < 75%` (Gap 2)
- [x] Savings fill zone renders between PAYG and PTU lines (Gap 3)
- [x] Observability events emitted for all 4 required events (Gap 5)
