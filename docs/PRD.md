Product Requirements Document (PRD)

Product Name
PTU Advisor

**Version:** 1.0 (Implemented)  
**Last Updated:** January 2026  
**Status:** ✅ MVP Complete

---

Problem Statement
Customers frequently ask Solution Engineers and PMs:

“Do I need to buy Provisioned Throughput Units (PTU)?”

Today, answering this requires:

Manual inspection of Foundry monitoring
Deep PTU expertise
Subjective judgment
Non‑repeatable recommendations

This increases:

Time to decision
Risk of incorrect recommendations
Customer dissatisfaction or overspend

There is no automated, opinionated, data‑driven decision system that analyzes existing deployment monitoring and recommends PTU vs PAYG.

Goal
Create an automatic decision tool that connects to Azure AI Foundry, analyzes historical monitoring data, and produces a clear, explainable recommendation:

✅ “PTU recommended”
❌ “PTU not recommended”
⚠ “Borderline – validate with load test”

With justification based only on observable metrics.

Non‑Goals

No automatic purchase of PTU
No exact PTU sizing commitments
No future traffic prediction
No custom application instrumentation


Target Users

Solution Engineers / CSA

Need fast, defensible recommendations


Enterprise Customers

Want clarity and confidence before committing spend


Product / Ops Teams

Want standardized decision criteria




User Stories
Primary
As a Solution Engineer,
I want an automated assessment of my customer’s Foundry deployments
so I can confidently recommend whether PTU makes sense.
Secondary
As a customer,
I want a transparent explanation of why PTU is or isn’t recommended
so I trust the decision.

Data Sources (Grounded in Foundry capabilities)
Foundry Metrics (Available Today)
From Azure AI Foundry / Azure Monitor: [learn.microsoft.com], [learn.microsoft.com]

Requests per time unit
Prompt Tokens Processed
Completion Tokens Generated
Inference Tokens Processed
Time to First Byte
Time to Last Byte
Time to Response
Tokens per Second
Throttling / HTTP 429s
Concurrency patterns
PTU Utilization (when applicable)

✅ All metrics are historical and observable
✅ No customer code access required

Core Product Concept
The tool evaluates four dimensions of readiness:

Workload Shape
Capacity Pressure
Latency Sensitivity
Load Predictability

These align directly with Microsoft’s official PTU guidance:

Predictable throughput
Production readiness
Latency‑sensitive workloads [learn.microsoft.com], [github.com]
---

## Utilization Pattern Analysis (Implemented)

Beyond the four core dimensions, PTU Advisor analyzes **temporal usage patterns** to provide deeper insights:

### Metrics Collected
| Metric | Description | PTU Implication |
|--------|-------------|-----------------|
| **Peak-to-Average Ratio** | Max TPM / Mean TPM | < 1.5 = stable (PTU friendly), > 2.0 = spiky |
| **Sustained Utilization Rate** | % of time above 30% of peak | > 60% favors PTU |
| **Active Hours Percentage** | % of hours with non-zero traffic | > 70% favors PTU |
| **Business Hours Concentration** | % of traffic during 9am-6pm | < 60% = 24/7 usage (PTU optimal) |
| **Weekend vs Weekday Ratio** | Weekend avg / Weekday avg | > 0.7 = consistent (PTU friendly) |
| **Coefficient of Variation** | Std Dev / Mean | < 0.5 = predictable |
| **Zero Activity Periods** | % of time with no traffic | Low = good for PTU |

### Visualizations
- **Hourly Distribution Heatmap**: 24-hour pattern analysis
- **Weekly Distribution Chart**: Day-of-week usage patterns
- **Trend Analysis**: Rolling averages and spike detection

---

Decision Engine (High‑Level Logic)
Input Window

Configurable lookback (default: last 7–14 days)
Business hours vs full day segmentation


Dimension 1: Workload Shape
Signals

