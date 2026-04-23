# PTU Advisor - Comprehensive Codebase Overview

## 🗺️ Codebase Overview

**PTU Advisor** is an automated, data-driven decision tool for Azure AI Foundry customers to determine whether to use **Provisioned Throughput Units (PTU)** or **Pay-As-You-Go (PAYG)** pricing for their deployments.

The tool analyzes real deployment metrics across **four dimensions** (Workload Shape, Capacity Pressure, Latency Sensitivity, Load Predictability), computes break-even analysis with hybrid PTU + spillover cost models, and delivers recommendations through three interfaces: a **React Dashboard**, **FastAPI** REST API, and **CLI** (Typer).

- **Project Status**: MVP Complete (v0.1.0) with 9+ feature PRDs in various stages
- **Code Size**: ~12.6K lines of Python backend + ~7.5K lines of tests + React/TypeScript frontend
- **Last Major Update**: March 31, 2026 (Break-even cost explorer, live pricing fetch, multi-deployment consolidation)

---

## 🏗️ Architecture

**Layered Architecture** with clear separation of concerns:

```
┌─ Presentation Layer ─────────────────────┐
│  React Dashboard (frontend/)              │
│  FastAPI REST API (ptu_advisor/api/)      │
│  CLI (ptu_advisor/cli.py)                 │
├─ Orchestration Layer ────────────────────┤
│  API Server (routes, request shaping)     │
│  Decision Engine (ptu_advisor/analysis/)  │
├─ Business Logic Layer ───────────────────┤
│  4-Dimension Scoring (dimensions.py)      │
│  Cost Calculator (cost/calculator.py)     │
│  Pricing Resolver (cost/price_resolver.py)│
├─ Data Collection Layer ──────────────────┤
│  Metrics Collector (metrics/collector.py) │
│  Azure Resource Discovery                 │
│  Demo Data Generator (demo.py)            │
└─ Infrastructure Layer ──────────────────┘
   Azure Monitor, Auth, LLM Providers
```

**Design Philosophy**:
- Core business logic (analysis, cost math) is **testable and reusable**
- Decoupled from UI — same decision engine powers CLI, API, and Dashboard
- **Demo mode** mirrors live mode; scenarios share the same execution path
- **Extensible**: New dimensions, pricing models, or interfaces add incrementally

---

## 🛠️ Technology Stack

### Backend (Python)
- **Framework**: FastAPI 0.116.0 (API server) + Uvicorn (ASGI server)
- **CLI**: Typer 0.9.0 (command-line interface)
- **Data Processing**: NumPy 1.26+, Pandas 2.1+, SciPy (implicit via NumPy)
- **Azure SDKs**:
  - `azure-identity` 1.15+ (authentication, DefaultAzureCredential)
  - `azure-mgmt-monitor` 6.0+ (metrics retrieval)
  - `azure-mgmt-cognitiveservices` 13.5+ (resource discovery)
  - `azure-mgmt-subscription` 3.0+ (subscription listing)
- **Validation & Serialization**: Pydantic 2.5+ (request/response models)
- **Templating**: Jinja2 3.1+ (HTML report generation)
- **Visualization**: Matplotlib 3.8+ (chart generation for reports)
- **HTTP Client**: httpx 0.27+ (for live pricing API calls)
- **LLM Integration**: OpenAI SDK 1.12+ (optional, for narrative explanations)
- **Terminal UI**: Rich 13.7+ (console formatting, progress spinners)

### Frontend (React + TypeScript)
- **Framework**: React 19.2.0 with TypeScript 5.9.3
- **Build Tool**: Vite 7.1.11 (dev server + production build)
- **Charting**: ECharts 6.0.0 + echarts-for-react 3.0.6 (interactive charts)
- **Testing**: Vitest 2.1.8, Playwright 1.56.1 (e2e), React Testing Library 16.1.0
- **Linting**: ESLint 9.39.1 + TypeScript ESLint 8.48.0

