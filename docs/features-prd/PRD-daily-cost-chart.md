# PRD: Daily Cost Chart (Replace Response Time Stability)

> **Version**: 1.0  
> **Date**: March 16, 2026  
> **Author**: PTU Advisor Team  
> **Status**: 📋 Proposed

---

## 1. Executive Summary

### Problem Statement

The current "Response Time Stability" chart (P50/P95/P99 latency lines) provides limited actionable value for PTU vs PAYG decision-making. Latency percentiles are already approximated via z-score interpolation from `AVG` and `MAX` aggregations — not true percentile data — making them unreliable indicators. Meanwhile, the single most important question users have — **"How much is this deployment actually costing me per day?"** — has no visual answer anywhere in the tool.

Users currently see projected monthly costs in the "Calculation Details" section, but have no visibility into **actual daily cost trends** derived from real consumption data. This makes it difficult to:

- Spot cost spikes from traffic bursts or misconfigurations  
- Understand day-of-week cost patterns (weekday vs weekend)
- Validate that PTU Advisor's projected costs align with actual Azure bills
- Build confidence in the tool's cost recommendations

### Proposed Solution

Replace the "Response Time Stability" chart with a **"Daily Deployment Cost"** bar chart that:

1. Fetches **actual token consumption metrics** (prompt + completion tokens) from Azure Monitor for the selected Foundry resource and deployment
2. Computes **daily PAYG cost** by applying the resolved pricing rates (from the live pricing feature or fallback) to actual daily token volumes
3. Renders as a **stacked bar chart** (input cost + output cost) with all existing chart capabilities: zoom, expand, tooltip, sync, reference lines

### Success Criteria

| KPI | Target |
|-----|--------|
| Daily cost accuracy | ≤ 5% deviation from Azure Cost Management for the same period |
| Chart render time | < 200ms after data arrives (client-side aggregation) |
| Feature parity with other charts | 100% — zoom, expand, tooltip sync, reference lines, point select all work |
| Data availability | Works for any deployment with ≥ 1 day of token metrics |
| Demo mode support | Demo scenarios generate realistic daily cost data |

---

## 2. User Experience & Functionality

### User Personas

| Persona | Pain Point | Need |
|---------|-----------|------|
| **FinOps Engineer** | Monthly cost projections don't show daily variance; can't identify cost spikes | Day-by-day cost breakdown to catch anomalies and validate budget models |
| **Cloud Architect** | No way to visually compare actual spend patterns with PTU break-even threshold | A cost chart overlaid with the PTU cost reference line |
| **Platform Team Lead** | Reporting to leadership requires historical cost trends, not just snapshots | Exportable daily cost time series with weekday/weekend patterns visible |

### User Stories

#### US-1: Daily Cost Visualization

> As a **FinOps Engineer**, I want to see a bar chart of my deployment's actual daily cost broken down by input vs output tokens, so I can identify cost patterns and spikes.

**Acceptance Criteria:**
- [ ] The chart replaces "Response Time Stability" in the same grid position
- [ ] Each bar represents one calendar day within the lookback period
- [ ] Bars are stacked: bottom segment = input token cost, top segment = output token cost
- [ ] Y-axis shows cost in USD (formatted: `$1,234`)
- [ ] X-axis shows dates (formatted via existing `smartDateFmt`)
- [ ] Hovering over a bar shows tooltip with: date, input cost, output cost, total daily cost
- [ ] Chart title: **"Daily Deployment Cost"**
- [ ] Chart tooltip tip: "Actual daily cost derived from token consumption metrics at current pricing rates."

#### US-2: PTU Reference Line

> As a **Cloud Architect**, I want to see the equivalent daily PTU cost as a horizontal reference line on the cost chart, so I can visually assess when PAYG exceeds PTU.

**Acceptance Criteria:**
- [ ] A horizontal dashed reference line shows the daily PTU cost at the current slider position: `(baseline_ptu × ptu_hourly_rate × 24)`
- [ ] Reference line is labeled "PTU Daily Cost" in the legend
- [ ] The line updates when the user adjusts the PTU slider or changes reservation type
- [ ] Days where bars exceed the reference line are visually distinguishable (bars above the line highlight the cost difference)