Variance of TPM/RPM
Prompt + completion size consistency

Scoring

Stable = ✅
Highly variable / spiky = ❌


Dimension 2: Capacity Pressure
Signals

TPM plateauing
Throttling events
Queuing behavior
Degraded throughput under demand

Interpretation

Indicates PAYG capacity ceiling [learn.microsoft.com]


Dimension 3: Latency Sensitivity
Signals

P95 / P99 latency
Latency variance at similar loads

Heuristic

Stable low latency required → PTU friendly
Latency not business‑critical → stay PAYG


Dimension 4: Load Predictability
Signals

% of day with sustained traffic
Day‑over‑day similarity

Threshold

Sustained load ≥ X% of business hours → PTU candidate
(Exact threshold configurable)


Recommendation Logic
Final Decision Rules (Productized)





















ResultCriteria✅ PTU Recommended≥2 dimensions positive, sustained over time⚠ BorderlineMixed signals or insufficient data❌ PTU Not RecommendedSpiky, idle‑heavy, non‑latency‑critical
This intentionally mirrors how experienced CSAs decide today — but consistently.

Output UX

### Implementation: React Dashboard + FastAPI Backend

The PTU Advisor delivers recommendations through a **React single-page application** backed by a **FastAPI API**. The UI features a dark-themed design with two primary panels:

#### Panel 1: Deployment Advisor
Connect to Azure (or use demo scenarios) to analyze a real deployment:

- **Auto-discovery flow**: Selects subscription → Azure OpenAI account → deployment
- **Focus topics**: "Cost Reduction", "Latency Optimization", etc. (demo mode available)
- **At a Glance cards**: Avg TPM, Peak TPM, Throttling Rate, Analysis Window
- **5 interactive Recharts visualizations** with click-drag-to-zoom and reset:
  - Processed Tokens (area chart)
  - Requests: Success vs Throttled
  - Time to First Byte (P50/P95/P99)
  - Token Usage (Prompt vs Completion)
  - Tokens per Minute
- **Break-even chart** with PAYG vs PTU+Spillover cost curves and baseline slider
- **Spillover cost model**: Sizes PTU to baseline, overflows peaks to PAYG
- **4-dimension scoring breakdown**: Workload Shape, Capacity Pressure, Latency Sensitivity, Load Predictability
- **Recommendation banner** with confidence bar
- **Cost formula details** — transparent math showing how costs were computed
- **Region & deployment type selector**: 35 regions, 3 deployment types (Global, Data Zone, Regional)
- **Reservation type selector**: Hourly, Monthly, 1-Year
- **LLM-powered explanations** (optional — Azure OpenAI)

#### Panel 2: PTU Calculator
Estimate costs from manual inputs — no Azure connection required:

- **8 models**: GPT-4o, GPT-4o Mini, GPT-4.1, GPT-4.1 Mini, GPT-4.1 Nano, GPT-5, o3-mini, o4-mini
- **7 pricing scenarios**: PAYG, Full PTU (On-Demand / 1-Year / 3-Year), Hybrid (On-Demand / 1-Year / 3-Year)
- **Inputs**: Model selection, average TPM, peak TPM, output token share, peak hours/day, region, deployment type
- **Outputs**: Recommendation banner, scenario comparison table, break-even TPM, PTU sizing, savings percentages
- Entirely client-side computation

### Primary Output
One‑sentence verdict with confidence score:

"PTU is recommended for this deployment." (87% confidence)

Supporting Explanation

Key metrics that triggered the recommendation
Visual graphs (TPM, latency, throttling) in Azure Monitor style
Clear human‑readable rationale
**AI-generated analysis** explaining the recommendation

Example

"Your deployment shows stable token throughput across business hours with 78% sustained utilization, consistent hourly patterns (CV: 0.23), and increasing P95 latency under steady load. These characteristics match scenarios PTU is designed to address."


Explainability (Critical Requirement)
Every recommendation must be explainable:

Which metrics mattered
Which ones didn’t
What would change the decision

This is essential for trust with enterprise customers.
### AI-Powered Explanations (Implemented)

The PTU Advisor integrates with **Azure OpenAI** to provide natural language explanations:

```python
# LLM Provider Configuration
LLMConfig(
    provider="azure_openai",  # or "openai", "mock"
    model="gpt-4o",
    temperature=0.3,          # Low temperature for consistent analysis
    max_tokens=1500,
    enable_cache=True         # Cache responses to reduce API calls
)
```

**Explanation Components:**
1. **Main Analysis**: Overall assessment with key findings
2. **Dimension Breakdown**: Score explanation for each dimension
3. **Action Items**: Specific next steps based on recommendation
4. **Conditional Guidance**: "When would PTU make sense?" for non-recommended scenarios

**Mock Provider** for demo mode returns scenario-appropriate responses:
- PTU recommended → Positive analysis with next steps
- PTU not recommended → Explains why PAYG is better
- Borderline → Recommends load testing

---
---

## Architecture (Implemented)

### Technology Stack

**Frontend:**
- **React 19** with TypeScript
- **Vite 7** build tooling
- **Recharts 3** for interactive data visualizations
- Dark-themed CSS with glassmorphism effects

**Backend:**
- **Python 3.9+** with virtual environment
- **FastAPI** + **Uvicorn** for the API server
- **Pydantic** for data validation
- **Typer** for CLI interface
- **Azure Identity** for authentication
- **OpenAI SDK** for LLM integration

**Deployment:**
- **Docker** (recommended) — multi-stage build (Node.js + Python)
- Single container serves both the React SPA and the FastAPI API on port 8000

### Package Structure
```
ptu-recommander/
├── ptu_advisor/                  # Python backend
│   ├── cli.py                    # Typer CLI entry point
│   ├── config.py                 # Configuration, thresholds, model capacity tables
│   ├── auth.py                   # Azure authentication
│   ├── demo.py                   # Demo scenarios with simulated data
│   ├── discovery.py              # Azure subscription/account/deployment discovery
│   ├── api/
│   │   └── server.py             # FastAPI API server (7 endpoints)
│   ├── metrics/
│   │   ├── models.py             # TimeSeries, DeploymentMetrics, DimensionResult, etc.
│   │   └── collector.py          # Azure Monitor metrics collection
│   ├── analysis/
│   │   ├── dimensions.py         # 4 dimension analyzers
│   │   ├── engine.py             # DecisionEngine
│   │   └── rule_explainer.py     # Rule-based explanation generator
│   ├── cost/
│   │   ├── calculator.py         # Spillover cost calculations, break-even
│   │   └── pricing.py            # Region configs, deployment type configs
│   ├── llm/
│   │   ├── provider.py           # Azure OpenAI / OpenAI / Mock providers
│   │   ├── prompts.py            # Structured prompt templates
│   │   └── explainer.py          # LLM-powered narrative explanations
│   ├── visualization/
│   │   └── charts.py             # Matplotlib chart generation (CLI reports)
│   └── report/
│       ├── generator.py          # HTML report builder
│       └── templates/
│           └── report.html       # Jinja2 template
├── frontend/                     # React SPA
│   ├── src/
│   │   ├── App.tsx               # Main app — landing, advisor, calculator, results
│   │   ├── api.ts                # API client (fetch wrappers)
│   │   ├── types.ts              # TypeScript types
│   │   └── styles.css            # Dark-themed CSS
│   ├── vite.config.ts            # Vite config with /api proxy
│   └── package.json
├── Dockerfile                    # Multi-stage build (Node + Python)
├── docker-compose.yml            # Docker deployment
├── pyproject.toml                # Python package config
└── tests/                        # Backend test suite
```