### DevOps & Infrastructure
- **Containerization**: Docker (multi-stage build) + Docker Compose
- **Python Version**: 3.9-3.12 (officially supported); runtime uses Python 3.11-slim
- **Package Manager**: `uv` (Python) + npm (Node.js)
- **Testing Framework**: pytest 7.4+ (Python) + Vitest (TypeScript)
- **Code Quality**: 
  - Ruff 0.1+ (linting, formatting)
  - MyPy 1.7+ (static type checking)
  - Pre-commit hooks (via `pre-commit` 3.6+)
- **CI/CD**: GitHub Actions (.github/workflows/)

---

## 📁 Directory Structure

```
ptu-advisor/
├── ptu_advisor/                    # Backend Python package
│   ├── __init__.py
│   ├── cli.py                      # Typer CLI commands (analyze, demo-list, demo, etc.)
│   ├── config.py                   # ThresholdConfig, ModelCapacityConfig, AnalysisConfig
│   ├── auth.py                     # Azure authentication (DefaultAzureCredential, validation)
│   ├── demo.py                     # 15+ demo scenarios (ptu-recommended, cost-high-volume, etc.)
│   ├── discovery.py                # Azure resource discovery (subscriptions, accounts, deployments)
│   │
│   ├── api/
│   │   ├── server.py               # FastAPI app, endpoints, request/response schemas
│   │   └── __init__.py
│   │
│   ├── analysis/                   # 4-dimension scoring engine
│   │   ├── engine.py               # DecisionEngine: orchestrates dimension analysis
│   │   ├── dimensions.py           # WorkloadShapeAnalyzer, CapacityPressureAnalyzer, etc.
│   │   ├── rule_explainer.py       # Text explanation generation for dimensions
│   │   └── __init__.py
│   │
│   ├── cost/                       # Cost calculation & pricing
│   │   ├── calculator.py           # PTU/PAYG break-even, spillover cost, cost curves (v1 & v2)
│   │   ├── price_resolver.py       # Live pricing via Azure Retail Prices API + static fallback
│   │   ├── pricing.py              # REGION_CONFIGS, DEPLOYMENT_TYPE_CONFIGS
│   │   └── __init__.py
│   │
│   ├── metrics/                    # Data collection and merging
│   │   ├── collector.py            # MetricsCollector: fetches from Azure Monitor
│   │   ├── models.py               # TimeSeries, DeploymentMetrics, AnalysisResult
│   │   ├── merge.py                # Consolidation: merge multiple deployments' metrics
│   │   └── __init__.py
│   │
│   ├── llm/                        # Optional LLM-powered explanations
│   │   ├── provider.py             # Abstract LLMProvider, AzureOpenAIProvider, MockProvider
│   │   ├── explainer.py            # LLM-based narrative generation
│   │   ├── prompts.py              # System & user prompts for LLM
│   │   └── __init__.py
│   │
│   ├── visualization/              # Chart and report generation
│   │   ├── charts.py               # ChartGenerator: matplotlib-based visualizations
│   │   └── __init__.py
│   │
│   ├── report/                     # HTML report generation
│   │   ├── generator.py            # ReportGenerator: Jinja2 templates → HTML
│   │   ├── templates/              # HTML/Jinja2 report templates
│   │   │   ├── recommendation.html
│   │   │   ├── charts.html
│   │   │   ├── cost_summary.html
│   │   │   └── footer.html
│   │   └── __init__.py
│   │
│   └── dashboard/                  # Streamlit dashboard (legacy/alternative UI)
│       ├── app.py
│       └── __init__.py
│
├── frontend/                        # React + TypeScript SPA
│   ├── src/
│   │   ├── App.tsx                 # Main app component, routing, state management
│   │   ├── main.tsx                # React 19 entry point with React.createRoot
│   │   ├── types.ts                # TypeScript interfaces (AnalysisResponse, ConsolidationSummary, etc.)
│   │   ├── api.ts                  # HTTP client functions (fetch wrappers for /api/*)
│   │   ├── telemetry.ts            # Event emission for analytics
│   │   │
│   │   ├── charts/                 # ECharts-based visualization components
│   │   │   ├── TokenVolumeChart.tsx         # TPM/RPM over time
│   │   │   ├── DailyCostChart.tsx           # Daily cost breakdown
│   │   │   ├── RequestOutcomesChart.tsx     # Success/throttle/error rates
│   │   │   ├── ThrottleChart.tsx            # 429 rate trends
│   │   │   ├── TpmBandChart.tsx             # Min/avg/max TPM bands
│   │   │   ├── CostCurveChart.tsx           # Break-even curve (PTU vs PAYG)
│   │   │   ├── LatencyOverlayChart.tsx      # P50/P95/P99 latency
│   │   │   ├── echarts-setup.ts             # Global ECharts theme config
│   │   │   ├── theme.ts                     # Color palettes, styling
│   │   │   ├── use-chart-zoom.ts            # Chart zoom/pan hook
│   │   │   └── index.ts                     # Exports
│   │   │
│   │   ├── ExportReport.tsx         # Export as PDF/HTML
│   │   ├── ExportReport.test.tsx    # Export tests
│   │   ├── eligibility.test.tsx     # PTU model eligibility gate tests
│   │   ├── App.test.tsx             # App-level tests
│   │   ├── ui-enhancements.test.tsx # UI feature tests
│   │   └── test/
│   │       └── setup.ts             # Vitest setup
│   │
│   ├── package.json                # Dependencies, scripts (dev, build, test, test:e2e)
│   ├── package-lock.json           # Lock file
│   ├── vite.config.ts              # Vite build config, API proxy settings
│   ├── tsconfig.json               # TypeScript compiler config
│   ├── eslint.config.js            # ESLint rules
│   ├── vitest.config.ts            # Vitest test runner config
│   ├── playwright.config.ts        # Playwright e2e test config
│   ├── dist/                       # (generated) Built SPA served by FastAPI
│   └── node_modules/               # (generated) npm dependencies
│
├── tests/                          # Backend Python tests (pytest)
│   ├── test_analysis_explainer.py         # Tests for rule_explainer.py
│   ├── test_api_server.py                 # FastAPI endpoint tests
│   ├── test_auth.py                       # Azure auth tests
│   ├── test_charts.py                     # Visualization tests
│   ├── test_collector.py                  # Metrics collection tests
│   ├── test_config.py                     # Config validation tests
│   ├── test_consolidation_api.py          # Multi-deployment consolidation tests (P1 feature)
│   ├── test_cost_calculator.py            # Cost calculation unit tests (v1 & v2)
│   ├── test_cost_functions.py             # Cost function regression tests
│   ├── test_demo_scenarios.py             # Demo scenario data generation
│   ├── test_dimensions.py                 # Dimension analyzer tests
│   ├── test_dimensions_expanded.py        # Extended dimension test coverage
│   ├── test_discovery.py                  # Azure discovery mocking
│   ├── test_eligibility.py                # PTU model eligibility gating
│   ├── test_engine.py                     # DecisionEngine tests
│   ├── test_engine_expanded.py            # Extended engine coverage
│   ├── test_llm_provider.py               # LLM provider (mock, azure, openai)
│   ├── test_merge.py                      # Consolidation math & merging
│   ├── test_models.py                     # Data model (de)serialization
│   ├── test_price_resolver.py             # Pricing resolver tests
│   ├── test_price_resolver_integration.py # Live pricing API integration tests
│   ├── test_report_generator.py           # Report generation tests
│   └── __init__.py
│
├── docs/                           # Documentation and PRDs
│   ├── PRD.md                      # Main Product Requirements Document (MVP complete)
│   ├── gap-analysis-ptucalc.md     # Competitive analysis vs ptucalc.com
│   ├── ux-7-scenario-cost-comparison.md  # UX spec for scenario comparison
│   │
│   └── features-prd/               # Individual feature PRDs
│       ├── PRD-multi-deployment-consolidation.md     ✅ Phase 3 Complete (v1.2)
│       ├── PRD-ptu-model-eligibility.md              ✅ Complete (v1.0)
│       ├── PRD-breakeven-cost-explorer.md            ✅ Complete (v1.1) — break-even curves, safety verdicts
│       ├── PRD-live-pricing-fetch.md                 ✅ Complete (v1.0) — Azure Retail Prices API
│       ├── PRD-daily-cost-chart.md                   ✅ Complete (v1.0) — daily cost breakdown
│       ├── PRD-chart-overhaul-timeframe-selection.md ✅ Complete (v1.0) — chart interactivity
│       ├── PRD-export-report.md                      ✅ Complete (v1.0) — HTML/PDF export
│       ├── PRD-auto-discovery-live-connect.md        📋 Draft — live Azure discovery
│       ├── PRD-regional-pricing-deploy-types-export.md  (supplementary)
│       └── screenshot/                        # Screenshots for design specs
│
├── docker/                         # (implicit) Docker configuration
│   └── (files in root: Dockerfile, docker-compose.yml, .dockerignore)
│
├── .github/                        # GitHub Actions workflows
│   ├── workflows/
│   │   └── (CI/CD pipelines — may exist)
│   └── ...
│
├── .agents/                        # Custom skills for copilot/Claude
│   └── skills/
│       ├── ptu-advisor/            # Main skill definition
│       ├── frontend-design/
│       ├── frontend-ui-dark-ts/
│       ├── react/
│       ├── pydantic-models-py/
│       ├── test-driven-development/
│       ├── refactor/
│       ├── prd/
│       └── skill-creator/
│
├── outputs/                        # (generated) Report and data exports
│   ├── reports/
│   ├── charts/
│   └── ...
│
├── pyproject.toml                  # Python package metadata, dependencies, build config
├── uv.lock                         # Python dependency lock file (uv)
├── Dockerfile                      # Multi-stage build (Node → Python → runtime)
├── docker-compose.yml              # Local dev/demo orchestration
├── docker-ignore                   # Docker build exclusions
├── .gitignore                      # Git exclusions
├── README.md                       # Main project documentation (comprehensive)
├── opencode.json                   # Config for OpenCode integrations
├── skills-lock.json                # Locked skill definitions
└── .venv/                          # (local) Virtual environment for dev

```

