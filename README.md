# PTU Advisor: PTU vs PAYG Decisioning for Azure AI Foundry

[![Run with Docker](https://img.shields.io/static/v1?style=for-the-badge&label=Docker&message=Run+Locally&color=2496ED&logo=docker)](#quick-start-docker-recommended)
[![Local Dev Setup](https://img.shields.io/static/v1?style=for-the-badge&label=Local+Dev&message=Python+%2B+React&color=brightgreen&logo=visualstudiocode)](#local-development)
[![CLI + API + Dashboard](https://img.shields.io/static/v1?style=for-the-badge&label=Interfaces&message=CLI+API+Dashboard&color=blue)](#capabilities)

PTU Advisor helps you decide when to use **Provisioned Throughput Units (PTU)** versus **Pay-As-You-Go (PAYG)** for Azure AI Foundry deployments.

It combines Azure usage metrics, 4-dimension scoring, break-even analysis, and hybrid spillover modeling to produce clear recommendations with confidence and cost impact.

## Capabilities

PTU Advisor provides three delivery surfaces over one analysis engine:

| Surface | Tech | Primary Use | Output |
|---|---|---|---|
| **Dashboard** | React + TypeScript | Interactive exploration and what-if analysis | Cost curves, break-even point, scoring breakdown |
| **API** | FastAPI | Integrations and programmatic analysis | JSON recommendation payloads |
| **CLI** | Typer | Terminal-first workflows and reports | Console summaries + HTML report |

Core analysis includes:

- **4-dimension recommendation model** (Workload Shape, Capacity Pressure, Latency Sensitivity, Load Predictability)
- **Hybrid PTU + spillover PAYG cost model**
- **Break-even TPM calculation and baseline PTU sensitivity**
- **Auto-discovery for subscriptions, accounts, and deployments**
- **Optional LLM-powered narrative explanation**

---

## Prerequisites

Before running PTU Advisor, prepare the following.

### Required Tooling

- Python 3.11+
- Node.js 18+ and npm
- Docker + Docker Compose (for containerized run)

### Azure Access (for live analysis)

- Azure subscription access to the target AI Foundry / Azure OpenAI resources
- Azure CLI installed and authenticated (**required before `docker compose up` when using live Azure mode**):

```shell
az login
az account show
```

### Optional Environment Variables

Create a `.env` file in the project root when using service principals or optional LLM explanations:

```env
# Azure credentials (optional if using az login + user context)
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_SUBSCRIPTION_ID=...

# Optional LLM narrative explanation
AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

---

## Quick Start: Docker (recommended)

### Use host Azure CLI login with Docker

Yes — this repository supports host-based Azure CLI auth with Docker.

> **Important:** For live Azure discovery/analysis, `az login` on the host is a prerequisite to `docker compose up`.
> Without a valid host login, setup/discovery endpoints will fail in live mode.

1. Authenticate on your host machine:

```shell
az login
az account set --subscription <your-subscription-id>
```

2. Start the stack:

```shell
docker compose up --build
```

The compose file mounts your host `~/.azure` into the container and sets `AZURE_CONFIG_DIR`, so discovery and live analysis can use the same signed-in context.

If you only want demo mode, Azure login is not required.

The web service is published on host loopback only and uses `PTU_ADVISOR_AUTH_MODE=local`. Authentication fails closed when this setting is omitted.

For an Azure App Service deployment, enable App Service Authentication with **Require authentication**, prevent direct access that bypasses App Service, and configure:

- `PTU_ADVISOR_AUTH_MODE=easy_auth`
- `PTU_ADVISOR_REQUIRED_APP_ROLE=PTUAdvisor.User` (or your configured Entra app role)
- `PTU_ADVISOR_ALLOWED_SUBSCRIPTION_IDS=<subscription-id>[,<subscription-id>...]`

In Easy Auth mode, every API endpoint except `/api/health` requires an authenticated principal with the configured app role. Live Azure operations are restricted to the configured subscription allowlist.

### 1. Launch the full application

```shell
docker compose up
```

The app is available at `http://localhost:8000`.

### 2. Build and run manually (alternative)

```shell
docker build -t ptu-advisor .
docker run -e PTU_ADVISOR_AUTH_MODE=local -p 127.0.0.1:8000:8000 ptu-advisor
```

### 3. Verify

Open `http://localhost:8000` and choose one of:

- **Deployment Advisor** (live Azure or demo scenarios)
- **PTU Calculator** (manual estimation, no Azure dependency)

### 4. Run CLI commands in Docker

```shell
# Run demo scenario
docker compose run --rm cli demo --scenario ptu-recommended

# List scenarios
docker compose run --rm cli demo-list

# Analyze live deployment
docker compose run --rm cli analyze \
  --resource-group my-rg \
  --workspace my-workspace \
  --deployment gpt-4o-production
```

---

## Local Development

### 1. Backend setup (FastAPI)

```shell
cd ptu-recommander
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
PTU_ADVISOR_AUTH_MODE=local uvicorn ptu_advisor.api.server:app --reload --port 8000
```

### 2. Frontend setup (React + Vite)

```shell
cd frontend
npm install
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies `/api/*` to backend port `8000`.

### 3. CLI usage

```shell
# Demo mode
ptu-advisor demo --scenario ptu-recommended

# List demos
ptu-advisor demo-list

# Live deployment analysis
ptu-advisor analyze \
  --resource-group my-rg \
  --workspace my-workspace \
  --deployment gpt-4o-production \
  --days 14
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/focus-topics` | Demo focus topics |
| `GET` | `/api/pricing/options` | Regions and deployment types |
| `GET` | `/api/discovery/subscriptions` | List subscriptions |
| `GET` | `/api/discovery/accounts` | List Azure OpenAI accounts |
| `GET` | `/api/discovery/deployments` | List deployments |
| `POST` | `/api/analyze` | Run PTU vs PAYG analysis |

---

## Recommendation Model

PTU Advisor evaluates four dimensions and combines them into a recommendation:

| Dimension | Focus | PTU-Favorable Signal |
|---|---|---|
| **Workload Shape** | Throughput stability and variance | Stable, sustained demand |
| **Capacity Pressure** | Throttling and utilization pressure | Frequent saturation / 429s |
| **Latency Sensitivity** | Tail latency behavior (P95/P99) | High or unstable tail latency |
| **Load Predictability** | Regularity of demand patterns | Predictable baseline load |

Recommendation outcomes:

- ✅ **PTU Recommended**
- ⚠️ **Borderline**
- ❌ **PTU Not Recommended**

Cost outputs include:

- PAYG monthly estimate
- Hybrid PTU + spillover monthly estimate
- Break-even TPM
- Suggested baseline PTU and sensitivity curve

---

## Technical Architecture Overview

This solution uses a layered architecture so UI, API, and decision logic can evolve independently.

### Main Components

- **Frontend (`frontend/`)**: React dashboard for interactive analysis and PTU calculator
- **API (`ptu_advisor/api/server.py`)**: FastAPI orchestration layer and response shaping
- **Analysis Engine (`ptu_advisor/analysis/`)**: 4-dimension scoring and recommendation logic
- **Cost Engine (`ptu_advisor/cost/`)**: PTU sizing, break-even, and spillover calculations
- **Metrics & Discovery (`ptu_advisor/metrics/`, `ptu_advisor/discovery.py`)**: data collection and Azure resource discovery
- **Reports (`ptu_advisor/report/`)**: HTML report generation for CLI workflows

### Why this design?

- Keeps **cost math** and **recommendation scoring** testable and reusable
- Supports **multiple interfaces** (CLI, API, Dashboard) with a shared core
- Enables **demo mode** and **live Azure mode** with the same decision path

---

## Project Structure

```text
ptu-recommander/
├── ptu_advisor/
│   ├── api/server.py
│   ├── analysis/
│   ├── cost/
│   ├── metrics/
│   ├── report/
│   ├── visualization/
│   ├── cli.py
│   ├── config.py
│   ├── demo.py
│   └── discovery.py
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Development Workflow

### Run tests

```shell
# Backend
pytest

# Frontend
cd frontend && npm test
```

### Type checking and linting

```shell
# Backend static checks
mypy ptu_advisor
ruff check ptu_advisor
ruff format ptu_advisor

# Frontend type check + build
cd frontend && npx tsc -b --noEmit
cd frontend && npm run build
```

---

## Troubleshooting

### Authentication issues

```shell
az login
az account show
```

### Docker + Azure setup issues

For **live mode** with Docker, verify this order:

```shell
az login
az account set --subscription <your-subscription-id>
docker compose up --build
```

If discovery still fails:

- Confirm host Azure profile exists at `~/.azure`
- Rebuild the app image: `docker compose up -d --build`
- Check app logs: `docker compose logs -f app`

### Workspace or deployment not found

```shell
az cognitiveservices account show \
  --name my-workspace \
  --resource-group my-rg
```

### No metrics returned

- Ensure deployment has recent traffic
- Verify Azure Monitor metrics are available
- Confirm Reader+ access to the resource scope

### Docker startup issues

```shell
docker compose build --no-cache
docker compose logs -f
```

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add or update tests for your changes
4. Run backend/frontend test suites
5. Open a pull request

## License

MIT
