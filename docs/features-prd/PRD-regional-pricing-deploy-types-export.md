# PRD: Regional Pricing, Deployment Types & Report Export

> **Version**: 1.0  
> **Date**: February 9, 2026  
> **Author**: PTU Advisor Team  
> **Features Covered**: Gap Items #3 (Regional Pricing), #4 (Deployment Type Multipliers), #7 (CSV/JSON Export)

---

## 1. Executive Summary

### Problem Statement

PTU Advisor's cost calculations use hardcoded flat rates ($2.00/PTU-hr for Global, $1.50/PTU-hr for Regional) that do not account for Azure's region-specific pricing multipliers or deployment topology. Additionally, users cannot export analysis results in structured formats for sharing with finance teams and leadership. This undermines trust in cost figures and limits adoption in enterprise procurement workflows.

### Proposed Solution

Implement three interconnected features:
1. **Regional pricing multipliers** across 35 Azure regions
2. **Deployment type awareness** (Global, Data Zone, Regional) with correct rate structures
3. **CSV and JSON report export** from the Streamlit dashboard

### Success Criteria

| KPI | Target |
|---|---|
| Cost estimate accuracy vs Azure pricing calculator | ≥ 95% match within 5% tolerance |
| Region/deployment coverage | All 35 Azure OpenAI regions, 3 deployment types |
| Export format completeness | Exported file contains 100% of dashboard data points |
| Export round-trip time | < 2 seconds for CSV/JSON generation |
| User completion rate | > 80% of dashboard sessions produce an export (tracked via demo analytics) |

---

## 2. User Experience & Functionality

### User Personas

| Persona | Description | Primary Need |
|---|---|---|
| **Cloud Architect** | Designs Azure infrastructure, selects regions based on latency + compliance | Accurate per-region cost comparison to justify region selection |
| **FinOps Engineer** | Optimizes Azure spend, presents cost reports to leadership | Exportable, stakeholder-ready cost breakdowns |
| **Platform Team Lead** | Manages multiple deployments across regions | Compare Global vs Data Zone vs Regional deployment costs |

### User Stories

#### US-1: Region-Aware Cost Estimation

> As a **Cloud Architect**, I want to see cost estimates adjusted for my deployment's Azure region so that my budget projections match actual Azure invoices.

**Acceptance Criteria:**
- [ ] User can select from all Azure OpenAI regions (35 regions)
- [ ] Cost calculations apply the correct regional multiplier (e.g., Switzerland North = 1.2x)
- [ ] Default region is auto-detected from the deployment resource (when using live Azure data) or defaults to "East US" in demo mode
- [ ] Changing region recalculates all 7 pricing scenarios in < 500ms
- [ ] Region multiplier is displayed alongside cost figures (e.g., "East US (1.0x)")
- [ ] Tooltip explains what the regional multiplier means

#### US-2: Deployment Type Selection

> As a **Platform Team Lead**, I want to compare costs across Global, Data Zone, and Regional deployment types so that I can choose the most cost-effective topology.

**Acceptance Criteria:**
- [ ] Three deployment types available: Global, Data Zone, Regional
- [ ] Each type applies correct pricing:
  - Global: base rate × 1.0x, min PTU per model config, increment 5
  - Data Zone: base rate × 1.2x, min PTU per model config, increment 5  
  - Regional: separate rate structure, min PTU per model config, increment 50
- [ ] PTU sizing (minimum PTU, increment) adjusts per deployment type
- [ ] Cost comparison table shows all 3 types when expanded
- [ ] Default is "Global" (most common deployment type)

#### US-3: CSV Export

> As a **FinOps Engineer**, I want to export the analysis results as CSV so that I can import them into Excel for budget planning and share with non-technical stakeholders.

**Acceptance Criteria:**
- [ ] "Export CSV" button is visible in the dashboard sidebar or report section
- [ ] CSV file contains these sections with clear headers:
  - **Metadata**: Report date, model, deployment name, analysis period, region, deployment type
  - **Cost Breakdown**: All 7 scenarios with monthly/annual costs, savings %, commitment term
  - **Metrics Summary**: Avg TPM, Peak TPM, throttling rate, latency P50/P95/P99
  - **Recommendation**: Verdict, confidence, dimension scores
  - **Break-Even**: Break-even TPM, current TPM vs break-even ratio