#### US-3: Average Daily Cost Reference

> As a **FinOps Engineer**, I want a reference line showing the average daily PAYG cost, so I can quickly assess typical spend vs outliers.

**Acceptance Criteria:**
- [ ] A horizontal solid line shows the mean daily PAYG cost across the period
- [ ] Labeled "Avg Daily Cost" in the legend
- [ ] Color: neutral/muted to not compete with the bars

#### US-4: Full Chart Capabilities

> As a **user**, I want the daily cost chart to behave like every other chart in the tool.

**Acceptance Criteria:**
- [ ] **Zoom**: Drag-to-select a date range → triggers re-analysis with windowed data
- [ ] **Expand**: Click expand icon → chart fills viewport as overlay modal
- [ ] **Tooltip sync**: Hovering syncs cursor across all charts via `syncId="time-sync"`
- [ ] **Point select**: Clicking a bar sets the `selectedTimestamp` dashed reference line on all synced charts
- [ ] **Reference area**: Blue highlight during drag-to-zoom
- [ ] **Escape to close**: Expanded chart closes on `Esc` key
- [ ] **Empty state**: Shows `<ChartEmpty>` placeholder when no cost data available

#### US-5: Demo Mode Support

> As a **Solution Engineer** running a demo, I want the daily cost chart to show realistic cost patterns for each demo scenario.

**Acceptance Criteria:**
- [ ] `DemoScenario.PTU_RECOMMENDED` → high, stable daily costs (~$300–400/day) with weekend dips
- [ ] `DemoScenario.PTU_NOT_RECOMMENDED` → low daily costs (~$20–50/day) with high variance
- [ ] `DemoScenario.BORDERLINE` → moderate costs (~$100–200/day) with some spikes
- [ ] Cost data is derived from the existing demo token metric generation (not separately hardcoded)

### Non-Goals

- **Azure Cost Management API integration** — we derive costs from token metrics × pricing rates, not from the billing API directly. The billing API requires different permissions (Cost Management Reader), has multi-hour data delay, and doesn't filter by deployment name reliably.
- **Hourly or sub-daily cost granularity** — the chart always shows daily bars regardless of the selected metric granularity (1/5/15/30 min). Sub-daily cost is not meaningful for cost planning.
- **Multi-currency support** — costs are in USD only.
- **Historical pricing** — daily costs are computed using the current resolved rates, not the rates that were in effect on each historical day.

---

## 3. Technical Specifications

### 3.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                  Existing Metric Flow                     │
│  MetricsCollector → DeploymentMetrics → _serialize_...   │
│  (prompt_tokens, completion_tokens per interval)          │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│              Daily Cost Aggregation (Backend)             │
│                                                          │
│  For each calendar day in the lookback window:           │
│    daily_input_tokens  = Σ prompt_tokens[intervals]      │
│    daily_output_tokens = Σ completion_tokens[intervals]  │
│    daily_input_cost    = daily_input_tokens / 1M         │
│                          × payg_input_rate               │
│    daily_output_cost   = daily_output_tokens / 1M        │
│                          × payg_output_rate              │
│    daily_total_cost    = input_cost + output_cost        │
│                                                          │
│  Also compute:                                           │
│    avg_daily_cost = mean(daily_total_cost[])             │
│    ptu_daily_cost = baseline_ptu × ptu_hourly × 24      │
│                     × reservation_discount               │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  API Response (new field)                 │
│                                                          │
│  charts.daily_cost: {                                    │
│    dates: ["2026-03-01", "2026-03-02", ...],             │
│    input_cost: [45.20, 52.30, ...],                      │
│    output_cost: [120.50, 148.70, ...],                   │
│    total_cost: [165.70, 201.00, ...],                    │
│    avg_daily_cost: 183.40,                               │
│    ptu_daily_cost: 168.00                                │
│  }                                                       │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  Frontend Bar Chart                       │
│                                                          │
│  Recharts <BarChart> with:                               │
│    <Bar dataKey="input_cost" stackId="cost" />           │
│    <Bar dataKey="output_cost" stackId="cost" />          │
│    <ReferenceLine y={ptu_daily_cost} />                  │
│    <ReferenceLine y={avg_daily_cost} />                  │
│    + zoom, expand, tooltip, sync, reference lines        │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Backend Changes

