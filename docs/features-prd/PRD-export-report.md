# PRD: Customer-Facing Export Report

> **Status:** Draft  
> **Author:** PTU Advisor Team  
> **Date:** 2026-03-10  
> **Priority:** P1 — High-value feature for customer engagement

---

## 1. Executive Summary

### Problem Statement

The PTU Advisor dashboard is an **internal analysis workbench** — packed with interactive charts, dimension scores, formula derivations, traffic-shape signals, and sliders. This level of detail is essential for the engineer running the analysis, but it is **too dense to share directly with a customer**.

When a Solution Engineer finishes an analysis and wants to communicate the recommendation, they currently:

1. Screenshot fragments of the dashboard.
2. Paste them into a slide deck or email.
3. Manually write a summary explaining what the data means.
4. Risk inconsistency, missing context, or human error in translation.

There is **no one-click way to produce a clean, customer-ready document** that says: *"Here is our recommendation, here is why, and here is the cost impact."*

### Proposed Solution

Add an **"Export Report"** button to the results view that generates a **single-page, self-contained PDF/HTML report** designed for customer consumption. The report distills the analysis into five concise sections:

1. **Recommendation banner** — the verdict and confidence level.
2. **Why we recommend this** — plain-language rationale.
3. **Key evidence** — the 4–6 most important metrics, no raw charts.
4. **Cost comparison** — PAYG vs PTU+Spillover bottom line, plus break-even.
5. **Next steps** — what the customer should do.

Critically, when the user has **zoomed into a specific time window** and the analysis has been re-computed for that window, the export reflects the **zoomed analysis** — not the full lookback period. The report header clearly states the exact date range it covers, so the customer knows the recommendation is scoped to that timeframe.

Everything else (interactive charts, granularity controls, formula blocks, dimension deep-dives) stays in the dashboard for the engineer — it does **not** appear in the export.

### Success Criteria

| KPI | Target |
|-----|--------|
| Time from "Export" click to downloadable file | < 3 seconds |
| Report fits on 1–2 printed pages | 100% of scenarios |
| Customer can understand the recommendation without PTU expertise | Validated via 3 usability walkthroughs |
| Report includes no internal jargon or raw formula blocks | 0 instances |
| Works offline (no external asset dependencies in the PDF) | Self-contained |

---

## 2. User Experience & Functionality

### 2.1 User Personas

| Persona | Role | Need |
|---------|------|------|
| **Solution Engineer** | Runs the analysis, exports the report, sends to customer | One-click export, professional appearance |
| **Customer (recipient)** | Decision-maker, FinOps lead, or engineering manager | Clear recommendation, cost impact, actionable next steps |
| **CSA / Account Team** | Forwards report to multiple stakeholders | Self-explanatory document that needs no verbal walkthrough |

### 2.2 User Flow