### Demo Mode
Three pre-configured scenarios for testing without Azure connection:
1. **ptu-recommended**: High utilization, stable patterns, latency sensitive
2. **ptu-not-recommended**: Spiky traffic, low utilization, no throttling
3. **borderline**: Mixed signals requiring load test validation

### LLM Integration
- **Azure OpenAI Provider**: Uses gpt-4o via Azure endpoint
- **OpenAI Provider**: Direct OpenAI API access
- **Mock Provider**: Scenario-aware responses for demo mode
- **Caching**: Optional response caching to reduce API calls
- **Structured Prompts**: Role-based system prompts with metrics context

---

Integration Points
Entry Points

✅ **CLI Interface** (`ptu-advisor analyze`, `ptu-advisor demo`)
✅ **React Dashboard + FastAPI API** (Docker: localhost:8000; Dev: localhost:5173 + localhost:8000)
Foundry portal blade (future)
Azure AI resource overview (future)

Permissions

Read‑only monitoring access
No deployment mutation


Success Metrics (KPIs)

% reduction in manual PTU advisory time
Adoption rate by Solution Engineers
Reduction in post‑purchase regret
Customer confidence (qualitative feedback)


Risks & Mitigations

























RiskMitigationOver‑recommending PTUConservative thresholdsUnder‑recommending PTUBorderline stateMisinterpreting burst workloadsBurst detection logicTrust issuesFull metric transparency

Future Extensions (Backlog)

~~Cost simulation~~ ✅ Implemented (Cost Calculator tab)
Automated PTU sizing
Reservation optimization
Load test orchestration
Azure Portal integration
API endpoint for programmatic access
Multi-deployment comparison view
Historical trend analysis
Slack/Teams notifications


---

## Quick Start

```bash
# Docker (recommended)
docker compose up
# Open http://localhost:8000

# Or local dev:
cd ptu-recommander
pip install -e .
uvicorn ptu_advisor.api.server:app --reload --port 8000
cd frontend && npm install && npm run dev
# Open http://localhost:5173

# CLI demo (no dashboard needed)
ptu-advisor demo --scenario ptu-recommended
```

---

Summary (Executive‑Ready)
PTU Advisor standardizes expert judgment into a repeatable, explainable, metrics‑driven decision tool—built directly on Azure AI Foundry's monitoring stack.

**Key Differentiators:**
- 📊 **Interactive Recharts visualizations** with drag-to-zoom
- 🤖 **AI-powered explanations** via Azure OpenAI integration
- 🔄 **Auto-discovery** of Azure subscriptions, accounts, and deployments
- 💰 **Spillover cost model** with break-even analysis and baseline slider
- 🧮 **PTU Calculator** — 8 models, 7 pricing scenarios, no Azure connection needed
- 🎭 **Demo mode** with focus-topic scenarios
- 🐳 **Docker-first deployment** — single container, single port

It reduces friction, increases confidence, and aligns recommendations with actual observed usage, not speculation.

---

## PRD Governance Addendum (v1.1 Planning)

### 1) PRD Hierarchy (Single Source of Truth)

Use this document as the **product-level source of truth**. Feature PRDs define implementation details and must link back to requirement IDs here.

| Document | Purpose | Owner | Status |
|---|---|---|---|
| `PRD.md` | Product vision, release plan, global requirements, KPIs | PM | Canonical |
| `docs/features-prd/PRD-auto-discovery-live-connect.md` | Live-connect discovery UX and backend integration | Eng + PM | Active |
| `docs/features-prd/PRD-breakeven-slider.md` | Interactive cost decision UX | Eng + PM | Active |
| `docs/PRD-regional-pricing-deploy-types-export.md` | Pricing correctness + export workflows | Eng + PM | Active |

### 2) Release Scope and Exit Criteria