#### 3.2.1 Daily Cost Aggregation in `_serialize_analysis()` ([api/server.py](ptu_advisor/api/server.py))

Add a new aggregation step after existing metric serialization:

```python
def _aggregate_daily_costs(
    timestamps: List[str],
    prompt_values: List[float],
    completion_values: List[float],
    payg_input_rate: float,      # $ per 1M tokens
    payg_output_rate: float,     # $ per 1M tokens
) -> Dict[str, Any]:
    """Aggregate interval-level token data into daily cost bars."""
    from collections import defaultdict
    daily_input: Dict[str, float] = defaultdict(float)
    daily_output: Dict[str, float] = defaultdict(float)

    for ts, p_tok, c_tok in zip(timestamps, prompt_values, completion_values):
        day = ts[:10]  # "2026-03-01T14:00:00Z" → "2026-03-01"
        daily_input[day] += p_tok
        daily_output[day] += c_tok

    dates = sorted(daily_input.keys())
    input_costs = [(daily_input[d] / 1_000_000) * payg_input_rate for d in dates]
    output_costs = [(daily_output[d] / 1_000_000) * payg_output_rate for d in dates]
    total_costs = [ic + oc for ic, oc in zip(input_costs, output_costs)]
    avg_daily = sum(total_costs) / len(total_costs) if total_costs else 0.0

    return {
        "dates": dates,
        "input_cost": [round(v, 2) for v in input_costs],
        "output_cost": [round(v, 2) for v in output_costs],
        "total_cost": [round(v, 2) for v in total_costs],
        "avg_daily_cost": round(avg_daily, 2),
    }
```

Add to return payload under `charts`:

```python
"daily_cost": {
    **_aggregate_daily_costs(
        timestamps=iso_timestamps,
        prompt_values=prompt_token_values,
        completion_values=completion_token_values,
        payg_input_rate=payg_input_rate,
        payg_output_rate=payg_output_rate,
    ),
    "ptu_daily_cost": round(ptu_baseline_cost / 30, 2),  # monthly → daily
}
```

#### 3.2.2 Remove Latency Chart Serialization

Remove from the `charts` response:

```python
# DELETE: charts.latency section
"latency": {
    "timestamps": ...,
    "p50": ...,
    "p95": ...,
    "p99": ...,
}
```

#### 3.2.3 Demo Data Generation ([demo.py](ptu_advisor/demo.py))

The daily cost chart derives data from existing `prompt_tokens` and `completion_tokens` TimeSeries in demo scenarios — no new demo data generation needed. The backend aggregation function handles both live and demo data identically.

### 3.3 Frontend Changes

#### 3.3.1 Type Updates ([types.ts](frontend/src/types.ts))

```typescript
// ADD to charts type:
daily_cost: {
  dates: string[]           // "2026-03-01", "2026-03-02", ...
  input_cost: number[]      // $ per day (input tokens)
  output_cost: number[]     // $ per day (output tokens)
  total_cost: number[]      // $ per day (input + output)
  avg_daily_cost: number    // Mean across all days
  ptu_daily_cost: number    // PTU daily cost at current slider
}

// REMOVE from charts type:
latency: {
  timestamps: string[]
  p50: number[]
  p95: number[]
  p99: number[]
}
```

#### 3.3.2 Chart Data Construction ([App.tsx](frontend/src/App.tsx))

Replace `latencyChartData` memo:

```tsx
const dailyCostChartData = useMemo(() => {
  if (!analysis) return []
  const dc = analysis.charts.daily_cost
  return dc.dates.map((date, idx) => ({
    time: date,
    input_cost: dc.input_cost[idx] ?? 0,
    output_cost: dc.output_cost[idx] ?? 0,
    total_cost: dc.total_cost[idx] ?? 0,
    avg: dc.avg_daily_cost,
    ptu_ref: dc.ptu_daily_cost,
  }))
}, [analysis])
```