```
┌─────────────────────────────────────────────────────┐
│  Dashboard — Results View (existing)                │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  At a Glance · Evidence · Financial · Scoring │  │
│  │  ... full analysis UI (unchanged) ...         │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│         [ Export Report ▼ ]   ← NEW BUTTON          │
│           ├─ Download PDF                           │
│           └─ Download HTML                          │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Generated Report (PDF or HTML)                     │
│                                                     │
│  ┌─ Header ────────────────────────────────────┐   │
│  │  PTU Advisor — Deployment Assessment        │   │
│  │  Deployment: gpt-4o-2024-11-20              │   │
│  │  Model: gpt-4o                              │   │
│  │  Analysis Period: Mar 3–Mar 7 (zoomed)      │   │
│  │  Full Lookback: Feb 24–Mar 10 (14 days)     │   │
│  │  Generated: March 10, 2026                  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 1. Recommendation ─────────────────────────┐   │
│  │  ✅ PTU Recommended · Confidence: 82%       │   │
│  │                                              │   │
│  │  "This deployment shows consistent high      │   │
│  │  throughput with measurable rate-limiting.   │   │
│  │  Provisioned throughput would reduce 429     │   │
│  │  errors and lower monthly costs by ~34%."   │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 2. Key Evidence ───────────────────────────┐   │
│  │  Avg TPM          42,300                     │   │
│  │  Peak TPM         78,500                     │   │
│  │  Throttle Rate    8.2%                       │   │
│  │  P95 Latency      320 ms                     │   │
│  │  Active Hours     94%                        │   │
│  │  Burstiness       1.86x                      │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 3. Cost Comparison ────────────────────────┐   │
│  │                                              │   │
│  │  PAYG Only        $12,450 / month            │   │
│  │  PTU + Spillover  $8,200 / month             │   │
│  │  Monthly Savings  $4,250 (34%)               │   │
│  │  Break-even TPM   38,000                     │   │
│  │                                              │   │
│  │  Assumptions: Monthly reservation ·          │   │
│  │  East US (1.00x) · Regional deployment       │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 4. Why This Recommendation ────────────────┐   │
│  │  • Workload is steady with 94% active hours  │   │
│  │  • 8.2% throttle rate indicates capacity     │   │
│  │    pressure under PAYG limits                │   │
│  │  • PTU + spillover is 34% cheaper than PAYG  │   │
│  │  • Burstiness of 1.86x is manageable with    │   │
│  │    PTU baseline at P65 coverage              │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 5. What Would Change This ─────────────────┐   │
│  │  • If traffic drops below 38K sustained TPM  │   │
│  │  • If usage becomes highly seasonal          │   │
│  │  • If throttle rate drops below 2%           │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ 6. Recommended Next Steps ─────────────────┐   │
│  │  1. Reserve 50 PTU (Regional, Monthly term)  │   │
│  │  2. Monitor spillover % in the first week    │   │
│  │  3. Re-evaluate in 30 days with this tool    │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ── Footer ─────────────────────────────────────   │
│  Generated by PTU Advisor · For discussion only ·  │
│  Not a contractual commitment                      │
└─────────────────────────────────────────────────────┘
```

### 2.3 What Is Included vs Excluded

| Section | In Dashboard | In Export Report |
|---------|:------------:|:----------------:|
| Recommendation + confidence | ✅ | ✅ |
| Plain-language explanation | ✅ | ✅ |
| Key metrics summary (6 numbers) | ✅ | ✅ |
| Cost comparison (PAYG vs PTU) | ✅ | ✅ |
| What would change this call | ✅ | ✅ |
| Next steps / action items | ❌ (new) | ✅ |
| Interactive time-series charts | ✅ | ❌ |
| Zoom / pan / granularity controls | ✅ | ❌ |
| Formula blocks (PAYG Math / PTU Math) | ✅ | ❌ |
| Break-even slider | ✅ | ❌ |
| Dimension score deep-dives | ✅ | ❌ |
| Traffic shape signals (burstiness, etc.) | ✅ | ❌ (folded into Key Evidence) |
| Selected point inspector | ✅ | ❌ |
| Region / deployment type picker | ✅ | ❌ (shown as static assumption) |
| Zoom window context / period label | ✅ (via chart UI) | ✅ (as header metadata showing exact date range) |

### 2.4 Zoom-Aware Export

The dashboard supports drag-to-zoom on charts. When the user zooms into a sub-range, the backend re-analyzes **only that time window** — the `analysis` state in React is updated with metrics, costs, dimensions, and recommendation scoped to the zoomed period.

The export report uses **whatever `analysis` state is active at the moment of export**. This means:

| User state | What gets exported |
|------------|-------------------|
| No zoom (full lookback) | Full-period analysis. Header shows `Analysis Period: Feb 24 – Mar 10 (14 days)`. |
| Zoomed to a sub-range | Zoomed analysis. Header shows `Analysis Period: Mar 3 – Mar 7 (zoomed from 14-day lookback)`. |
| Zoomed + adjusted PTU slider | Zoomed analysis with the user's custom PTU baseline and pricing assumptions. |

**Report header fields:**

| Field | Source | Behavior |
|-------|--------|----------|
| Analysis Period | `analysis.analysis_period` | Shows the effective window (full or zoomed) |
| Full Lookback | `baseAnalysis.analysis_period` (if zoomed) | Shows the original full range for context; omitted if not zoomed |
| Zoom indicator | Derived: `zoomDomain !== null` | If zoomed, append "(zoomed)" and show the full lookback as a secondary line |

