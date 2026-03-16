# PRD: Chart Overhaul — Timeframe Selection & Visualization Upgrade

> **Version**: 1.0  
> **Date**: March 16, 2026  
> **Author**: PTU Advisor Team  
> **Priority**: P1 — UX-critical regression  
> **Status**: Draft

---

## 1. Executive Summary

### Problem Statement

The current chart implementation uses **Recharts 3.x** with a **custom-built drag-to-zoom** mechanism for timeframe selection. This approach has accumulated several UX and technical issues:

| Issue | Impact |
|---|---|
| **Index-based zoom on categorical X-axis** | `fullTimeLabels.indexOf()` does a linear scan on every mouse-up — laggy on large datasets (1000+ points) |
| **No minimap / overview bar** | After zooming, user has no visual reference of where they are within the full dataset. A raw `<input type="range">` slider is the only navigation — unintuitive |
| **ReferenceArea flicker** | The zoom overlay briefly flashes on quick click-and-release interactions |
| **Re-analysis spam** | Every zoom/pan fires a debounced (250ms) backend API call. Rapid slider adjustments cause excessive network requests and flickering results |
| **No touch / keyboard support** | Drag-to-zoom is mouse-only — inaccessible on tablets and for keyboard-driven users |
| **syncId coupling confusion** | All 5 time charts share `syncId="time-sync"`, so dragging on one chart zooms all — but visual feedback only appears on the chart being dragged |
| **No data downsampling** | Full dataset renders even when only a slice is visible — unnecessary DOM/canvas work |
| **`any` casts in tooltips** | Multiple Recharts v3 typing gaps forced `eslint-disable` + `as any` workarounds |

The drag-to-zoom was a reasonable MVP solution, but it reimplements ~200 lines of what mature charting libraries ship as a built-in, battle-tested component. It's time to replace it.

### Platform Clarification

> **Note:** `react-native-chart-kit` was considered but is a **React Native (mobile)** library. PTU Advisor's frontend is a **React web app** (Vite + TypeScript). This PRD evaluates web-native charting libraries that provide the same spirit — clean, opinionated time-series charts with built-in range selection — for the browser.

### Proposed Solution

Replace Recharts with **Apache ECharts** (via `echarts-for-react`) as the charting engine. ECharts provides:

- **Built-in `dataZoom`** — both a slider-type minimap bar and an inside-chart drag-to-zoom, with no custom code needed.
- **Chart linking** via `echarts.connect()` — synced crosshairs, zoom, and tooltips across all charts.
- **Canvas rendering** with automatic downsampling — handles 10K+ points without DOM bloat.
- **All current chart types** (area, line, composed, reference lines/dots) plus stacked bars, heatmaps, and more.
- **Accessible** — keyboard navigation, ARIA attributes, and touch/pinch zoom built-in.

The migration replaces ~700 lines of Recharts JSX + ~200 lines of custom zoom logic with ~500 lines of ECharts option configs, while gaining a significantly better timeframe selection UX.

### Success Criteria

| KPI | Target |
|---|---|
| Timeframe selection works via slider minimap AND drag-to-zoom | Both interaction modes available on all time-series charts |
| Zoom/pan does not trigger backend re-analysis until user confirms | "Re-analyze this window" button replaces automatic debounced calls |
| All 6 current chart types render identically to today | Visual parity validated via screenshot comparison |
| Chart render time for 14-day dataset (20K points) | < 200ms initial, < 50ms on zoom |
| Touch zoom works on iPad Safari | Pinch-to-zoom + drag-to-pan |
| Keyboard accessible | Arrow keys pan, +/- zoom, Enter to confirm window |
| No `any` casts or eslint-disable in chart code | 0 type workarounds |
| ExportReport inline SVGs unaffected | Export path remains independent |

---

## 2. Library Evaluation

### Why Apache ECharts