#### 3.3.3 Chart JSX — Replace Response Time Stability

Remove the existing `<LineChart>` for latency and replace with:

```tsx
<article className={`chart-card${expandedChart === 'dailyCost' ? ' is-chart-expanded' : ''}`}>
  <WidgetHeader
    title="Daily Deployment Cost"
    tip="Actual daily cost derived from token consumption metrics at current pricing rates."
    onExpand={() => setExpandedChart(expandedChart === 'dailyCost' ? null : 'dailyCost')}
  />
  {dailyCostChartData.length === 0 ? <ChartEmpty height={240} /> : (
  <ResponsiveContainer width="100%" height={getChartHeight('dailyCost', 240)}>
    <ComposedChart data={applyZoom(dailyCostChartData)} syncId="time-sync" {...zoomChartProps}>
      <CartesianGrid stroke="rgba(120,140,170,0.2)" />
      <XAxis dataKey="time" tick={...} tickFormatter={smartDateFmt} ... />
      <YAxis tickFormatter={(v) => `$${formatWithCommas(v)}`} label={{ value: 'USD', ... }} />
      <Tooltip
        contentStyle={CHART_TOOLTIP_STYLE}
        formatter={(value, name) => [`$${formatWithCommas(value)}`, name]}
      />
      <Legend content={<StaticLegend items={[
        { label: 'Input Cost', color: CHART_COLORS.primary },
        { label: 'Output Cost', color: CHART_COLORS.secondary },
        { label: 'Avg Daily', color: CHART_COLORS.neutral },
        { label: 'PTU Daily', color: CHART_COLORS.danger },
      ]} />} />
      <Bar dataKey="input_cost" stackId="cost" fill={CHART_COLORS.primary} name="Input Cost" radius={[0, 0, 0, 0]} />
      <Bar dataKey="output_cost" stackId="cost" fill={CHART_COLORS.secondary} name="Output Cost" radius={[4, 4, 0, 0]} />
      <ReferenceLine y={dailyCostChartData[0]?.avg} stroke={CHART_COLORS.neutral} strokeDasharray="6 3" />
      <ReferenceLine y={dailyCostChartData[0]?.ptu_ref} stroke={CHART_COLORS.danger} strokeDasharray="4 3" />
      {selectedTimestamp && <ReferenceLine x={selectedTimestamp} stroke="rgba(215,225,255,0.7)" strokeDasharray="4 3" />}
      {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
    </ComposedChart>
  </ResponsiveContainer>
  )}
</article>
```

### 3.4 Data Flow: Token Metrics → Daily Cost Bars

```
Azure Monitor
  │
  │  MetricsCollector._collect_metric()
  │  PT{granularity}M intervals
  │
  ├─► prompt_tokens: TimeSeries     (e.g., 4,032 five-minute intervals over 14 days)
  ├─► completion_tokens: TimeSeries
  │
  ▼
_serialize_analysis()
  │
  │  Already serializes prompt/completion per interval for the Token Volume chart
  │
  ├─► charts.tokens.prompt[]        (existing, per-interval)
  ├─► charts.tokens.completion[]    (existing, per-interval)
  │
  │  NEW: _aggregate_daily_costs()
  │  Groups intervals by calendar day (ts[:10])
  │  Sums tokens per day, multiplies by pricing rates
  │
  └─► charts.daily_cost             (new, per-day)
        dates: ["2026-03-01", ...]
        input_cost: [45.20, ...]
        output_cost: [120.50, ...]
        total_cost: [165.70, ...]
        avg_daily_cost: 183.40
        ptu_daily_cost: 168.00
```

### 3.5 Sync Behavior: Daily Bars + Interval-Level Charts

The daily cost chart uses **date strings** (`"2026-03-01"`) as X-axis keys while other charts use ISO timestamps (`"2026-03-01T14:00:00Z"`). For `syncId="time-sync"` to work:

- **Tooltip sync**: Recharts syncs by mouse position (pixel offset), not by data key value. Stacked bars still sync visually when hovering across the chart grid.
- **Zoom**: The zoom handler must handle date strings correctly. Since zoom triggers a re-analysis with `window_start`/`window_end`, the selected date range translates to `{date}T00:00:00Z` / `{date}T23:59:59Z`.
- **Point select**: Clicking a bar sets `selectedTimestamp` to the date string. Other charts show the reference line at the nearest timestamp.

### 3.6 Files Modified

| File | Change |
|------|--------|
| `ptu_advisor/api/server.py` | Add `_aggregate_daily_costs()`, add `charts.daily_cost`, remove `charts.latency` |
| `frontend/src/types.ts` | Add `daily_cost` type, remove `latency` type from `charts` |
| `frontend/src/App.tsx` | Replace `latencyChartData` with `dailyCostChartData`, replace LineChart JSX with BarChart JSX |
| `tests/test_api_server.py` | Update chart assertions: expect `daily_cost` instead of `latency` |
| `frontend/src/App.test.tsx` | Update chart rendering tests |

---

## 4. Cost Derivation Formula

The daily cost is computed from **actual token consumption** already collected by the metrics pipeline:

```
daily_input_tokens  = Σ prompt_tokens[i]      for all intervals i in calendar day
daily_output_tokens = Σ completion_tokens[i]   for all intervals i in calendar day

daily_input_cost  = (daily_input_tokens / 1,000,000) × payg_input_rate
daily_output_cost = (daily_output_tokens / 1,000,000) × payg_output_rate
daily_total_cost  = daily_input_cost + daily_output_cost

ptu_daily_cost = (baseline_ptu × ptu_hourly_rate × 24 × reservation_discount)
```

**Why derive from token metrics instead of the Azure Cost Management API:**

| Approach | Pros | Cons |
|----------|------|------|
| **Token metrics × rates** (chosen) | No extra permissions, instant data, deployment-level granularity, works with demo mode | Approximation — doesn't include any surcharges or billing adjustments |
| **Cost Management API** | Exact billing data | Requires Cost Management Reader role, 24-48h data delay, resource-level only (not per-deployment), doesn't work in demo mode |

---

## 5. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| Token metric gaps (zero-fill intervals) | Daily cost bars show artificially low cost for days with missing data | Medium | Count non-zero intervals per day; if < 50% of expected intervals, mark the bar as "partial" with a visual indicator |
| Pricing rate mismatch with billing | Daily costs don't match Azure invoice exactly | Medium | Display disclaimer: "Estimated cost based on current rates × token consumption. May differ from invoice due to commitment discounts, rounding, or rate changes." |
| Tooltip sync mismatch (daily vs sub-daily) | Hover on daily bar doesn't perfectly align with sub-daily charts | Low | Acceptable UX tradeoff; Recharts syncs by pixel position which is close enough for cross-chart comparison |
| Removing latency chart loses useful data | Some users rely on latency trends | Low | Latency metrics remain in the "At a Glance" summary cards (P50/P95/P99 values). A future iteration could add a latency chart back as a togglable view. |

---

## 6. Phased Rollout

### Phase 1: Core Daily Cost Chart (MVP)

- [ ] Add `_aggregate_daily_costs()` to `api/server.py`
- [ ] Add `charts.daily_cost` to API response with `dates`, `input_cost`, `output_cost`, `total_cost`, `avg_daily_cost`, `ptu_daily_cost`
- [ ] Remove `charts.latency` from API response
- [ ] Update `frontend/src/types.ts` — remove latency chart type, add daily_cost chart type
- [ ] Replace `latencyChartData` with `dailyCostChartData` in `App.tsx`
- [ ] Render stacked `<Bar>` chart with input/output cost stacks
- [ ] Add PTU daily cost reference line + average daily cost reference line
- [ ] Wire up zoom, expand, tooltip sync, point select, reference area
- [ ] Update tests (backend + frontend)
- [ ] Verify demo mode renders realistic daily cost bars

### Phase 2: Polish & Edge Cases

