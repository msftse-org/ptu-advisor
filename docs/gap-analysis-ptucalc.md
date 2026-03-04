# PTU Advisor vs ptucalc.com — Gap Analysis

> **Date**: February 2026  
> **Source**: https://www.ptucalc.com/ (full JS bundle analysis)  
> **Purpose**: Feature comparison and implementation roadmap

---

## 1. Our Competitive Strengths (Keep & Amplify)

These capabilities exist **only in PTU Advisor** — ptucalc.com does not have them:

| Capability | Description | File |
|---|---|---|
| **Automated metric collection** | Pulls directly from Azure Monitor SDK — no manual data entry | `metrics/collector.py` |
| **4-dimension analysis** | Workload Shape, Capacity Pressure, Latency Sensitivity, Load Predictability | `analysis/dimensions.py` |
| **Latency sensitivity analysis** | P50/P95/P99 TTFB analysis — zero latency awareness in ptucalc | `analysis/dimensions.py` |
| **LLM-powered explanations** | GPT-enriched natural language reasoning | `llm/explainer.py` |
| **Data quality scoring** | Tells users when they need more data for confidence | `analysis/engine.py` |
| **"What would change" guidance** | Explains what factors would flip the recommendation | `analysis/engine.py` |
| **CLI automation** | Scriptable via Typer for CI/CD or bulk analysis | `cli.py` |
| **Demo mode** | 3 realistic simulated scenarios for testing | `demo.py` |

---

## 2. What ptucalc.com Has

### 2.1 Pricing Models (7 Scenarios)

| Scenario | Description | Status in PTU Advisor |
|---|---|---|
| PAYG | Pay per token, no commitment | ✅ Have (basic) |
| PTU On-Demand | Reserved capacity, hourly billing ($1/PTU/hr base) | ❌ Missing — we only show "PTU" without term distinction |
| PTU 1-Year | 25% discount with 1-year reservation | ❌ Missing — hardcoded single discount |
| PTU 3-Year | 45% discount with 3-year reservation | ❌ Missing |
| Spillover (On-Demand) | Base PTU + PAYG overflow | ✅ Have (dashboard `calculate_spillover_cost`) |
| Spillover (1-Year) | Spillover with 1Y PTU reservation | ❌ Missing — no reservation variants |
| Spillover (3-Year) | Spillover with 3Y PTU reservation | ❌ Missing |

### 2.2 Data Input Methods

| Method | ptucalc.com | PTU Advisor |
|---|---|---|
| Azure Log Analytics (KQL) | Pre-built model-aware KQL query users paste into Azure Monitor | ❌ N/A — we pull via SDK directly |
| Azure Portal Metrics | Manual entry from portal views | ❌ N/A |
| Manual Estimation | Enter avgTPM, P99TPM, maxTPM for planning | ❌ Missing — requires Azure credentials |

### 2.3 Cost Calculation Formulas

| Formula | Expression |
|---|---|
| PTU Hourly | `Base Rate × Regional Multiplier × Deployment Multiplier × PTU Count` |
| PTU Monthly | `Hourly Rate × 730 hours` |
| PTU Yearly | `Monthly Rate × 12 × (1 - Yearly Discount)` |
| PAYG Cost | `Input Tokens × Input Rate + Output Tokens × Output Rate` |
| Break-Even | `PTU Monthly Cost ÷ (Input Rate + Output Rate)` — token volume crossover |
| Spillover | `Base PTU Cost + Overflow PAYGO Cost` |

### 2.4 Regional Pricing (35 Regions)

| Region | Multiplier | | Region | Multiplier |
|---|---|---|---|---|
| East US | 1.0 | | Canada Central | 1.1 |
| East US 2 | 1.0 | | Brazil South | 1.15 |
| West US | 1.05 | | North Europe | 1.05 |
| West US 2 | 1.0 | | West Europe | 1.05 |
| Central US | 1.0 | | UK South | 1.1 |
| South Central US | 1.0 | | France Central | 1.1 |
| East Asia | 1.1 | | Germany West Central | 1.1 |
| Southeast Asia | 1.05 | | Norway East | 1.15 |
| Japan East | 1.15 | | Switzerland North | 1.2 |
| Australia East | 1.1 | | Sweden Central | 1.1 |
| Korea Central | 1.1 | | UAE North | 1.15 |
| South India | 1.05 | | South Africa North | 1.2 |

### 2.5 Deployment Type Multipliers

| Type | Rate Multiplier | Min PTU (typical) | Increment |
|---|---|---|---|
| Global | 1.0x ($1.00/PTU/hr) | 15 | 5 |
| Data Zone | 1.2x ($1.10/PTU/hr) | 15 | 5 |
| Regional | 1.0x ($2.00/PTU/hr) | 50 | 50 |

### 2.6 Reservation Terms

| Term | Discount | Monthly (most models) |
|---|---|---|
| On-Demand | 0% | $730/PTU |
| 1-Year | 25% off | ~$548/PTU |
| 3-Year | 45% off | ~$402/PTU |

### 2.7 Model Coverage (22 Models)