| Criteria | Recharts 3 (current) | Apache ECharts 5 | Chart.js 4 | Victory |
|---|---|---|---|---|
| **Built-in range selection** | ❌ None — custom drag-to-zoom | ✅ `dataZoom` slider + inside | ⚠️ Plugin (`chartjs-plugin-zoom`) | ⚠️ `VictoryZoomContainer` (basic) |
| **Minimap overview bar** | ❌ Manual `<input range>` | ✅ Native — shows data preview | ⚠️ Plugin, no preview | ❌ None |
| **Chart linking / sync** | ⚠️ `syncId` (DOM-heavy) | ✅ `echarts.connect()` (canvas) | ❌ Manual | ❌ Manual |
| **Rendering** | SVG (DOM nodes per point) | Canvas (fast) + SVG option | Canvas | SVG |
| **Large dataset perf** | ⚠️ Degrades past 2K points | ✅ 100K+ points with sampling | ✅ Good with decimation | ⚠️ Degrades past 5K |
| **Touch/pinch zoom** | ❌ | ✅ Built-in | ✅ Via plugin | ⚠️ Basic |
| **TypeScript types** | ⚠️ v3 has gaps | ✅ Full `echarts/types` | ✅ Good | ✅ Good |
| **Stacked area/bar** | ✅ | ✅ | ✅ | ✅ |
| **Reference lines/dots** | ✅ | ✅ (`markLine`, `markPoint`) | ⚠️ Plugin | ✅ |
| **React wrapper maturity** | Native React lib | `echarts-for-react` (14K ★) | `react-chartjs-2` (6K ★) | Native React lib |
| **Bundle size (gzip)** | ~45 KB | ~300 KB (tree-shakeable to ~120 KB) | ~65 KB | ~55 KB |
| **Community / maintenance** | Active | Apache Foundation, very active | Active | Formidable Labs, active |

**Verdict:** ECharts wins on the core pain point (timeframe selection) and adds significant headroom for the upcoming [consolidation feature](PRD-multi-deployment-consolidation.md) (stacked per-deployment series, more chart types). The larger bundle size is offset by tree-shaking and the removal of ~400 lines of custom zoom infrastructure.

### Tree-Shaking Strategy

ECharts supports modular imports to reduce bundle size:

```typescript
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { DataZoomComponent, TooltipComponent, GridComponent, 
         MarkLineComponent, MarkPointComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, CanvasRenderer,
  DataZoomComponent, TooltipComponent, GridComponent,
  MarkLineComponent, MarkPointComponent, LegendComponent,
])
```

