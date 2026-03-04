# PRD: Interactive Break-Even Slider

> **Version**: 1.0  
> **Date**: February 9, 2026  
> **Author**: PTU Advisor Team  
> **Replaces**: The current "PTU Baseline Sizing" dropdown in the dashboard

---

## 1. Executive Summary

### Problem Statement

The current PTU Baseline Sizing control is a dropdown with 3 preset options (Min PTU, P50, P75). Users cannot see **where the break-even point is** between PAYG and PTU, so they're blindly picking a baseline without understanding the financial crossover. The most critical question — "at what usage level does PTU start saving me money?" — goes unanswered.

### Proposed Solution

Replace the dropdown with an **interactive chart + slider** that visualizes the full cost curve. The user drags a baseline handle along their TPM distribution, while the chart shows two overlaid cost lines (PAYG vs PTU+Spillover). A prominent **break-even marker** shows exactly where PTU becomes cheaper. As the user moves the slider, costs update in real-time.

### Success Criteria

| KPI | Target |
|---|---|
| User can identify break-even point without manual calculation | 100% of test users in usability review |
| Cost figures update within 200ms of slider movement | Measured via Streamlit re-render |
| Break-even TPM matches manual calculation | ± 2% tolerance |
| Time to understand "should I use PTU?" from this view | < 15 seconds (usability target) |

---

## 2. User Experience & Functionality

### 2.1 What It Replaces

**Current UI** (lines 1420-1456 in `dashboard/app.py`):
```
┌─── PTU Pricing ───────────┐  ┌─── PTU Baseline Sizing ──────────┐
│ [Monthly (List Price)    ▼]│  │ [P75 — Cover 75% of traffic   ▼] │
└────────────────────────────┘  └──────────────────────────────────┘
```

3 discrete options. No visual feedback. No break-even visibility.

### 2.2 What It Becomes

**New UI** — an interactive Plotly chart with an integrated slider:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Cost Explorer                                              [?] help │
│                                                                      │
│  Cost/mo                                                             │
│  $15K ┤                                                              │
│       │                              ╱ PAYG (linear)                 │
│  $12K ┤                            ╱                                 │
│       │                          ╱                                   │
│  $9K  ┤                        ╱                                     │
│       │       ┌──────────────╱── PTU+Spill (curve)                   │
│  $6K  ┤       │            ╳ ← BREAK-EVEN ($7,200/mo @ 38K TPM)     │
│       │       │          ╱ │                                         │
│  $3K  ┤       │        ╱   │                                         │
│       │       │      ╱     │                                         │
│  $0   ┼───────┴────╱──────┴─────────────────────────→ Baseline TPM   │
│       0    15K   25K  38K      55K      75K     95K                  │
│                        ↑                                             │
│                   break-even                                         │
│                                                                      │
│  ═══════════════════════════●══════════════════════ Your baseline     │
│  Min(15)    P25    P50    P65    P75    P85    P95    Peak            │
│                            ↑                                         │
│                     Currently: P65 (42K TPM)                         │
│                                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────────────┐  │
│  │ PAYG       │  │ PTU+Spill  │  │ You're 11% above break-even   │  │
│  │ $12,450/mo │  │ $8,200/mo  │  │ ✓ PTU saves $4,250/mo (34%)   │  │
│  └────────────┘  └────────────┘  └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 Component Breakdown

The new control has **4 layers** stacked vertically in a single section:

#### Layer A: The Cost Curve Chart (Plotly)

Two lines plotted against "Baseline TPM" on the x-axis:

1. **PAYG line** (blue, dashed) — Straight line:  
   `PAYG cost = (baseline_tpm × 60 × 24 × 30 / 1M) × blended_rate`  
   This rises linearly with TPM. It represents what you'd pay if all traffic went through PAYG.