| Model | TPM/PTU | Min PTU (Global/Regional) | PAYG (input/output per 1M) |
|---|---|---|---|
| gpt-4o | 2,500 | 15 / 50 | $2.50 / $10.00 |
| gpt-4o-mini | 37,000 | 15 / 25 | $0.15 / $0.60 |
| gpt-4.1 | 3,000 | 15 / 50 | $2.00 / $8.00 |
| gpt-4.1-mini | 14,900 | 15 / 25 | $0.40 / $1.60 |
| gpt-4.1-nano | 59,400 | 15 / 25 | $0.10 / $0.40 |
| gpt-5 | (default) | 15 / 50 | $1.25 / $10.00 |
| gpt-5-mini | (default) | 15 / 25 | $0.25 / $2.00 |
| gpt-5-nano | (default) | 15 / 25 | $0.05 / $0.40 |
| gpt-5.1 | 1,800 | 20 / 75 | $12.00 / $36.00 |
| gpt-5.2 | 1,600 | 25 / 100 | $15.00 / $45.00 |
| o3 | (default) | 15 / 50 | $2.00 / $8.00 |
| o3-mini | 2,500 | 15 / 25 | $1.10 / $4.40 |
| o4-mini | (default) | 15 / 25 | $1.10 / $4.40 |
| text-embedding-ada-002 | (default) | 25 / 50 | $0.10 / $0 |
| text-embedding-3-large | (default) | 25 / 50 | $0.13 / $0 |
| text-embedding-3-small | (default) | 25 / 50 | $0.02 / $0 |
| whisper | (default) | 25 / 50 | $0.006 / $0 |

### 2.8 Interactive Analytics Dashboard (4 Tabs)

1. **Costs Tab** — Bar chart comparing all 7 pricing scenarios
2. **Utilization Tab** — Capacity utilization + 24-hour hourly usage heatmap
3. **Projections Tab** — Cost growth at 1% monthly growth assumption
4. **Patterns Tab** — Burst ratio, frequency, peak ratio; Steady/Bursty/Spiky pie chart

### 2.9 Burst/Spike Analysis

- **Burst Ratio**: P99TPM / AvgTPM → Steady (< 2x), Bursty (2-3x), Spiky (> 3x)
- **Burst Frequency**: Bursts per day
- **Peak Ratio**: MaxTPM / AvgTPM
- Sizing adjusts split: steady → 70/20/10, spiky → 10/10/80

### 2.10 Export Capabilities

| Format | Content |
|---|---|
| CSV | Config, Cost Breakdown, Analysis, Recommendations |
| JSON | Complete report with metadata versioning (`2025.09.30`) |

### 2.11 Other Features

- **Live Azure Retail Pricing API** (`prices.azure.com`) with 3-hour cache + static fallback
- **Custom pricing overrides** for enterprise agreements (persisted to localStorage)
- **Guided tour** (6 steps) onboarding new users
- **Contextual tooltips** for PTU terminology
- **Pricing data status indicator** (live vs fallback)

---

## 3. Gap Items — Prioritized

### Priority 1: High Impact, Moderate Effort

| # | Gap | Business Value |
|---|---|---|
| **1** | 7-scenario cost comparison (PAYG / PTU On-Demand / 1Y / 3Y / Spillover / Spillover-1Y / Spillover-3Y) | Customers can't compare commitment options today |
| **2** | Break-even analysis (token volume where PTU < PAYG) | Most asked question in PTU consultations |
| **3** | Regional pricing multipliers (35 regions) | Our costs are wrong for non-US regions |
| **4** | Deployment type multipliers (Global / Data Zone / Regional) | Missing entire pricing dimension |
| **5** | Reservation term modeling (On-Demand / 1Y / 3Y explicit) | Currently a single hardcoded 35% discount |
| **6** | Cost growth projections (12-month with configurable growth) | CTO-level planning tool |
| **7** | CSV/JSON structured report export | Stakeholder sharing from dashboard |

### Priority 2: Medium Impact, Medium Effort

| # | Gap | Business Value |
|---|---|---|
| **8** | Burst/spike pattern visualization (Steady/Bursty/Spiky classifier + pie chart) | Better workload characterization |
| **9** | Pre-built KQL query generator for Azure Monitor | Helps users who can't grant SDK access |
| **10** | Live Azure Retail Pricing API integration | Eliminates stale hardcoded pricing |
| **11** | Custom pricing override (enterprise agreements) | EA customers have different rates |
| **12** | 24-hour utilization heatmap | Visual hourly pattern discovery |

### Priority 3: Nice-to-Have

| # | Gap | Business Value |
|---|---|---|
| **13** | Expanded model catalog (22 models including embeddings, whisper) | Broader model coverage |
| **14** | Contextual tooltips/help system | Better onboarding |
| **15** | Guided tour (6-step onboarding) | First-time user experience |
| **16** | Manual estimation input mode (no Azure credentials needed) | Planning/what-if scenarios |

---

## 4. Recommended Implementation Phases

### Phase 1 — Cost Engine Upgrade ← START HERE
Items: #1, #2, #3, #4, #5  
**Goal**: Match ptucalc.com's cost depth while keeping our analytical edge

### Phase 2 — Planning & Projections
Items: #6, #7, #11, #16  
**Goal**: CTO/finance-ready planning tools

### Phase 3 — Visualization & Data
Items: #8, #10, #12, #13  
**Goal**: Richer data presentation

### Phase 4 — Polish & Onboarding
Items: #9, #14, #15  
**Goal**: User experience refinement

---

## 5. Key Pricing Constants Reference (from ptucalc.com)

```
BASE_HOURLY_RATE = $1.00/PTU/hr (base, before multipliers)
MONTHLY_HOURS = 730
MONTHLY_MINUTES = 43,800

Reservation discounts:
  1-Year = 25% off
  3-Year = 45% off

Deployment type multipliers:
  Global = 1.0x
  Data Zone = 1.2x  
  Regional pricing uses separate rate structure

Regional multipliers:
  US (most) = 1.0x
  West US = 1.05x
  Asia = 1.05-1.15x
  Europe = 1.05-1.20x
  Brazil = 1.15x
  South Africa = 1.20x
```

---

*This document should be refreshed quarterly as Azure pricing evolves.*