Expected tree-shaken size: **~120 KB gzip** (vs Recharts' current ~45 KB — a +75 KB increase, acceptable for the feature gain).

---

## 3. User Experience

### 3.1 Timeframe Selection — New UX

The new timeframe selection replaces the fragile drag-to-zoom + range slider with ECharts' native `dataZoom` component, which provides **two interaction modes simultaneously**:

#### Mode 1: Minimap Slider (always visible)

A **data-preview slider bar** appears below the chart, showing a scaled-down version of the full dataset. The user drags the handles to select a window.

```
 ┌──────────────────────────────────────────────────────────────┐
 │                                                              │
 │         TPM over Time (zoomed to Mar 3–7)                    │
 │                                                              │
 │    ╱╲    ╱╲   ╱╲╱╲                                          │
 │   ╱  ╲  ╱  ╲ ╱    ╲                                         │
 │  ╱    ╲╱    ╲╱      ╲──────                                 │
 │ ╱                                                            │
 │                                                              │
 └──────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────┐
 │▕░░░░░░░░░░│████████████████│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▕│  ← MINIMAP
 │           ↑ Mar 3           Mar 7 ↑                         │
 └────────────────────────────────────────────────────────────┘
   ← Drag handles to resize window    Drag center to pan →

 The minimap shows the full 14-day dataset as a faded line
 preview. The highlighted region corresponds to the zoomed
 view above.
```

#### Mode 2: Inside-Chart Drag-to-Zoom (optional enhancement)

Holding **Shift + drag** inside the chart body selects a region (blue overlay), then zooms to that range. This preserves the "power user" gesture from the current implementation but without the custom code — ECharts handles it natively.

#### Mode 3: Scroll-to-Zoom

**Mouse wheel** over the chart zooms in/out centered on the cursor position. **Pinch gesture** on touch devices does the same.

#### Synced Zoom Across Charts

All 5 time-series charts share a linked `dataZoom` via `echarts.connect('time-group')`. Zooming one chart zooms all — just like today's `syncId`, but with the minimap staying in sync too.

```
 Token Volume        [zoomed to Mar 3–7]
 ┌─────────────────────────────────────┐
 │ ╱╲╱╲╱╲                              │
 └─────────────────────────────────────┘
 ┌─── minimap ─── [███████]────────────┐

 Request Outcomes   [zoomed to Mar 3–7]  ← synced automatically
 ┌─────────────────────────────────────┐
 │ ╱╲  ╱╲ ╱╲                           │
 └─────────────────────────────────────┘
 ┌─── minimap ─── [███████]────────────┐

 Latency (TTFB)     [zoomed to Mar 3–7]  ← synced automatically
 ┌─────────────────────────────────────┐
 │ ──╱──╲──╱──                          │
 └─────────────────────────────────────┘
 ┌─── minimap ─── [███████]────────────┐
```

**Key UX improvement:** Only the **first chart** (Token Volume) shows the full minimap with a data preview. The other charts show a **thin slider bar** (no data preview) to avoid visual clutter. All are synced.

### 3.2 Re-Analysis Behavior Change

**Current (broken):** Every zoom/pan triggers a debounced backend API call → results flicker, excessive network traffic.

**New:** Zoom/pan is **purely visual** (client-side data slice). A persistent **"Re-analyze this window"** button appears when the zoomed range differs from the analyzed range:

```
 ┌──────────────────────────────────────────────────────────────┐
 │  ⓘ Viewing Mar 3–7 of Mar 1–14.                             │
 │  The analysis below covers the full 14-day period.           │
 │                                                              │
 │  [ 🔄 Re-analyze Mar 3–7 only ]    [ ↩ Reset to full range ] │
 └──────────────────────────────────────────────────────────────┘
```

Clicking "Re-analyze" sends the window to the backend **once**, replacing the analysis. This eliminates the debounce-spam problem entirely.

### 3.3 Click-to-Pin (retained)

Clicking a data point still pins a vertical reference line across all synced charts and opens the "Selected Time Snapshot" card. This behavior is unchanged — ECharts supports it via `bindEvent('click')`.

### 3.4 Chart Feature Matrix — Current vs. New

| Feature | Current (Recharts) | New (ECharts) |
|---|---|---|
| Area chart with gradient fill | ✅ | ✅ (`areaStyle` with gradient) |
| Composed chart (area + line) | ✅ | ✅ (multiple series in one chart) |
| Line chart with multiple series | ✅ | ✅ |
| Custom dark tooltip | ✅ (manual CSS) | ✅ (`tooltip.backgroundColor`, `borderColor`, `textStyle`) |
| Synced crosshairs across charts | ✅ (`syncId`) | ✅ (`echarts.connect()`) |
| Reference lines (break-even, avg) | ✅ (`ReferenceLine`) | ✅ (`markLine`) |
| Reference dots (slider markers) | ✅ (`ReferenceDot`) | ✅ (`markPoint`) |
| Zoom — drag selection | ✅ (custom, buggy) | ✅ (`dataZoom` inside type) |
| Zoom — minimap slider | ❌ (raw `<input range>`) | ✅ (`dataZoom` slider type with data preview) |
| Zoom — scroll wheel | ❌ | ✅ (built-in) |
| Zoom — touch pinch | ❌ | ✅ (built-in) |
| Pan while zoomed | ⚠️ (raw slider only) | ✅ (drag minimap center, or drag inside chart) |
| Keyboard zoom/pan | ❌ | ✅ (after focus: arrow keys pan, +/- zoom) |
| Smart date axis formatting | ✅ (custom `makeSmartDateFormatter`) | ✅ (built-in adaptive time axis) |
| Expand/collapse toggle | ✅ (wrapper div) | ✅ (wrapper div — unchanged) |
| Empty state fallback | ✅ (`ChartEmpty`) | ✅ (wrapper component — unchanged) |
| Cost curve (non-time chart) | ✅ | ✅ (separate chart, no `dataZoom`) |
| Stacked area (consolidation future) | ⚠️ (possible but verbose) | ✅ (native `stack` property) |
| Heatmap (traffic patterns future) | ❌ | ✅ (native `heatmap` series) |
| Data downsampling | ❌ | ✅ (`sampling: 'lttb'` — Largest Triangle Three Buckets) |
| Canvas rendering | ❌ (SVG only) | ✅ (Canvas default, SVG optional) |

### 3.5 New Capabilities (beyond current)

These are "free" with ECharts — no extra work beyond configuration:

| Capability | Description | Value |
|---|---|---|
| **LTTB downsampling** | Automatically reduces rendered points while preserving visual shape | Performance on 14-day (20K+) datasets |
| **Toolbox** | Built-in floating toolbar: save as PNG, toggle data view, restore zoom | User can screenshot individual charts |
| **Data point highlight on hover** | Enlarged point + shadow on hover, matching series color | Better readability at dense scales |
| **Axis pointer crosshair** | Vertical + horizontal crosshair lines that track the cursor | Easier to read exact values |
| **Animation on load** | Smooth draw-in animation when charts first render | Polish |
| **Responsive text** | Axis labels auto-rotate and truncate based on container width | No more overlapping date labels on narrow screens |

---

## 4. Technical Specifications

### 4.1 Dependencies

**Add:**
```json
{
  "echarts": "^5.6.0",
  "echarts-for-react": "^3.0.2"
}
```

**Remove:**
```json
{
  "recharts": "^3.2.1"
}
```

### 4.2 File Structure

```
frontend/src/
├── charts/
│   ├── index.ts                   # Re-exports all chart components
│   ├── theme.ts                   # Dark theme config (colors, fonts, grid)
│   ├── echarts-setup.ts           # Tree-shaken ECharts module registration
│   ├── use-chart-zoom.ts          # Hook: manages dataZoom state + re-analyze trigger
│   ├── use-chart-sync.ts          # Hook: echarts.connect('time-group') lifecycle
│   ├── TokenVolumeChart.tsx       # Replaces inline token ComposedChart
│   ├── RequestOutcomesChart.tsx   # Replaces inline request ComposedChart
│   ├── LatencyChart.tsx           # Replaces inline latency LineChart
│   ├── ThrottleChart.tsx          # Replaces inline 429 LineChart
│   ├── TpmBandChart.tsx           # Replaces inline TPM ComposedChart
│   ├── CostCurveChart.tsx         # Replaces inline cost LineChart
│   └── ChartEmpty.tsx             # Retained empty-state fallback
├── App.tsx                        # Slimmed down — chart rendering delegated to chart components
└── ...
```

### 4.3 Dark Theme Config (`theme.ts`)

```typescript
export const PTU_CHART_THEME = {
  backgroundColor: 'transparent',
  textStyle: { color: '#a0aec0', fontFamily: 'Inter, system-ui, sans-serif' },
  title: { textStyle: { color: '#e8ecf2' } },
  line: { smooth: false, symbolSize: 0 },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#2d3748' } },
    splitLine: { lineStyle: { color: '#1e2533', type: 'dashed' } },
    axisLabel: { color: '#718096' },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#2d3748' } },
    splitLine: { lineStyle: { color: '#1e2533', type: 'dashed' } },
  },
  dataZoom: {
    backgroundColor: '#1a202c',
    fillerColor: 'rgba(91, 127, 255, 0.15)',
    borderColor: '#2d3748',
    handleStyle: { color: '#5b7fff', borderColor: '#5b7fff' },
    dataBackground: {
      lineStyle: { color: '#4a5568' },
      areaStyle: { color: 'rgba(74, 85, 104, 0.3)' },
    },
    textStyle: { color: '#a0aec0' },
  },
  tooltip: {
    backgroundColor: '#1a202c',
    borderColor: '#2d3748',
    textStyle: { color: '#e8ecf2' },
  },
  color: ['#5B7FFF', '#2F9E77', '#F6AD55', '#E53E3E', '#A78BFA', '#DD6B20'],
}
```

### 4.4 Chart Zoom Hook (`use-chart-zoom.ts`)

```typescript
type ZoomState = {
  /** Index range within the full dataset [start%, end%] — 0 to 100 */
  range: [number, number]
  /** Whether the current zoom differs from the analyzed window */
  isDirty: boolean
  /** The ISO timestamps of the current zoom window edges */
  windowStart: string | null
  windowEnd: string | null
}

function useChartZoom(
  fullTimestamps: string[],
  analysisStart: string,
  analysisEnd: string,
): {
  zoomState: ZoomState
  onDataZoom: (params: DataZoomEvent) => void
  reAnalyze: () => { window_start: string; window_end: string }
  resetZoom: () => void
}
```

This hook replaces the ~200 lines of `zoomLeft`/`zoomRight`/`zoomDomain`/`handleZoomMouseDown`/`handleZoomMouseMove`/`handleZoomMouseUp`/`applyZoom` logic in the current App.tsx.

### 4.5 Chart Sync Hook (`use-chart-sync.ts`)

```typescript
function useChartSync(groupId: string): {
  registerChart: (instance: ECharts) => void
  unregisterChart: (instance: ECharts) => void
}
```

Wraps `echarts.connect(groupId)` and `echarts.disconnect(groupId)` with proper cleanup on unmount. Replaces the implicit `syncId` prop.

### 4.6 Example: Token Volume Chart Migration

**Before (Recharts — ~65 lines inline in App.tsx):**
```tsx
<ResponsiveContainer width="100%" height={220}>
  <ComposedChart data={applyZoom(chartData.tokens)} syncId="time-sync" {...zoomChartProps}>
    <defs>
      <linearGradient id="gradPrompt">...</linearGradient>
      <linearGradient id="gradCompletion">...</linearGradient>
    </defs>
    <CartesianGrid strokeDasharray="3 3" stroke="#1e2533" />
    <XAxis dataKey="time" ... />
    <YAxis ... />
    <Tooltip content={...} />
    <Area dataKey="prompt" fill="url(#gradPrompt)" stroke="#5B7FFF" ... />
    <Area dataKey="completion" fill="url(#gradCompletion)" stroke="#2F9E77" ... />
    <Line dataKey="total" stroke="#F6AD55" strokeDasharray="6 3" dot={false} />
    {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} ... />}
    {selectedTimestamp && <ReferenceLine x={selectedTimestamp} ... />}
  </ComposedChart>
</ResponsiveContainer>
```

**After (ECharts — `TokenVolumeChart.tsx`):**
```tsx
export function TokenVolumeChart({ data, onDataZoom, selectedTimestamp }: Props) {
  const option: EChartsOption = {
    xAxis: { type: 'time', data: data.timestamps },
    yAxis: { type: 'value', name: 'Tokens' },
    series: [
      {
        name: 'Prompt',
        type: 'line',
        stack: 'tokens',
        areaStyle: { opacity: 0.3 },
        data: data.prompt,
      },
      {
        name: 'Completion',
        type: 'line',
        stack: 'tokens',
        areaStyle: { opacity: 0.3 },
        data: data.completion,
      },
      {
        name: 'Total',
        type: 'line',
        lineStyle: { type: 'dashed' },
        data: data.total,
      },
    ],
    dataZoom: [
      { type: 'slider', bottom: 0, height: 30 },
      { type: 'inside', zoomOnMouseWheel: true },
    ],
    tooltip: { trigger: 'axis' },
    ...(selectedTimestamp && {
      markLine: { data: [{ xAxis: selectedTimestamp }] },
    }),
  }

  return <ReactEChartsCore echarts={echarts} option={option} onEvents={{ datazoom: onDataZoom }} />
}
```

### 4.7 Cost Curve Chart (non-time — no dataZoom)

The cost curve chart plots PAYG vs Hybrid cost against baseline TPM (not time). It retains the same structure — `markLine` for break-even and baseline references, `markPoint` for slider dots. No `dataZoom` is applied since it's a parametric chart.

### 4.8 ExportReport — No Changes

[ExportReport.tsx](../../frontend/src/ExportReport.tsx) renders inline SVG charts for the print/export view. This is intentionally independent of the charting library and **requires no changes**. The export path will continue to use hand-built `<svg>` elements.

---

## 5. Migration Plan

### Phase 1: Foundation (no visual changes yet)

| Task | Detail | Effort |
|---|---|---|
| Install `echarts` + `echarts-for-react` | Add deps, verify build | S |
| Create `echarts-setup.ts` | Tree-shaken module registration | S |
| Create `theme.ts` | Dark theme matching current CSS | S |
| Create `use-chart-zoom.ts` | Zoom state hook with re-analyze trigger | M |
| Create `use-chart-sync.ts` | Chart connection lifecycle hook | S |
| Create `ChartEmpty.tsx` | Port existing empty state wrapper | S |

### Phase 2: Migrate charts one-by-one

Each chart is extracted from `App.tsx` into its own component, tested for visual parity, then swapped in:

| Chart | Component | Effort |
|---|---|---|
| Token Volume | `TokenVolumeChart.tsx` | M |
| Request Outcomes | `RequestOutcomesChart.tsx` | M |
| Latency (TTFB) | `LatencyChart.tsx` | M |
| Rate-Limit (429) | `ThrottleChart.tsx` | S |
| TPM Band | `TpmBandChart.tsx` | M |
| Cost Curve | `CostCurveChart.tsx` | M |

### Phase 3: Remove old code

| Task | Detail | Effort |
|---|---|---|
| Delete all Recharts JSX from `App.tsx` | ~700 lines removed | S |
| Delete custom zoom logic from `App.tsx` | ~200 lines removed (`zoomLeft`, `zoomRight`, `zoomDomain`, `handleZoomMouse*`, `applyZoom`, `resetZoom`, pan slider) | S |
| Remove `recharts` from `package.json` | `npm uninstall recharts` | S |
| Wire up "Re-analyze this window" button | Replace debounced auto-re-analysis | M |
| Update `CHART_TOOLTIP_STYLE` references | Remove — tooltip style is now in theme | S |

### Phase 4: New capabilities

| Task | Detail | Effort |
|---|---|---|
| Enable LTTB downsampling | `sampling: 'lttb'` on large series | S |
| Add toolbox (save PNG, data view) | `toolbox` option on each chart | S |
| Keyboard zoom/pan accessibility | Verify default ECharts keyboard support, add ARIA labels | S |
| Touch pinch-to-zoom validation | Test on iPad Safari, Android Chrome | S |

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Bundle size increase** (~+75 KB gzip) | Certain | Low | Tree-shaking keeps it to ~120 KB. Lazy-load chart modules via `React.lazy()` so charts don't block initial page load. |
| **Visual regression** — charts look subtly different | High | Medium | Create before/after screenshot tests with Playwright. Allow a 2-sprint stabilization window for style tuning. |
| **ECharts learning curve for team** | Medium | Low | ECharts option-based API is declarative and well-documented. Provide a `charts/README.md` with a pattern guide. |
| **Click-to-pin behavior change** | Low | Medium | ECharts' `bindEvent('click')` provides the same data as Recharts `onClick`. Verify payload shape early in Phase 2. |
| **ExportReport breaks** | None | — | Export uses hand-built SVGs — completely independent. |
| **Consolidation feature dependency** | Medium | Medium | The [consolidation PRD](PRD-multi-deployment-consolidation.md) requires stacked per-deployment series. ECharts' native `stack` property makes this trivial, whereas Recharts would require significant additional effort. This migration **unblocks** consolidation. |

---

## 7. Testing Strategy

### 7.1 Visual Regression Testing

Use **Playwright screenshot comparison** (already configured in `playwright.config.ts`):

```typescript
// e2e/charts.spec.ts
test('token volume chart matches baseline', async ({ page }) => {
  await page.goto('/')
  // Select a demo scenario to get chart data
  await page.click('[data-testid="demo-mode"]')
  await page.click('[data-testid="analyze-button"]')
  await page.waitForSelector('[data-testid="token-volume-chart"]')
  
  const chart = page.locator('[data-testid="token-volume-chart"]')
  await expect(chart).toHaveScreenshot('token-volume.png', { maxDiffPixelRatio: 0.05 })
})
```

Run against both **current Recharts** (baseline) and **new ECharts** (comparison). Accept a 5% pixel diff threshold for minor rendering differences (font smoothing, anti-aliasing).

### 7.2 Interaction Testing

| Test | Validation |
|---|---|
| Drag minimap handles | `dataZoom` event fires, chart data updates, all charts sync |
| Scroll-to-zoom | Chart zooms centered on cursor, minimap updates |
| Shift+drag inside chart | Region selected, chart zooms to region |
| Click data point | `selectedTimestamp` updates, reference line appears on all charts |
| "Re-analyze this window" button | Backend call fires once, results update |
| "Reset to full range" button | Zoom clears, minimap returns to 100% |
| Keyboard arrow keys while chart focused | Chart pans |
| Touch pinch on mobile viewport | Chart zooms |

### 7.3 Unit Testing (vitest)

- `use-chart-zoom.ts` — test zoom state transitions, `isDirty` flag, `reAnalyze()` output
- `use-chart-sync.ts` — test lifecycle (register/unregister)
- `theme.ts` — snapshot test of theme object

---

## 8. Acceptance Criteria Summary

- [ ] All 5 time-series charts render with a `dataZoom` slider minimap
- [ ] Dragging the minimap handles zooms the chart and syncs all other time-series charts
- [ ] Scroll-to-zoom works inside any time chart
- [ ] Zooming does NOT auto-trigger backend re-analysis
- [ ] "Re-analyze this window" button appears when zoom ≠ analysis window
- [ ] Clicking "Re-analyze" sends `window_start`/`window_end` to backend once
- [ ] "Reset to full range" button restores the full 14-day view and original analysis
- [ ] Click-to-pin shows a vertical reference line across all synced charts
- [ ] Cost curve chart renders without `dataZoom` (non-time chart)
- [ ] ExportReport inline SVGs are unchanged
- [ ] `recharts` is fully removed from `package.json` and all imports
- [ ] No `eslint-disable` or `as any` casts in chart code
- [ ] Charts render initial load in < 200ms for 14-day datasets
- [ ] Touch zoom works on iPad Safari
- [ ] Keyboard navigation works: arrows to pan, +/- to zoom

---

## 9. Open Questions

| # | Question | Recommendation |
|---|---|---|
| 1 | Should we show a minimap on **all** charts or only the first one? | **First chart only** (Token Volume) gets the full minimap with data preview. Others get a thin slider bar. All stay synced. This reduces visual clutter. |
| 2 | Should Shift+drag be the default zoom gesture, or should free drag zoom? | **Shift+drag** for zoom inside chart. Free drag should pan (when zoomed). This prevents accidental zooms. |
| 3 | When re-analyzing a zoom window, should we show a loading skeleton or keep stale data? | **Keep stale data** with a subtle "Updating…" indicator in the analysis cards. Avoids layout shifts. |
| 4 | Should the toolbox (save PNG, data view) be visible by default or on hover? | **On hover** — keeps the UI clean but discoverable. |
| 5 | Should we evaluate `lightweight-charts` (TradingView) as an alternative for time-series? | **Not for v1.** It's excellent for financial charts but lacks stacked area/bar, reference lines, and the general-purpose flexibility we need. Consider for a dedicated "traffic pattern" view in the future. |