This ensures the customer sees exactly what time range the recommendation is based on, with no ambiguity.

**Why this matters:** A Solution Engineer may zoom into a high-traffic week to show the customer that PTU makes sense during peak periods. The exported report should reflect that focused analysis — not dilute it with off-peak weeks.

### 2.5 Export Button Placement

The button appears in the results section header, next to the existing recommendation banner:

```
┌─────────────────────────────────────────────────────────────┐
│  ✅ PTU Recommended — Confidence 82%                        │
│  "Steady high throughput with measurable rate-limiting..."  │
│                                                             │
│  [ Explore Analysis ▼ ]    [ Export Report ▼ ]  ← NEW      │
└─────────────────────────────────────────────────────────────┘
```

The dropdown offers:
- **Download as PDF** — uses browser `window.print()` with a print-optimized stylesheet, or client-side PDF generation (html2pdf.js / jsPDF).
- **Download as HTML** — self-contained HTML file with inlined CSS, no external dependencies.

---

## 3. Report Content Specification

### 3.1 Section 1 — Recommendation Banner

| Field | Source in `AnalysisResponse` |
|-------|----------------------------|
| Recommendation label | `recommendation` → mapped to "PTU Recommended" / "Borderline" / "PTU Not Recommended" |
| Confidence percentage | `confidence * 100` |
| One-line summary | `summary` |

Display rules:
- **PTU Recommended** → green banner with checkmark
- **Borderline** → amber banner with warning icon
- **PTU Not Recommended** → neutral/blue banner with X icon

### 3.2 Section 2 — Key Evidence

A table of exactly **6 metrics** that tell the story:

| Label | Source | Format |
|-------|--------|--------|
| Average TPM | `metrics.avg_tpm` | Number with commas |
| Peak TPM | `metrics.peak_tpm` | Number with commas |
| Throttle Rate | `metrics.throttling_rate_pct` | Percentage (e.g., "8.2%") |
| P95 Latency | `metrics.latency.p95` | Milliseconds (e.g., "320 ms") |
| Active Hours | `metrics.utilization.active_hours_percentage` | Percentage |
| Burstiness | `metrics.utilization.peak_to_average_ratio` | Ratio (e.g., "1.86x") |

### 3.3 Section 3 — Cost Comparison

A side-by-side comparison:

| Field | Source |
|-------|--------|
| PAYG monthly cost | `cost_analysis.payg.payg_total` |
| PTU + Spillover monthly cost | `cost_analysis.hybrid.hybrid_total` |
| Monthly savings (absolute + %) | `cost_analysis.comparison.savings`, `cost_analysis.comparison.savings_pct` |
| Break-even TPM | `cost_analysis.comparison.break_even_tpm` |
| Cheaper strategy | `cost_analysis.comparison.cheaper_strategy` |

Assumptions line (shown below the table):

```
{reservation_type} · {region_display_name} ({region_multiplier}x) · {deployment_type_label} · {baseline_ptu} PTU baseline
```

Source: `cost_analysis.pricing.*` and `cost_analysis.hybrid.baseline_ptu`

### 3.4 Section 4 — Why This Recommendation

Plain-language paragraphs explaining the reasoning. Source: `explanation` field from `AnalysisResponse`.

Augmented with the strongest dimension signals. For each of the 4 dimensions where `score !== 'insufficient'`, include a bullet:

```
• {dimension.name}: {dimension.summary}
```

Source: `dimensions[].name`, `dimensions[].summary`

### 3.5 Section 5 — What Would Change This

Source: `what_would_change` field. Rendered as bullet points (split on sentence boundaries).

### 3.6 Section 6 — Recommended Next Steps

Generated from the analysis context:

| Recommendation | Next Steps Template |
|----------------|-------------------|
| PTU Recommended | 1. Reserve {baseline_ptu} PTU ({deployment_type}, {reservation_type}). 2. Monitor spillover % in week 1. 3. Re-evaluate in 30 days. |
| Borderline | 1. Run a 1-week load test with PTU. 2. Compare actual vs projected spillover. 3. Re-run analysis after the test. |
| PTU Not Recommended | 1. Stay on PAYG. 2. Set up cost alerts at current spend level. 3. Re-evaluate if traffic grows or throttling appears. |

### 3.7 Footer

Static text:

```
Generated by PTU Advisor · {date} · For discussion purposes only — not a contractual commitment.
```

---

## 4. Technical Design

### 4.1 Architecture

```
Frontend (React)
    │
    ├─ "Export Report" button click
    │
    ├─ Option A: Client-side generation (preferred for MVP)
    │   ├─ Build report HTML from AnalysisResponse already in memory
    │   ├─ Inject into a print-optimized <div> or hidden iframe
    │   ├─ PDF: trigger window.print() with @media print styles
    │   └─ HTML: serialize to Blob, trigger download
    │
    └─ Option B: Server-side generation (future)
        ├─ POST /api/export-report with AnalysisResponse payload
        ├─ Backend renders Jinja2 HTML template (extend existing report/generator.py)
        └─ Returns HTML or uses WeasyPrint / Playwright for PDF
```

**MVP uses Option A** — no new API endpoint, no server-side dependency. All data is already available in the React state (`analysis: AnalysisResponse`).

### 4.2 Client-Side Implementation

#### New component: `ExportReport.tsx`

```typescript
interface ExportReportProps {
  analysis: AnalysisResponse       // Current analysis (may be zoomed)
  baseAnalysis: AnalysisResponse | null  // Original full-period analysis (null if not zoomed)
  isZoomed: boolean                // Whether user has an active zoom selection
}
```

Responsibilities:
1. Render a hidden `<div id="export-report">` with the report layout.
2. On "Download PDF" → clone the div, open a print window, apply print stylesheet.
3. On "Download HTML" → serialize the div's `outerHTML` with inlined `<style>` block, create a Blob, and trigger `<a download>`.

#### Print stylesheet: `export-report.css`

```css
@media print {
  /* Hide everything except #export-report */
  body > *:not(#export-report-root) { display: none !important; }
  
  /* Report layout */
  #export-report-root {
    font-family: 'Segoe UI', sans-serif;
    color: #323130;
    max-width: 800px;
    margin: 0 auto;
  }
}
```

No external fonts. No external images. Self-contained.

### 4.3 Data Flow

```
App state
  ├── analysis (current — may be full or zoomed)
  ├── baseAnalysis (original full-period, null if no zoom)
  └── zoomDomain (active zoom indices, null if no zoom)
       │
       ▼
  ExportReport component extracts from `analysis`:
       │
       ├── recommendation, confidence, summary
       ├── metrics.avg_tpm, peak_tpm, throttling_rate_pct, latency.p95
       ├── metrics.utilization.active_hours_percentage, peak_to_average_ratio
       ├── cost_analysis.payg.payg_total, hybrid.hybrid_total
       ├── cost_analysis.comparison.savings, savings_pct, break_even_tpm
       ├── cost_analysis.pricing.reservation_type, region_display_name, ...
       ├── explanation, what_would_change
       └── dimensions[].name, summary, score
       │
       ├── IF zoomed: add header line "Analysis Period: {analysis.analysis_period} (zoomed)"
       ├── IF zoomed: add subline "Full Lookback: {baseAnalysis.analysis_period}"
       └── IF not zoomed: header line "Analysis Period: {analysis.analysis_period}"
       │
       ▼
  Rendered into static HTML (no interactivity)
       │
       ▼
  PDF (window.print) or HTML (Blob download)
```

### 4.4 File Changes

| File | Change |
|------|--------|
| `frontend/src/ExportReport.tsx` | **New** — report component + export logic. Receives `analysis`, `baseAnalysis`, and `isZoomed` props. |
| `frontend/src/export-report.css` | **New** — print/export styles |
| `frontend/src/App.tsx` | Add export button + dropdown in results header. Pass `analysis`, `baseAnalysis`, and `zoomDomain !== null` to `ExportReport`. |
| `frontend/src/types.ts` | No changes — existing `AnalysisResponse` has all needed fields |