2. **PTU + Spillover line** (green, solid) — Curved line:  
   At each baseline TPM level, calculate:
   - PTU cost = `ceil(baseline_tpm / tpm_per_ptu) × 5 × hourly_rate × 720`
   - Spillover = tokens above baseline that overflow to PAYG
   - Total = PTU fixed + spillover variable
   
   This line starts high (fixed PTU cost even at low usage), then flattens as more traffic is absorbed by PTU.

3. **Break-even marker** — A vertical dashed line + annotation where the two lines cross. This is the TPM level where PTU+Spillover cost equals PAYG cost.

4. **"You are here" marker** — A vertical line at the user's current average TPM, showing where they sit relative to break-even.

#### Layer B: The Baseline Slider

A Streamlit slider below the chart:

```python
baseline_pctl = st.slider(
    "PTU Baseline Coverage",
    min_value=0,
    max_value=95,
    value=65,
    step=5,
    format="P%d",
    help="Drag to set what % of your traffic the PTU covers. "
         "Traffic above this spills to PAYG."
)
```

- **Range**: 0 (minimum PTU block) to 95 (near-peak coverage)
- **Step**: 5 (P0, P5, P10, ... P95)
- **Default**: Automatically set to the percentile closest to — but above — the break-even point
- Updates the chart + cost summary in real-time on change

#### Layer C: Cost Summary Strip

Three inline metrics below the slider (same pattern as current UI):

| PAYG Monthly | PTU + Spillover | Verdict |
|---|---|---|
| $12,450 | $8,200 | ✓ 34% saving / PTU saves $4,250/mo |

These update immediately when the slider moves.

#### Layer D: Break-Even Callout

A small contextual banner:

```
┌──────────────────────────────────────────────────────────┐
│ ⚡ Break-even point: 38,000 TPM                          │
│   Your avg usage (42,000 TPM) is 11% above break-even.  │
│   PTU is cost-effective at your current usage level.     │
└──────────────────────────────────────────────────────────┘
```

- **Green** when user's avg TPM > break-even TPM (PTU wins)
- **Yellow** when within ±10% of break-even (marginal)
- **Blue** when user's avg TPM < break-even (PAYG wins)

### 2.4 User Stories

#### US-1: Discover Break-Even Point

> As a **FinOps engineer**, I want to see where PAYG and PTU costs cross so that I know the minimum usage level that justifies PTU commitment.

**Acceptance Criteria:**
- [ ] Break-even TPM is calculated and displayed as a vertical marker on the chart
- [ ] Break-even annotation shows the TPM value and corresponding monthly cost
- [ ] Break-even is recalculated when reservation term changes (on-demand vs 1Y vs 3Y)
- [ ] If break-even doesn't exist (PTU always cheaper or always more expensive), a clear message explains why

#### US-2: Explore Baseline Sizing Interactively

> As a **Cloud Architect**, I want to drag a slider to explore different PTU baseline sizes so that I can see how cost changes as I commit more or less capacity.

**Acceptance Criteria:**
- [ ] Slider is continuous from P0 to P95 in steps of 5
- [ ] Chart updates in < 300ms when slider moves
- [ ] PTU count (units), spillover %, and monthly cost update in the summary strip
- [ ] A vertical indicator on the chart tracks the slider position
- [ ] Current slider position shows the actual TPM value and PTU count

#### US-3: Understand Position vs Break-Even

> As a **Platform Team Lead**, I want to see how far above or below the break-even point my usage is so that I can assess the risk of committing to PTU.

**Acceptance Criteria:**
- [ ] "You are here" marker on the chart at the user's avg TPM
- [ ] Callout shows distance from break-even as a percentage
- [ ] Color coding: green (above break-even), yellow (near), blue (below)
- [ ] If usage is below break-even, callout explicitly says "PAYG is cheaper at your usage level"

#### US-4: Compare Reservation Terms Effect on Break-Even

> As a **FinOps engineer**, I want to see how break-even shifts between on-demand, 1-year, and 3-year reservation terms so that I can evaluate commitment risk vs savings.