---

## 🔑 Key Entry Points & Files

### Backend Entry Points

1. **API Server** (`ptu_advisor/api/server.py`)
   - FastAPI application with CORS middleware
   - Main endpoints: `/api/health`, `/api/analyze`, `/api/consolidation`, `/api/discovery/*`, `/api/pricing/*`
   - Handles request validation, response shaping, error handling
   - Returns JSON: `AnalysisResponse`, `ConsolidationSummary`

2. **CLI Entry Point** (`ptu_advisor/cli.py`)
   - Typer CLI with commands: `analyze`, `demo`, `demo-list`
   - Output: console tables (Rich) + HTML reports
   - Supports live Azure analysis or demo scenarios

3. **Decision Engine** (`ptu_advisor/analysis/engine.py`)
   - Core logic: orchestrates 4-dimension scoring
   - Input: `DeploymentMetrics` (from Azure or demo)
   - Output: `AnalysisResult` with recommendation, confidence, explanations
   - Reused by API, CLI, and potentially third-party integrations

4. **Demo Generator** (`ptu_advisor/demo.py`)
   - 15+ pre-configured scenarios with realistic workload patterns
   - Generates synthetic `DeploymentMetrics` for testing/demo without Azure access
   - Supports focus topics: Cost Reduction, Throttling, Latency, Predictable Billing, etc.