- [ ] Partial-day indicator for first/last day of lookback window (may have less than 24h of data)
- [ ] Tooltip shows breakdown: input tokens, output tokens, input cost, output cost, total
- [ ] Cost formatting with 2 decimal places in tooltip, rounded in axis labels
- [ ] Bar color gradient matching existing chart aesthetic (gradient fill like Token Volume chart)
- [ ] Weekend shading or labels on X-axis to highlight day-of-week patterns

### Phase 3: Integration with Live Pricing (depends on PRD-live-pricing-fetch)

- [ ] When live pricing is resolved, daily costs automatically use the live rates
- [ ] Display pricing source badge on the chart header ("Live rates" / "Fallback rates")
- [ ] If pricing overrides are active, annotate chart title: "Daily Cost (custom rates)"

---

## 7. Testing Strategy

| Layer | What | Tool |
|-------|------|------|
| Unit | `_aggregate_daily_costs()` — correct day grouping, cost math, edge cases (empty data, single day) | `pytest` |
| Unit | Daily cost response shape in `_serialize_analysis()` | `pytest` + `TestClient` |
| Unit | Demo scenario daily cost values are reasonable (PTU_RECOMMENDED > $200/day, PTU_NOT_RECOMMENDED < $80/day) | `pytest` |
| Frontend | `dailyCostChartData` memo returns correct structure | `vitest` |
| Frontend | Chart renders bars, not lines; has correct legend items | `vitest` + React Testing Library |
| E2E | Full demo flow → daily cost chart visible with bars, zoom works | Playwright |

---

## 8. Appendix

### A. Visual Mockup (ASCII)

```
 Daily Deployment Cost                                          [⤢]
 ┌──────────────────────────────────────────────────────────────────┐
 │                                                                  │
 │  $400 ┤                                                          │
 │       │        ████                                              │
 │  $300 ┤  ████  ████  ████  ████  ████        ████  ████  ████   │
 │       │  ████  ████  ████  ████  ████  ────  ████  ████  ████   │  ← PTU Daily ($288)
 │  $200 ┤  ████  ████  ████  ████  ████  ════  ████  ████  ████   │  ← Avg Daily ($265)
 │       │  ████  ████  ████  ████  ████  ████  ████  ████  ████   │
 │  $100 ┤  ████  ████  ████  ████  ████  ████  ████  ████  ████   │
 │       │  ████  ████  ████  ████  ████  ████  ████  ████  ████   │
 │    $0 ┤──█▓▓█──█▓▓█──█▓▓█──█▓▓█──█▓▓█──█▓▓█──█▓▓█──█▓▓█──█▓▓█│
 │       └──┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┘
 │        Mar 1  Mar 2  Mar 3  Mar 4  Mar 5  Mar 6  Mar 7  Mar 8   │
 └──────────────────────────────────────────────────────────────────┘
  ■ Input Cost  ■ Output Cost  ── Avg Daily  ╌╌ PTU Daily
```

### B. Chart Capabilities Parity Checklist

| Capability | Token Volume | Request Outcomes | Daily Cost (new) |
|------------|:---:|:---:|:---:|
| Zoom (drag-to-select) | ✅ | ✅ | ✅ |
| Expand (modal overlay) | ✅ | ✅ | ✅ |
| Tooltip (synchronized) | ✅ | ✅ | ✅ |
| Legend (static) | ✅ | ✅ | ✅ |
| Reference lines | ✅ | ✅ | ✅ (avg + PTU) |
| Point select (dashed vertical) | ✅ | ✅ | ✅ |
| Empty state | ✅ | ✅ | ✅ |
| `syncId="time-sync"` | ✅ | ✅ | ✅ |
| Gradient fill | ✅ | ✅ | Phase 2 |

### C. Relationship to Other PRDs

- **PRD-live-pricing-fetch.md**: When implemented, the daily cost chart will automatically benefit from live-resolved rates instead of hardcoded fallbacks. The `payg_input_rate` and `payg_output_rate` used in `_aggregate_daily_costs()` come from the same variables that the live pricing feature will replace.
- **PRD-breakeven-slider.md**: The PTU daily cost reference line updates reactively as the user moves the PTU slider, providing immediate visual feedback on which days would have been cheaper under PTU.