**Acceptance Criteria:**
- [ ] Reservation term selector (keep existing dropdown, move above the chart)
- [ ] When term changes, chart redraws with new PTU+Spillover line and break-even marker
- [ ] Break-even annotation updates to show the new crossover point
- [ ] Optionally: show all 3 term lines simultaneously with different opacities

### Non-Goals

- **Multiple models on one chart** — This view is for a single deployment/model
- **Regional pricing** — Region multiplier integration is a separate PRD (#3). Break-even uses the current pricing (hardcoded or future region-aware). Break-even math is pricing-agnostic.
- **Custom pricing overrides** — Deferred (Phase 2, item #11)

---

## 3. Technical Specifications

### 3.1 Break-Even Calculation

The break-even point is the TPM where:  
`PAYG_cost(tpm) = PTU_spillover_cost(tpm, baseline=tpm)`

When baseline = the user's actual TPM (i.e., no spillover), the equation simplifies to:

```python
def calculate_break_even(
    tpm_values: List[float],
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,  # $/1M tokens
    reservation_discount: float = 1.0,  # 1.0 = no discount, 0.303 = 1Y reserved
    min_ptu: int = 15,
    ptu_increment: int = 5,
) -> Optional[float]:
    """
    Find the TPM where PTU monthly cost equals PAYG monthly cost.
    
    PAYG cost = tpm × 60 × 24 × 30 / 1M × blended_rate
    PTU cost  = ceil_to_increment(tpm / capacity_per_ptu, min, inc) × hourly × 720 × discount
    
    Returns the break-even TPM, or None if lines don't cross.
    """
    # Sweep TPM from 0 to max observed + 50% headroom
    max_tpm = max(tpm_values) * 1.5 if tpm_values else 100_000
    step = max(100, max_tpm / 1000)  # 1000 sample points
    
    prev_diff = None
    for tpm in np.arange(step, max_tpm, step):
        payg = tpm * 43_200 / 1_000_000 * payg_blended_rate  # 60×24×30 = 43,200 min/mo
        
        ptu_units = max(min_ptu, int(np.ceil(tpm / ptu_capacity_per_unit / ptu_increment) * ptu_increment))
        ptu_cost = ptu_units * ptu_hourly_rate * 720 * reservation_discount
        
        diff = payg - ptu_cost
        
        if prev_diff is not None and prev_diff < 0 and diff >= 0:
            # Crossed from PTU-more-expensive to PAYG-more-expensive
            # Linear interpolation for exact crossover
            prev_tpm = tpm - step
            ratio = abs(prev_diff) / (abs(prev_diff) + abs(diff))
            return prev_tpm + ratio * step
        
        prev_diff = diff
    
    return None  # Lines don't cross in range
```

**Key insight**: The PTU cost function is a step function (jumps at each PTU increment boundary), while PAYG is linear. The break-even is where the linear line rises above the step function.

### 3.2 Cost Curve Data Generation

For the Plotly chart, pre-compute cost at ~100 TPM sample points:

```python
def generate_cost_curves(
    tpm_values: List[float],
    ptu_capacity_per_unit: float,
    ptu_hourly_rate: float,
    payg_blended_rate: float,
    reservation_discount: float,
    min_ptu: int = 15,
    ptu_increment: int = 5,
) -> pd.DataFrame:
    """
    Generate PAYG and PTU+Spillover cost curves for charting.
    
    Returns DataFrame with columns:
        tpm, payg_monthly, ptu_spillover_monthly
    """
    max_tpm = max(tpm_values) * 1.3 if tpm_values else 100_000
    sample_tpms = np.linspace(0, max_tpm, 200)
    
    rows = []
    for tpm in sample_tpms:
        # PAYG: linear
        payg = tpm * 43_200 / 1_000_000 * payg_blended_rate
        
        # PTU+Spillover at this baseline: 
        # PTU covers `tpm`, spillover is actual traffic above `tpm`
        ptu_units = max(min_ptu, int(np.ceil(tpm / ptu_capacity_per_unit / ptu_increment) * ptu_increment))
        ptu_fixed = ptu_units * ptu_hourly_rate * 720 * reservation_discount
        
        # Spillover: from actual traffic distribution, what overflows above `tpm`
        overflow = [max(0, actual - tpm * ptu_units * ptu_capacity_per_unit / max(tpm, 1)) 
                    for actual in tpm_values]
        avg_overflow = np.mean(overflow) if overflow else 0
        spillover = avg_overflow * 43_200 / 1_000_000 * payg_blended_rate
        
        rows.append({
            "tpm": tpm,
            "payg_monthly": payg,
            "ptu_spillover_monthly": ptu_fixed + spillover,
        })
    
    return pd.DataFrame(rows)
```

### 3.3 Plotly Chart Construction

```python
def create_breakeven_chart(
    cost_curves: pd.DataFrame,
    break_even_tpm: Optional[float],
    user_avg_tpm: float,
    slider_tpm: float,
) -> go.Figure:
    """Create the interactive break-even visualization."""
    fig = go.Figure()
    
    # PAYG line (blue, dashed)
    fig.add_trace(go.Scatter(
        x=cost_curves["tpm"],
        y=cost_curves["payg_monthly"],
        name="PAYG",
        line=dict(color="#0078D4", width=2.5, dash="dash"),
        hovertemplate="<b>PAYG</b><br>%{x:,.0f} TPM<br>$%{y:,.0f}/mo<extra></extra>"
    ))
    
    # PTU + Spillover line (green, solid)
    fig.add_trace(go.Scatter(
        x=cost_curves["tpm"],
        y=cost_curves["ptu_spillover_monthly"],
        name="PTU + Spillover",
        line=dict(color="#00d4aa", width=2.5),
        hovertemplate="<b>PTU+Spillover</b><br>%{x:,.0f} TPM<br>$%{y:,.0f}/mo<extra></extra>"
    ))
    
    # Break-even marker
    if break_even_tpm:
        be_cost = break_even_tpm * 43_200 / 1_000_000 * payg_blended_rate
        fig.add_vline(x=break_even_tpm, line_dash="dot", line_color="#FFB900", line_width=2)
        fig.add_annotation(
            x=break_even_tpm, y=be_cost,
            text=f"Break-even<br>{break_even_tpm:,.0f} TPM<br>${be_cost:,.0f}/mo",
            showarrow=True, arrowhead=2, arrowcolor="#FFB900",
            font=dict(color="#FFB900", size=12),
            bgcolor="rgba(26,26,36,0.9)", bordercolor="#FFB900",
        )
    
    # "You are here" marker
    fig.add_vline(x=user_avg_tpm, line_dash="solid", line_color="#ffffff", line_width=1, opacity=0.5)
    fig.add_annotation(
        x=user_avg_tpm, y=0, yref="paper", yshift=10,
        text=f"Your avg: {user_avg_tpm:,.0f} TPM",
        showarrow=False, font=dict(color="#b8b8c8", size=11),
    )
    
    # Savings zone (green fill between lines where PTU is cheaper)
    # ... fill_between equivalent in Plotly
    
    # Dark theme layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,26,36,0.5)",
        xaxis_title="Baseline TPM",
        yaxis_title="Monthly Cost ($)",
        yaxis_tickformat="$,.0f",
        xaxis_tickformat=",.0f",
        height=400,
        margin=dict(l=60, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        font=dict(family="DM Sans", color="#b8b8c8"),
    )
    
    return fig
```

### 3.4 Slider Integration

The Streamlit slider replaces the current dropdown:

```python
# Replace the current 3-option selectbox with a continuous slider
baseline_pctl = st.slider(
    "PTU Baseline Coverage",
    min_value=0,
    max_value=95,
    value=st.session_state.get('ptu_baseline_percentile', 65),
    step=5,
    format="P%d",
    help="Drag to set what % of your traffic the PTU covers. "
         "Traffic above this spills to PAYG. "
         "The break-even marker shows where PTU becomes cost-effective."
)
```

When the slider moves:
1. Recalculate `baseline_tpm = np.percentile(tpm_values, baseline_pctl)`
2. Recalculate spillover costs via existing `calculate_spillover_cost()`
3. Update the 3-metric summary strip
4. Chart is static (precomputed curves) — only the annotations move

### 3.5 Smart Default

Instead of defaulting to P75, auto-compute the optimal starting position:

```python
# Set default slider to the percentile just above break-even
if break_even_tpm is not None:
    # Find which percentile of the TPM distribution corresponds to break-even
    for p in range(0, 100, 5):
        if np.percentile(tpm_values, p) >= break_even_tpm:
            default_baseline = p
            break
    else:
        default_baseline = 75  # fallback
else:
    default_baseline = 0 if payg_total < hybrid_total else 75
```

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

## 7. Rollout

| Phase | Scope | Effort |
|---|---|---|
| **MVP** | Break-even calc + slider + 2-line chart + summary strip + callout | 1-2 days |
| **v1.1** | Green savings fill zone between lines, "You are here" marker | 0.5 day |
| **v1.2** | Multi-term overlay (show all 3 reservation terms as faded lines) | 0.5 day |
| **v2.0** | Integrate with `cost/engine.py` module when it's built (from main PRD) | Depends on main PRD |

### MVP Scope (implement first)

1. `calculate_break_even()` function  
2. `generate_cost_curves()` function  
3. Plotly chart with 2 lines + break-even vline  
4. `st.slider` replacing the dropdown  
5. Summary strip (PAYG / PTU+Spill / Verdict)  
6. Break-even callout banner  

### Deferred

- Savings fill zone  
- "You are here" marker (nice-to-have since the summary strip already shows the user's costs)
- Multi-reservation-term overlay

---

## 8. Requirement IDs & Traceability

| Requirement ID | Description | Primary Files | Test Coverage | KPI |
|---|---|---|---|---|
| `REQ-UX-101` | Break-even marker visible and interpretable | `dashboard/app.py`, `frontend/src/App.tsx` | `test_dashboard_frontend.py::test_breakeven_marker` | Time-to-understand |
| `REQ-COST-102` | Break-even TPM correctness within tolerance | `cost/engine.py` | `test_cost_engine.py::test_break_even_accuracy` | Accuracy |
| `REQ-UX-103` | Slider updates cost outputs in near real-time | `dashboard/app.py` / frontend | `test_frontend_comprehensive.py::test_slider_recalc` | Recalc latency |
| `REQ-OBS-104` | Slider interaction telemetry emitted | UI layer | telemetry validation test | Interaction analytics |
| `REQ-UX-105` | Position-vs-break-even callout clarity | UI layer | visual/e2e assertion | Usability |

## 9. Performance Budgets

| Interaction | Target | Measurement |
|---|---|---|
| Slider change to updated curve + summary | ≤ 250ms p95 | `ui.chart.interaction_ms` |
| Reservation term change to full redraw | ≤ 500ms p95 | `ui.cost.recalc_ms` |

## 10. Observability Plan

Required events:

- `assumption_changed` (includes term + baseline percentile)
- `cost_recalculated`
- `break_even_marker_rendered`
- `break_even_unavailable`

Required dimensions:

- `policy_version`
- `recommendation`
- `model_name`
- `deployment_type`

## 11. Definition of Done (Feature)

- [ ] `REQ-*` requirements mapped to automated tests
- [ ] Break-even correctness validated against manual baseline cases
- [ ] Interaction latency budgets recorded (p50/p95)
- [ ] Tooltip and copy reviewed for plain-language clarity
- [ ] No markdown formatting artifacts in rendered narrative text
- [ ] Rollback path documented (fallback to static baseline mode)