### Frontend Entry Points

1. **App Component** (`frontend/src/App.tsx`)
   - Main React component with state management (useState)
   - Handles routing between Deployment Advisor and PTU Calculator modes
   - Orchestrates data flow: discovery → selection → analysis → results

2. **API Client** (`frontend/src/api.ts`)
   - HTTP wrapper functions (`fetchAnalyze`, `fetchConsolidation`, `fetchDiscovery`, etc.)
   - Handles timeout, error responses, type safety
   - Proxies to `/api/*` endpoints (routed through Vite dev server or FastAPI in production)

### Configuration & Models

1. **Config** (`ptu_advisor/config.py`)
   - `ThresholdConfig`: dimension scoring thresholds (CV, throttling, latency)
   - `ModelCapacityConfig`: PTU specs per model (gpt-4o, gpt-4.1, o1, etc.)
   - `AnalysisConfig`: runtime parameters (lookback_days, subscription_id, etc.)

2. **Data Models** (`ptu_advisor/metrics/models.py`)
   - `TimeSeries`: metric time series with statistics (mean, p95, cv, etc.)
   - `DeploymentMetrics`: aggregated metrics for a deployment
   - `AnalysisResult`: complete recommendation with dimensions & explanations
   - `DimensionScore`: enum (POSITIVE, NEUTRAL, NEGATIVE, INSUFFICIENT)