- [ ] File name follows convention: `ptu-report-{deployment}-{date}.csv`
- [ ] Download triggers immediately (no server round-trip for generation)

#### US-4: JSON Export

> As a **Platform Team Lead**, I want to export analysis results as JSON so that I can feed them into automated pipelines or compare across deployments programmatically.

**Acceptance Criteria:**
- [ ] "Export JSON" button adjacent to CSV export
- [ ] JSON structure includes:
  ```json
  {
    "metadata": {
      "version": "2.0.0",
      "generated_at": "2026-02-09T12:00:00Z",
      "tool": "ptu-advisor",
      "model": "gpt-4o",
      "deployment": "prod-chat",
      "region": "eastus",
      "deployment_type": "global",
      "analysis_period_days": 14
    },
    "recommendation": {
      "verdict": "PTU_RECOMMENDED",
      "confidence": 0.87,
      "summary": "...",
      "dimensions": [...]
    },
    "cost_comparison": {
      "scenarios": [...],  // All 7
      "break_even_tpm": 32000,
      "cheapest_scenario": "spillover_1y"
    },
    "metrics": {
      "avg_tpm": 45000,
      "peak_tpm": 78000,
      "throttling_rate": 0.034,
      "latency_p50_ms": 180,
      "latency_p95_ms": 450,
      "latency_p99_ms": 890
    }
  }
  ```
- [ ] JSON is pretty-printed with 2-space indentation
- [ ] File name: `ptu-report-{deployment}-{date}.json`

### Non-Goals