### 4.5 Dependencies

- **Zero new npm packages** for MVP (using native `window.print()` and Blob API).
- Future enhancement: `html2pdf.js` (~50 KB) for higher-fidelity PDF without print dialog.

---

## 5. Design Requirements

### 5.1 Visual Style

The export report uses a **clean, light-theme, print-friendly design** — not the dashboard's dark theme.

| Aspect | Specification |
|--------|--------------|
| Background | White (`#FFFFFF`) |
| Text | Dark gray (`#323130`) |
| Accent colors | Azure blue (`#0078D4`), green (`#107C10`), amber (`#FFB900`), red (`#D13438`) |
| Font | `Segoe UI` → system sans-serif fallback |
| Page width | 800px max (fits US Letter and A4) |
| Margins | 40px padding all sides |

### 5.2 Recommendation Banner Colors

| Recommendation | Background | Text |
|---------------|-----------|------|
| PTU Recommended | `#DFF6DD` (light green) | `#107C10` |
| Borderline | `#FFF4CE` (light amber) | `#7A6400` |
| PTU Not Recommended | `#DEECF9` (light blue) | `#0078D4` |

### 5.3 Typography

| Element | Size | Weight |
|---------|------|--------|
| Report title | 20px | 600 |
| Section headings | 16px | 600 |
| Body text | 13px | 400 |
| Metric values | 15px | 600 |
| Footer | 11px | 400, muted |

---

## 6. Scope & Milestones

### Phase 1 — MVP (This PR)

- [ ] Export button + dropdown in results header
- [ ] `ExportReport.tsx` component with 6 report sections
- [ ] PDF export via `window.print()` with print stylesheet
- [ ] HTML export via Blob download
- [ ] Self-contained — no external assets

### Phase 2 — Enhancements

- [ ] Include a single static TPM chart snapshot (canvas → PNG → inline `<img>`)
- [ ] Server-side PDF via `/api/export-report` endpoint (reuse `report/generator.py`)
- [ ] Customizable company logo / header via settings
- [ ] "Email report" integration (mailto: with attachment or link)

### Phase 3 — Advanced

- [ ] Multi-deployment comparison report (export all analyzed deployments in one document)
- [ ] LLM-generated executive summary paragraph (via `llm/explainer.py`)
- [ ] Attach report to Azure DevOps work item or GitHub issue

---

## 7. Edge Cases

| Scenario | Handling |
|----------|---------|
| Break-even TPM is `null` | Show "N/A" instead of a number, omit from next-steps |
| Dimension score is `insufficient` | Omit that dimension from the "Why" section, add note: "Some dimensions had insufficient data" |
| Cost savings are negative (PAYG cheaper) | Invert language: "PAYG is currently more cost-effective by $X/month" |
| Very long explanation text | Truncate at 500 characters with "…" in the export |
| Analysis run in demo mode | Add subtle watermark: "Generated from simulated demo data" |
| User is zoomed into a very narrow window (< 1 hour) | Show warning in header: "⚠ Analysis based on a very short time window ({duration}). Results may not be representative." |
| User zooms, exports, then resets zoom | Report reflects the state at time of export — subsequent zoom changes don't affect already-downloaded files |
| `baseAnalysis` is null but `zoomDomain` is set | Shouldn't happen; defensive fallback: treat as non-zoomed, omit "Full Lookback" line |
| Browser blocks print dialog (popup blocker) | Fall back to HTML download with instructions to print |

---

## 8. Out of Scope

- Editable/customizable report templates (Phase 2+).
- Charts or interactive elements in the exported document.
- Automatic email delivery.
- Report versioning or history.
- CSV/Excel data export (separate feature).
- Multi-language / i18n support.

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Should the report include the deployment name prominently, or allow the SE to add a customer-facing project name? | Open |
| 2 | Should we watermark demo-mode reports? | Leaning yes |
| 3 | Do we need a "preview" before download, or is direct download sufficient? | Open |
| 4 | Should the footer include a link back to the live dashboard? | Open — may not be accessible to customer |