3. **TypeScript Types** (`frontend/src/types.ts`)
   - `AnalysisResponse`: matches backend `AnalysisResponse` schema
   - `ConsolidationSummary`: consolidation mode results
   - `FocusTopic`, `PricingRegion`, `DeploymentTypeOption`: UI model data

---

## 🔗 Module Relationships

### Data Flow

```
Azure Monitor / Demo
    ↓
MetricsCollector (metrics/collector.py)
    ↓
DeploymentMetrics (metrics/models.py)
    ↓
DecisionEngine (analysis/engine.py)
  ├─ WorkloadShapeAnalyzer
  ├─ CapacityPressureAnalyzer
  ├─ LatencySensitivityAnalyzer
  └─ LoadPredictabilityAnalyzer
    ↓
AnalysisResult (dimensions + recommendation)
    ↓
CostCalculator (cost/calculator.py)
    ├─ calculate_spillover_cost()
    ├─ calculate_break_even()
    └─ generate_cost_curves()
    ↓
API Server / CLI / Dashboard
    ↓
Frontend / Reports / JSON
```

### Dependencies

- **API Server** depends on:
  - `DecisionEngine`, `MetricsCollector` (core logic)
  - `CostCalculator`, `PricingResolver` (cost analysis)
  - `Discovery` module (resource lookup)
  - `Demo` module (demo scenarios)
  - `LLM` providers (optional)

- **DecisionEngine** depends on:
  - `DeploymentMetrics`, `TimeSeries` (data models)
  - `Dimension` analyzers (scoring logic)
  - `ThresholdConfig` (tunable thresholds)

- **CostCalculator** depends on:
  - `PricingResolver` (for live pricing)
  - `ModelCapacityConfig` (for model specs)

- **Frontend** depends on:
  - `api.ts` (HTTP client)
  - `types.ts` (TypeScript interfaces)
  - ECharts (visualization)
  - React Testing Library (for tests)

### Consolidation (Multi-Deployment) Flow

1. User selects 2+ deployments of same model in UI
2. `POST /api/consolidation` with deployment list
3. `MetricsCollector` fetches metrics for each independently
4. `merge_deployment_metrics()` (metrics/merge.py) combines time-series
5. `DecisionEngine.analyze()` on merged metrics
6. `ConsolidationSummary` includes per-deployment attribution + combined recommendation

---

## 📝 Notable Observations

### 1. **Core Strengths**

- **Testability**: Business logic isolated from UI; high test coverage (22 test files, 7.5K lines)
- **Multi-Interface Design**: Same engine powers CLI, API, and Dashboard — zero duplication
- **Demo-First Approach**: Realistic scenarios enable offline testing, demos, and CI/CD without Azure
- **Transparent Cost Math**: Break-even, spillover, and PTU sizing are fully auditable
- **Live Pricing Integration**: Fetches real regional pricing via Azure Retail Prices API; falls back to static configs
- **Extensible Pricing**: Regional multipliers, deployment types (global/data-zone/regional), reservation terms

### 2. **Implementation Status**

**MVP Features (Complete ✅)**:
- ✅ 4-dimension recommendation model
- ✅ Break-even analysis with spillover cost modeling
- ✅ Live Azure discovery (subscriptions, accounts, deployments)
- ✅ Demo mode with 15+ scenarios
- ✅ CLI with HTML report generation
- ✅ FastAPI REST API with Pydantic validation
- ✅ React dashboard with interactive charts (ECharts)
- ✅ PTU model eligibility gating (PRD-ptu-model-eligibility.md)
- ✅ Multi-deployment consolidation (test_consolidation_api.py, PRD-multi-deployment-consolidation.md)
- ✅ Live pricing fetching (PricingResolver, PRD-live-pricing-fetch.md)
- ✅ Break-even cost explorer with fixed-PTU curves (calculator v2)
- ✅ Daily cost chart breakdown
- ✅ Export report (HTML/PDF)