| Milestone | In Scope | Out of Scope | Exit Criteria |
|---|---|---|---|
| **MVP (Complete)** | 4-dimension analysis, demo/live analysis, recommendation output, explainability | Live pricing API, enterprise discount overrides, multi-deployment compare | Existing MVP acceptance tests pass |
| **v1.1** | Auto-discovery live connect, break-even slider/curve, automatic assumptions recompute | Programmatic API, scheduler | P95 interaction latency targets met, no blocking UX defects |
| **v1.2** | Regional/deployment-aware pricing, CSV/JSON export, policy version in outputs | Auto PTU purchase/sizing commitments | 95% cost parity (within tolerance) against reference calculator |

### 3) Requirement ID Taxonomy

Every new requirement in feature PRDs must map to one of these prefixes:

- `REQ-DEC-*` Decision quality and scoring logic
- `REQ-UX-*` User experience and interaction behavior
- `REQ-COST-*` Cost model, pricing, break-even correctness
- `REQ-DATA-*` Data collection, schema, and data quality behavior
- `REQ-OBS-*` Observability and telemetry
- `REQ-SEC-*` Security, privacy, and compliance

Minimum traceability format per requirement:

`Requirement ID → Module/File → Test Case ID → KPI`

### 4) Canonical Analysis Data Contract

All UI/report/export surfaces must conform to a versioned contract.

```json
{
  "contract_version": "2.1.0",
  "policy_version": "decision-policy-2026-03-01",
  "metadata": {
    "generated_at": "ISO-8601",
    "analysis_period_days": 14,
    "mode": "demo|live"
  },
  "recommendation": {
    "verdict": "PTU_RECOMMENDED|BORDERLINE|PTU_NOT_RECOMMENDED",
    "confidence": 0.0,
    "summary": "string"
  },
  "dimensions": [
    {
      "name": "Workload Shape",
      "score": "positive|neutral|negative|insufficient",
      "confidence": 0.0,
      "summary": "string",
      "explanation": "string",
      "key_metrics": {}
    }
  ],
  "cost_analysis": {},
  "metrics": {}
}
```

Compatibility policy:
- Patch (`x.y.Z`): additive fields only
- Minor (`x.Y.z`): additive + optional behavior flags
- Major (`X.y.z`): breaking field/schema changes (requires migration notes)

### 5) Decision Policy Versioning

Every recommendation output must include:
- `policy_version`
- threshold snapshot reference (or hash)
- data quality classification used in the decision

This enables auditability and support investigations when decisions differ over time.

### 6) Performance Budgets (Product SLOs)

| Journey | Budget | Metric |
|---|---|---|
| Time to initial recommendation render | ≤ 5s (p95, cached auth) | `ui.analysis.ttfr_ms` |
| Assumption change to updated cost section | ≤ 500ms (p95) | `ui.cost.recalc_ms` |
| Break-even chart interaction response | ≤ 250ms (p95) | `ui.chart.interaction_ms` |
| Export generation (CSV/JSON) | ≤ 2s (p95) | `ui.export.duration_ms` |

### 7) Observability Requirements

Required product events (min set):
- `analysis_run_started`
- `analysis_run_completed`
- `analysis_run_failed`
- `assumption_changed`
- `export_requested`
- `export_completed`

Minimum dimensions:
- mode (`demo|live`)
- region
- deployment_type
- recommendation
- policy_version

### 8) Security & Privacy Requirements

- Never log credentials, tokens, or raw secrets.
- Export artifacts must exclude subscription secrets and auth context.
- PII in free-text fields must be redacted before telemetry emission.
- Retention: product telemetry retained per organizational policy; no customer prompts or tokens stored by default.

### 9) Definition of Done (Global Template)

A feature is complete only when all are true:

- [ ] Requirement IDs assigned and traceability table updated
- [ ] Unit + integration tests added for each acceptance criterion
- [ ] Performance budget checks run and recorded
- [ ] Observability events emitted and validated
- [ ] Security/privacy checklist reviewed
- [ ] UX copy reviewed for clarity and non-generic tone
- [ ] Release notes + rollback plan documented