- **Live Azure Retail Pricing API integration** — Deferred to Phase 3 (item #10). We will use a static pricing table that's manually updated, not live API calls.
- **Custom pricing overrides for enterprise agreements** — Deferred to Phase 2 (item #11).
- **PDF export** — Not in scope. CSV and JSON cover the primary use cases.
- **Multi-deployment comparison in a single export** — Each export covers one deployment. Cross-deployment comparison is a separate feature.

---

## 3. Technical Specifications

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  dashboard/app.py                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ Region   │  │ Deploy    │  │ Export            │  │
│  │ Selector │  │ Type Sel. │  │ CSV / JSON        │  │
│  └─────┬────┘  └────┬──────┘  └────────┬─────────┘  │
│        │             │                  │             │
│        ▼             ▼                  ▼             │
│  ┌─────────────────────────┐  ┌──────────────────┐   │
│  │   cost/engine.py        │  │ export/          │   │
│  │   calculate_all()       │  │  csv_exporter.py │   │
│  │   break_even()          │  │  json_exporter.py│   │
│  └──────────┬──────────────┘  └──────────────────┘   │
│             │                                         │
│             ▼                                         │
│  ┌─────────────────────────┐                          │
│  │   cost/pricing.py       │  ← NEW                  │
│  │   REGION_MULTIPLIERS    │                          │
│  │   DEPLOYMENT_CONFIGS    │                          │
│  │   PAYG_RATES            │                          │
│  └─────────────────────────┘                          │
└─────────────────────────────────────────────────────┘
```

### 3.2 New Module: `ptu_advisor/cost/pricing.py`

Central pricing configuration file. Single source of truth for all pricing data.

```python
"""Azure OpenAI pricing data — updated February 2026."""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class DeploymentType(Enum):
    GLOBAL = "global"
    DATA_ZONE = "data_zone"
    REGIONAL = "regional"


@dataclass(frozen=True)
class RegionConfig:
    name: str
    display_name: str
    multiplier: float   # Applied to base PTU rate
    zone: str           # "US", "Europe", "Asia Pacific", etc.


# 35 Azure OpenAI regions
REGION_CONFIGS: Dict[str, RegionConfig] = {
    "eastus": RegionConfig("eastus", "East US", 1.0, "US"),
    "eastus2": RegionConfig("eastus2", "East US 2", 1.0, "US"),
    "westus": RegionConfig("westus", "West US", 1.05, "US"),
    "westus2": RegionConfig("westus2", "West US 2", 1.0, "US"),
    "westus3": RegionConfig("westus3", "West US 3", 1.0, "US"),
    "centralus": RegionConfig("centralus", "Central US", 1.0, "US"),
    "northcentralus": RegionConfig("northcentralus", "North Central US", 1.0, "US"),
    "southcentralus": RegionConfig("southcentralus", "South Central US", 1.0, "US"),
    "canadacentral": RegionConfig("canadacentral", "Canada Central", 1.1, "Canada"),
    "canadaeast": RegionConfig("canadaeast", "Canada East", 1.1, "Canada"),
    "brazilsouth": RegionConfig("brazilsouth", "Brazil South", 1.15, "South America"),
    "northeurope": RegionConfig("northeurope", "North Europe", 1.05, "Europe"),
    "westeurope": RegionConfig("westeurope", "West Europe", 1.05, "Europe"),
    "uksouth": RegionConfig("uksouth", "UK South", 1.1, "Europe"),
    "ukwest": RegionConfig("ukwest", "UK West", 1.1, "Europe"),
    "francecentral": RegionConfig("francecentral", "France Central", 1.1, "Europe"),
    "germanywestcentral": RegionConfig("germanywestcentral", "Germany West Central", 1.1, "Europe"),
    "norwayeast": RegionConfig("norwayeast", "Norway East", 1.15, "Europe"),
    "switzerlandnorth": RegionConfig("switzerlandnorth", "Switzerland North", 1.2, "Europe"),
    "swedencentral": RegionConfig("swedencentral", "Sweden Central", 1.1, "Europe"),
    "eastasia": RegionConfig("eastasia", "East Asia", 1.1, "Asia Pacific"),
    "southeastasia": RegionConfig("southeastasia", "Southeast Asia", 1.05, "Asia Pacific"),
    "japaneast": RegionConfig("japaneast", "Japan East", 1.15, "Asia Pacific"),
    "japanwest": RegionConfig("japanwest", "Japan West", 1.15, "Asia Pacific"),
    "australiaeast": RegionConfig("australiaeast", "Australia East", 1.1, "Asia Pacific"),
    "australiasoutheast": RegionConfig("australiasoutheast", "Australia Southeast", 1.1, "Asia Pacific"),
    "koreacentral": RegionConfig("koreacentral", "Korea Central", 1.1, "Asia Pacific"),
    "koreasouth": RegionConfig("koreasouth", "Korea South", 1.1, "Asia Pacific"),
    "centralindia": RegionConfig("centralindia", "Central India", 1.05, "India"),
    "southindia": RegionConfig("southindia", "South India", 1.05, "India"),
    "westindia": RegionConfig("westindia", "West India", 1.05, "India"),
    "uaenorth": RegionConfig("uaenorth", "UAE North", 1.15, "Middle East"),
    "southafricanorth": RegionConfig("southafricanorth", "South Africa North", 1.2, "Africa"),
}


@dataclass(frozen=True)
class DeploymentTypeConfig:
    base_hourly_rate: float     # $/PTU/hour before region multiplier
    rate_multiplier: float      # Applied after region multiplier
    increment: int              # PTU increment (5 or 50)
    label: str


DEPLOYMENT_TYPE_CONFIGS: Dict[DeploymentType, DeploymentTypeConfig] = {
    DeploymentType.GLOBAL: DeploymentTypeConfig(1.00, 1.0, 5, "Global"),
    DeploymentType.DATA_ZONE: DeploymentTypeConfig(1.10, 1.0, 5, "Data Zone"),
    DeploymentType.REGIONAL: DeploymentTypeConfig(2.00, 1.0, 50, "Regional"),
}


@dataclass(frozen=True)
class ReservationTerm:
    name: str
    discount: float             # 0.25 = 25% off
    commitment: str             # "None", "1 Year", "3 Years"


RESERVATION_TERMS = {
    "on_demand": ReservationTerm("On-Demand", 0.0, "None"),
    "1_year": ReservationTerm("1-Year Reserved", 0.25, "1 Year"),
    "3_year": ReservationTerm("3-Year Reserved", 0.45, "3 Years"),
}
```

### 3.3 New Module: `ptu_advisor/cost/engine.py`

See UX design document for the `CostScenario` and `CostComparison` dataclass definitions.

Key function signature:

```python
def calculate_all_scenarios(
    tpm_values: List[float],
    model: str,
    deployment_type: DeploymentType = DeploymentType.GLOBAL,
    region: str = "eastus",
    baseline_percentile: float = 75,
    completion_ratio: float = 0.3,
) -> CostComparison:
```

### 3.4 New Module: `ptu_advisor/export/`

```python
# ptu_advisor/export/csv_exporter.py
def export_csv(
    metrics: DeploymentMetrics,
    analysis: AnalysisResult,
    cost_comparison: CostComparison,
    output_path: Optional[Path] = None,
) -> bytes:
    """Generate CSV report as bytes (for Streamlit download button)."""

# ptu_advisor/export/json_exporter.py  
def export_json(
    metrics: DeploymentMetrics,
    analysis: AnalysisResult,
    cost_comparison: CostComparison,
    output_path: Optional[Path] = None,
) -> str:
    """Generate JSON report as string."""
```

### 3.5 Integration Points

| Component | Change Required |
|---|---|
| `dashboard/app.py` | Add region dropdown, deployment type selector, export buttons in sidebar |
| `report/generator.py` | Update `_estimate_ptu_sizing()` to use `cost/pricing.py` instead of hardcoded rates |
| `config.py` | Add `region` and `deployment_type` fields to `AnalysisConfig` |
| `cli.py` | Add `--region` and `--deployment-type` CLI flags |

### 3.6 Security & Privacy

- No user data leaves the browser/server during export — CSV/JSON is generated locally
- Region/pricing data is static, embedded in the package — no external API calls in this phase
- Export files do not contain Azure credentials or subscription IDs
- JSON export version field enables forward compatibility

---

## 4. Dashboard UX Integration

### Region & Deployment Type Selectors

Added to the sidebar (below "Your Goals"), always visible:

```python
# Sidebar additions
st.markdown("**Deployment Config:**")

region = st.selectbox(
    "Azure Region",
    options=grouped_by_zone,         # Grouped: US > East US, West US, ...
    format_func=lambda r: f"{r.display_name} ({r.multiplier}x)",
    help="Select your deployment region. Affects PTU hourly pricing."
)

deploy_type = st.radio(
    "Deployment Type",
    options=["Global", "Data Zone", "Regional"],
    horizontal=True,
    help="Global = lowest min PTU. Data Zone = 1.2x rate. Regional = higher min PTU."
)
```

### Export Buttons

Added to the sidebar bottom or as a floating action in the report section:

```python
st.divider()
st.markdown("**Export Report**")

col_csv, col_json = st.columns(2)
with col_csv:
    st.download_button(
        "📄 CSV",
        data=csv_bytes,
        file_name=f"ptu-report-{deployment}-{date}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with col_json:
    st.download_button(
        "{ } JSON", 
        data=json_str,
        file_name=f"ptu-report-{deployment}-{date}.json",
        mime="application/json",
        use_container_width=True,
    )
```

---

## 5. Risks & Roadmap

### Phased Rollout

| Phase | Scope | Timeline |
|---|---|---|
| **MVP** | Regional pricing table + deployment type selector + cost recalculation | 1 week |
| **v1.1** | CSV/JSON export from dashboard | 3 days |
| **v1.2** | Integrate into HTML report generator + CLI flags | 3 days |
| **v2.0** (future) | Live Azure Retail Pricing API with cache + fallback | Phase 3 |

### Technical Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Pricing data goes stale** | Cost estimates diverge from reality | Add `PRICING_LAST_UPDATED` constant + warning banner when > 90 days old. Phase 3 adds live API. |
| **Region multipliers change** | Incorrect per-region costs | Source multipliers from ptucalc.com's validated data. Add a test that fails if pricing file is > 90 days old. |
| **Model-specific pricing exceptions** | gpt-5.1/5.2 have different reservation rates | `ModelCapacityConfig` already has per-model fields. Extend with `reservation_override` dict. |
| **CSV formatting edge cases** | Commas in model names, Unicode chars | Use Python `csv` module with proper quoting. Add test with adversarial model names. |
| **Large export files** | Slow generation for 90-day analysis | Export aggregated summary only (not raw time-series). Time-series export as optional flag. |

### Dependencies

- None external — all features use static data + existing metrics
- `cost/pricing.py` is the only new module that other features depend on → implement first

---

## 6. Testing Strategy

### Unit Tests

| Test | Coverage |
|---|---|
| `test_pricing.py` | Region multiplier lookup for all 35 regions |
| `test_pricing.py` | Deployment type rate calculations (Global/DataZone/Regional) |
| `test_cost_engine.py` | All 7 scenarios produce non-negative costs |
| `test_cost_engine.py` | Break-even TPM is between 0 and peak TPM |
| `test_cost_engine.py` | Savings % is monotonically ordered: 3Y > 1Y > On-Demand |
| `test_csv_export.py` | CSV contains all required sections |
| `test_csv_export.py` | CSV is valid (parseable by `csv.reader`) |
| `test_json_export.py` | JSON matches schema (validate with `jsonschema`) |
| `test_json_export.py` | JSON is parseable and contains `metadata.version` |

### Integration Tests

| Test | Coverage |
|---|---|
| `test_dashboard_pricing.py` | Region change triggers cost recalculation |
| `test_dashboard_export.py` | Download buttons render and produce valid files |
| `test_report_pricing.py` | HTML report uses region-aware costs |

### Validation

- Cross-check 5 model × 5 region × 3 deployment type combos against ptucalc.com output
- Document any intentional differences (e.g., we use 730 hrs/month, they may use 720)

---

## 7. File Plan

```
ptu_advisor/
├── cost/                          ← NEW MODULE
│   ├── __init__.py
│   ├── pricing.py                 # Static pricing data (regions, deploy types, rates)
│   └── engine.py                  # 7-scenario calculator + break-even
├── export/                        ← NEW MODULE
│   ├── __init__.py
│   ├── csv_exporter.py
│   └── json_exporter.py
├── config.py                      ← MODIFY: add region, deployment_type fields
├── cli.py                         ← MODIFY: add --region, --deployment-type flags
├── dashboard/
│   └── app.py                     ← MODIFY: region/deploy type selectors, export buttons
└── report/
    └── generator.py               ← MODIFY: use cost/pricing.py instead of hardcoded rates
```

Estimated total new code: ~500 lines across 4 new files + ~100 lines of modifications.

---

## 8. Requirement IDs & Traceability

| Requirement ID | Description | Primary Files | Test Coverage | KPI |
|---|---|---|---|---|
| `REQ-COST-001` | Region multiplier applied to PTU rates | `cost/pricing.py`, `cost/engine.py` | `test_pricing.py::test_region_multiplier_*` | Cost parity |
| `REQ-COST-002` | Deployment type rules (Global/DataZone/Regional) | `cost/pricing.py`, `config.py` | `test_cost_engine.py::test_deployment_type_*` | Cost parity |
| `REQ-UX-003` | Region/deployment selectors update costs in UI | `dashboard/app.py` | `test_dashboard_pricing.py` | Recalc latency |
| `REQ-DATA-004` | CSV export completeness | `export/csv_exporter.py` | `test_csv_export.py` | Export completeness |
| `REQ-DATA-005` | JSON export contract validity | `export/json_exporter.py` | `test_json_export.py` | Export completeness |
| `REQ-OBS-006` | Export and recalc telemetry events | `dashboard/app.py` | `test_dashboard_export.py` | Adoption telemetry |

## 9. Performance Budgets

| Interaction | Target | Measurement |
|---|---|---|
| Region/deployment selector change to updated cost UI | ≤ 500ms p95 | `ui.cost.recalc_ms` |
| CSV export generation | ≤ 2s p95 | `ui.export.duration_ms` |
| JSON export generation | ≤ 2s p95 | `ui.export.duration_ms` |

## 10. Observability Plan

Emit these events with `policy_version`, `region`, `deployment_type`, and `mode`:

- `assumption_changed`
- `cost_recalculated`
- `export_requested`
- `export_completed`
- `export_failed`

## 11. Data Contract Notes

Exports must include:

- `contract_version`
- `policy_version`
- `generated_at`
- `analysis_period_days`

All added fields must follow non-breaking compatibility rules from `PRD.md`.

## 12. Definition of Done (Feature)

- [ ] All `REQ-*` items above mapped to tests and passing
- [ ] Cost parity check documented for representative model/region/type matrix
- [ ] Export schema validated with contract version present
- [ ] Telemetry events verified in non-demo and demo modes
- [ ] UX copy reviewed for clarity (no ambiguous pricing labels)
- [ ] Rollback strategy documented (feature flags or safe defaults)