**In Progress / Planned**:
- 📋 Auto-discovery UI refinements (PRD-auto-discovery-live-connect.md — Draft)
- 📋 1-Year and 3-Year PTU reservation terms (gap analysis notes)
- 📋 More detailed scenario/UX flows (ux-7-scenario-cost-comparison.md)

### 3. **Code Quality & Patterns**

- **Type Safety**: Full MyPy compliance (`disallow_untyped_defs: true`), comprehensive TypeScript coverage
- **Validation**: Pydantic v2 with strict validation on all API inputs
- **Testing Strategy**: Unit tests for dimensions, cost math, API endpoints; integration tests for Azure SDK; E2E tests via Playwright
- **Logging**: Rich console output with progress spinners; structured error messages
- **Error Handling**: Custom `AuthenticationError`, `MetricsCollectionError`; graceful fallbacks
- **Config Management**: Environment variables + hardcoded sensible defaults; no secrets in code

### 4. **Architectural Decisions Worth Understanding**

1. **Spillover Model**: PTU is sized to P50/P75 baseline (not peak), overflow spills to PAYG. This is Microsoft's official guidance.
2. **Cost-Optimal Sweep**: For a given percentile baseline, the calculator sweeps PTU levels to find the minimum total cost (PTU + spillover).
3. **Data Quality Scoring**: Recommendation includes a `confidence` field based on data point count and span; users know when they need more data.
4. **Dimension Independence**: Each of the 4 dimensions scores independently (POSITIVE/NEUTRAL/NEGATIVE); recommendation logic combines scores (≥3 positive = PTU Recommended).
5. **Demo-as-First-Class**: Not an afterthought; same execution path as live mode, ensuring consistency.

### 5. **Potential Gaps & TODOs**

- **No detected TODO/FIXME comments** in backend code (clean!)
- **Future gap**: 1-Year and 3-Year PTU reservation pricing terms currently hardcoded; could be more flexible (see gap-analysis-ptucalc.md)
- **Consideration**: KQL query support (ptucalc.com offers pre-built KQL; we only support Azure SDK discovery)
- **Consideration**: Custom model pricing (currently tied to `MODEL_CAPACITY_CONFIGS` hardcoded list)

### 5b. **Recent Bug Fixes (April 2026 Session)**

The following bugs were identified and fixed on the landing page ("Connect to Azure" flow):

| Bug | Root Cause | Fix Location |
|-----|-----------|--------------|
| **403 on subscription discovery** | `azure-mgmt-subscription` missing from local venv (listed in pyproject.toml but not installed) | `pip install azure-mgmt-subscription` (runtime fix) |
| **Refresh button not re-fetching** | Auth status `useEffect` dep array was `[mode]` — missing `discoveryKey`, so clicking Refresh didn't re-trigger auth or subscription fetch | `frontend/src/App.tsx:641` — changed to `[mode, discoveryKey]` |
| **"No subscriptions found" shown during loading** | No loading/fetching state — empty-list placeholder appeared immediately while fetch was in-flight | `frontend/src/App.tsx` — added `subscriptionsLoading` state + conditional "Loading subscriptions..." message |
| **Duplicate API calls on page load** | React StrictMode double-mounts effects in dev mode (React 19 standard behavior) | Not a bug — dev-only, no production impact |

### 6. **Testing Infrastructure**

- **Backend**: 22 test files covering dimensions, cost calc, API, discovery, consolidation, eligibility
- **Frontend**: Vitest + React Testing Library for unit tests; Playwright for E2E
- **Integration**: Live pricing API integration tests with mock caching
- **CI/CD Ready**: Docker multi-stage build, pytest markers for integration vs unit tests

### 7. **Deployment & Operations**

- **Single Docker Image**: Multi-stage build produces one ~800MB image with both backend and frontend
- **Health Check**: `/api/health` endpoint with Docker HEALTHCHECK
- **Host Azure Auth**: Compose mounts `~/.azure` so container can use host's `az login`
- **Output Artifacts**: Reports generated to `/app/outputs` (mounted volume in Compose)
- **Non-Root User**: Container runs as `advisor:advisor` (UID 1000) for security

---

## 📊 Codebase Statistics

| Metric | Value |
|--------|-------|
| **Backend Python LOC** | ~12,587 (ptu_advisor/) |
| **Test LOC** | ~7,548 (tests/) |
| **Test Files** | 22 files |
| **Test/Code Ratio** | ~60% |
| **Frontend Source Files** | ~20 TSX/TS files |
| **Main API Endpoints** | 6+ endpoints |
| **Demo Scenarios** | 15+ configurations |
| **Supported Models** | 9 models (gpt-5, gpt-4.1, gpt-4o, o1, o3-mini, o4-mini, etc.) |
| **Pricing Regions** | 35+ regions with multipliers |
| **Deployment Types** | 3 (global, data_zone, regional) |

---

## 🎯 Feature PRDs & Status Summary

| Feature | File | Status | Version |
|---------|------|--------|---------|
| Core MVP | PRD.md | ✅ Complete | 1.0 |
| Multi-Deployment Consolidation | PRD-multi-deployment-consolidation.md | ✅ Phase 3 Complete | 1.2 |
| PTU Model Eligibility | PRD-ptu-model-eligibility.md | ✅ Complete | 1.0 |
| Break-Even Cost Explorer | PRD-breakeven-cost-explorer.md | ✅ Complete | 1.1 |
| Live Pricing Fetch | PRD-live-pricing-fetch.md | ✅ Complete | 1.0 |
| Daily Cost Chart | PRD-daily-cost-chart.md | ✅ Complete | 1.0 |
| Chart Overhaul & Timeframe Selection | PRD-chart-overhaul-timeframe-selection.md | ✅ Complete | 1.0 |
| Export Report | PRD-export-report.md | ✅ Complete | 1.0 |
| Auto-Discovery & Live Connect | PRD-auto-discovery-live-connect.md | 📋 Draft | N/A |
| Regional Pricing & Deploy Types | PRD-regional-pricing-deploy-types-export.md | (Supplementary) | N/A |

---

## 🚀 Quick Start Commands

```bash
# Local Dev - Backend
cd ptu_advisor && python -m venv .venv
source .venv/bin/activate && pip install -e ".[dev]"
uvicorn ptu_advisor.api.server:app --reload --port 8000

# Local Dev - Frontend  
cd frontend && npm install && npm run dev
# Dev server on http://localhost:5173

# Docker (Recommended)
docker compose up --build
# App on http://localhost:8000

# CLI - Demo mode
ptu-advisor demo --scenario ptu-recommended

# CLI - Live analysis
ptu-advisor analyze \
  --resource-group my-rg \
  --workspace my-workspace \
  --deployment gpt-4o-prod \
  --days 14

# Run tests
pytest tests/
cd frontend && npm test
```

---

## 📚 Key Files to Read First

1. **README.md** — Comprehensive user-facing documentation
2. **docs/PRD.md** — Original product requirements (defines the 4 dimensions)
3. **ptu_advisor/config.py** — All configurable thresholds and model capacity specs
4. **ptu_advisor/analysis/engine.py** — How recommendations are computed
5. **ptu_advisor/cost/calculator.py** — Cost modeling and break-even logic
6. **frontend/src/App.tsx** — Main React component and UI flow
7. **tests/test_cost_calculator.py** — Best examples of cost calculation validation

---

## 🔐 Security & Dependencies

- **Azure Auth**: Uses DefaultAzureCredential chain (CLI, managed identity, service principal, user credentials)
- **No Credentials in Code**: All secrets via environment variables or `.env` file
- **Dependency Management**: 
  - Python: pinned via `uv.lock`; minimal Azure SDK surface (only mgmt + identity)
  - Node: standard npm lock file
- **Container Security**: Non-root user, slim base images, health checks

---

## 📞 Contact & Contribution

- **Maintainers**: Microsoft PTU Advisor Team
- **License**: MIT
- **Contributing**: Fork → feature branch → tests → PR
- **Issues**: GitHub issues (standard workflow)

