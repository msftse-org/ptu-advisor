# PRD: Auto-Discovery Live Connect for PTU Advisor

> **Status:** Draft  
> **Author:** PTU Advisor Team  
> **Date:** 2026-02-11  
> **Priority:** P0 — Core feature for production readiness

---

## 1. Executive Summary

### Problem Statement

Today, the PTU Advisor dashboard only works with **simulated demo data**. The recently added "Connect to Azure" mode requires users to manually type in their Subscription ID, Resource Group, Workspace, and Deployment name — information most users don't have memorized. This creates friction and makes the tool unusable for customers who want to analyze their real Foundry deployments.

### Proposed Solution

Replace the manual-entry Azure connection flow with an **automatic resource discovery** experience. When the user selects "Connect to Azure," the dashboard:

1. **Authenticates** via `az login` (already done — zero-click).  
2. **Auto-discovers** all Azure subscriptions, Cognitive Services / AI Services accounts, and their model deployments.  
3. **Presents** the discovered resources in a cascading picker UI: Subscription → Account → Deployment.  
4. **Shows deployment metadata** (model name, SKU type, capacity) as selection cards so the user knows exactly what they're analyzing.  
5. On clicking "Analyze," fetches real metrics from Azure Monitor and runs the full analysis pipeline.

### Success Criteria

| KPI | Target |
|-----|--------|
| Time from "Connect to Azure" click to deployment selection | < 10 seconds (with cached credentials) |
| Number of manual text inputs required | **0** (all fields are auto-populated via discovery) |
| Error rate on first-time live connect (authenticated user) | < 5% |
| Dashboard parity — live mode produces identical analysis/charts as demo mode | 100% feature parity |
| Graceful degradation when Azure SDKs not installed | Dashboard still works in demo-only mode, no import errors |

---

## 2. User Experience & Functionality

### 2.1 User Personas

| Persona | Description | Key Need |
|---------|-------------|----------|
| **Azure AI Engineer** | Manages Foundry deployments, familiar with Azure portal. Wants data-driven PTU decisions. | Quick analysis without leaving their workflow |
| **Platform/FinOps Lead** | Reviews cloud costs across teams. May not know individual deployment names. | Browse all deployments, compare costs |
| **CSA / Solutions Architect** | Advises customers on PTU sizing. Needs to analyze customer deployments. | Connect to any subscription, fast demo |

### 2.2 User Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    WELCOME PAGE                              │
│                                                              │
│  Step 1: What's Your Focus?                                  │
│  ┌─ [Cost Reduction] [Throttling] [Latency] ... ─┐         │
│                                                              │
│  Step 2: Select Data Source                                  │
│  ┌─ ( ) Demo Mode    (●) Connect to Azure ─┐               │
│                                                              │
│  ┌──────────────────────────────────────────┐               │
│  │  🔐 Authenticating with Azure...         │  ← auto       │
│  │  ✅ Signed in as user@contoso.com        │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
│  ┌──────────────────────────────────────────┐               │
│  │  📦 Subscription                         │               │
│  │  ┌─ [Sub A (abc123)] ▼ ──────────────┐  │               │
│  │                                        │  │               │
│  │  🏢 AI Services Account               │  │               │
│  │  ┌─ [my-openai-account] ▼ ───────────┐  │               │
│  │                                        │  │               │
│  │  🚀 Deployments (3 found)             │  │               │
│  │  ┌────────────────────────────────┐   │  │               │
│  │  │ ● gpt-4o-global               │   │  │               │
│  │  │   Model: gpt-4o  |  SKU: S    │   │  │               │
│  │  │   Capacity: 80K TPM            │   │  │               │
│  │  ├────────────────────────────────┤   │  │               │
│  │  │ ○ gpt-4o-mini-prod            │   │  │               │
│  │  │   Model: gpt-4o-mini  |  PTU  │   │  │               │
│  │  │   Capacity: 50 PTUs            │   │  │               │
│  │  ├────────────────────────────────┤   │  │               │
│  │  │ ○ text-embedding-3-large      │   │  │               │
│  │  │   Model: text-embedding-3     │   │  │               │
│  │  │   Capacity: 350K TPM           │   │  │               │
│  │  └────────────────────────────────┘   │  │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
│  Step 3: [  ▶ Analyze My Deployment  ]                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 User Stories

#### US-1: Auto-authenticate on mode switch
> **As an** Azure AI Engineer,  
> **I want** the dashboard to automatically authenticate when I select "Connect to Azure,"  
> **so that** I don't have to paste credentials or tokens.

**Acceptance Criteria:**
- When user selects "Connect to Azure," authentication happens automatically using `az login` credentials.
- A status indicator shows: spinner → "Signed in as user@contoso.com" (with the user's actual identity).
- If not authenticated, a clear error message says: "Please run `az login` in your terminal first."
- Authentication result is cached in `st.session_state` so it doesn't re-run on every Streamlit rerun.

#### US-2: Auto-discover subscriptions
> **As a** Platform Lead with multiple subscriptions,  
> **I want** the dashboard to list all my accessible Azure subscriptions,  
> **so that** I can pick the right one without looking it up.

**Acceptance Criteria:**
- A dropdown lists all subscriptions the authenticated user has access to.
- Each option shows: `Display Name (subscription-id-first-8-chars...)`.
- The default selection is the first subscription (or the `az` CLI default if detectable).
- If only 1 subscription exists, it is auto-selected and the dropdown is still visible but pre-filled.

#### US-3: Auto-discover AI Services accounts
> **As an** Azure AI Engineer,  
> **I want** to see all Cognitive Services / AI Services accounts in the selected subscription,  
> **so that** I don't have to remember or type account names.

**Acceptance Criteria:**
- After subscription is selected, a second dropdown lists all `Microsoft.CognitiveServices/accounts` resources in that subscription.
- Each option shows: `account-name (resource-group)`.
- Accounts are fetched by listing Cognitive Services accounts across all resource groups in the subscription.
- If no accounts are found, show: "No AI Services accounts found in this subscription."
- Loading state shows a spinner while fetching.

#### US-4: Auto-discover and display deployments as cards
> **As an** Azure AI Engineer,  
> **I want** to see all model deployments in the selected account as visual cards with metadata,  
> **so that** I can identify the right deployment to analyze at a glance.

**Acceptance Criteria:**
- After account selection, all deployments are listed as **selectable cards** (not a plain dropdown).
- Each card shows:
  - Deployment name (bold, primary text)
  - Model name (e.g., "gpt-4o")
  - SKU type badge: `Standard` (blue) or `ProvisionedManaged` (green)
  - SKU capacity (e.g., "80K TPM" for Standard or "50 PTUs" for Provisioned)
- Cards are radio-selectable (one at a time).
- If a deployment is already PTU (`ProvisionedManaged`), the card shows a subtle indicator: "Already on PTU — analyze to validate sizing."
- If no deployments exist, show: "No deployments found in this account."

#### US-5: Seamless transition to analysis
> **As a** user who has selected a deployment,  
> **I want** to click "Analyze" and see the full dashboard populated with real data,  
> **so that** the experience is identical to demo mode but with my actual metrics.

**Acceptance Criteria:**
- Clicking "Analyze My Deployment" fetches metrics via `MetricsCollector`, runs `DecisionEngine`, and renders the same dashboard sections (Usage, Cost Explorer, Recommendation, Deep Dive).
- A progress indicator shows: "Fetching metrics from Azure..." → "Running analysis..." → dashboard renders.
- If metric collection fails (e.g., insufficient permissions, no metric data), a clear error message is shown with troubleshooting steps.
- The sidebar shows the live deployment name and account instead of "Demo: ..."

#### US-6: Graceful fallback when Azure SDK is unavailable
> **As a** user running the dashboard without Azure SDK packages installed,  
> **I want** the "Connect to Azure" option to show a helpful install message instead of crashing,  
> **so that** the demo mode always works regardless of environment.

**Acceptance Criteria:**
- If `azure-identity` or `azure-mgmt-cognitiveservices` is not installed, the "Connect to Azure" radio option is still visible.
- Upon selection, it shows: "Azure SDK packages are required. Run: `pip install azure-identity azure-mgmt-cognitiveservices azure-mgmt-monitor azure-mgmt-resource`"
- Demo mode remains fully functional.

### 2.4 Non-Goals

- **Multi-deployment comparison in a single analysis run.** Users analyze one deployment at a time. Comparison features are a future enhancement.
- **Write operations.** The dashboard never modifies Azure resources — it is strictly read-only.
- **Service principal / client-secret auth.** Only `az login` / Managed Identity / DefaultAzureCredential flows are supported.
- **Cross-tenant discovery.** Only resources in the authenticated tenant are shown.

---

## 3. Technical Specifications

### 3.1 Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Streamlit UI    │────▶│  Discovery Layer  │────▶│  Azure ARM APIs │
│  (app.py)        │     │  (discovery.py)   │     │                 │
│                  │     │                   │     │  - SubscriptionClient
│  • Subscription  │     │  • list_subs()    │     │  - CogServicesClient
│    dropdown      │     │  • list_accounts()│     │  - MonitorClient
│  • Account       │     │  • list_deploys() │     │                 │
│    dropdown      │     │  • get_identity() │     └─────────────────┘
│  • Deployment    │     └──────────────────┘
│    cards         │              │
│                  │              ▼
│  ▶ Analyze ──────┼───▶  MetricsCollector.collect()
│                  │              │
│                  │              ▼
│  Dashboard       │◀─── DecisionEngine.analyze()
│  (reuse 100%)    │
└─────────────────┘
```

### 3.2 New Module: `ptu_advisor/discovery.py`

A thin orchestration layer that wraps Azure SDK calls with caching, error handling, and Streamlit-friendly return types.

```python
# Key functions:
def authenticate() -> Tuple[TokenCredential, UserInfo]
def list_subscriptions(credential) -> List[SubscriptionInfo]
def list_ai_accounts(credential, subscription_id) -> List[AccountInfo]
def list_deployments(credential, subscription_id, resource_group, account_name) -> List[DeploymentInfo]
```

**Data classes:**

| Class | Fields |
|-------|--------|
| `UserInfo` | `display_name`, `email`, `tenant_id` |
| `SubscriptionInfo` | `subscription_id`, `display_name`, `state` |
| `AccountInfo` | `name`, `resource_group`, `location`, `kind`, `sku` |
| `DeploymentInfo` | (existing) `name`, `model`, `sku_type`, `sku_capacity` |

### 3.3 Caching Strategy

| Data | Cache Key | TTL | Mechanism |
|------|-----------|-----|-----------|
| Credential + UserInfo | `azure_credential` | Session lifetime | `st.session_state` (not serializable → no `@st.cache_data`) |
| Subscriptions | `f"subs_{tenant_id}"` | 300s | `@st.cache_data` |
| Accounts | `f"accounts_{sub_id}"` | 300s | `@st.cache_data` |
| Deployments | `f"deps_{sub_id}_{account}"` | 120s | `@st.cache_data` |
| Metrics + Analysis | `f"analysis_{sub}_{rg}_{acct}_{dep}_{days}"` | 300s | `@st.cache_data` |

### 3.4 Error Handling

| Scenario | User-Facing Message | Recovery |
|----------|-------------------|----------|
| Not logged in (`az login`) | "Please run `az login` in your terminal, then refresh this page." | Show retry button |
| No subscriptions | "No Azure subscriptions found for your account." | Link to Azure portal |
| No AI accounts in subscription | "No AI Services accounts found. Try a different subscription." | Switch subscription |
| No deployments in account | "No model deployments found in this account." | Switch account |
| Metrics collection fails | "Failed to fetch metrics: {error}. Check permissions." | Show troubleshooting checklist |
| Azure SDK not installed | "Azure SDK not installed. Run: `pip install ...`" | Show install command |

### 3.5 Required RBAC Permissions

| Scope | Role | Purpose |
|-------|------|---------|
| Subscription | `Reader` | List resource groups and Cognitive Services accounts |
| Cognitive Services Account | `Cognitive Services User` or `Reader` | List deployments, get account info |
| Cognitive Services Account | `Monitoring Reader` | Read Azure Monitor metrics |

### 3.6 Integration Points

- **Authentication:** `ptu_advisor.auth.get_azure_credential()` — unchanged.
- **Subscription listing:** `azure.mgmt.resource.SubscriptionClient.subscriptions.list()` — already in auth.py.
- **Account listing:** `azure.mgmt.cognitiveservices.CognitiveServicesManagementClient.accounts.list()` (subscription-wide, no RG filter needed).
- **Deployment listing:** `ptu_advisor.metrics.collector.list_workspace_deployments()` — unchanged.
- **Metric collection:** `ptu_advisor.metrics.collector.MetricsCollector.collect()` — unchanged.
- **Analysis engine:** `ptu_advisor.analysis.engine.DecisionEngine.analyze()` — unchanged.

---

## 4. UI Component Specifications

### 4.1 Authentication Status Banner

```
┌─────────────────────────────────────────────┐
│  ✅ Signed in as user@contoso.com           │
│  Tenant: Contoso Corp (abc123...)           │
└─────────────────────────────────────────────┘
```
- Uses `st.success()` for the green banner.
- Shown immediately after credential validation.
- If auth fails: `st.error()` with "Run `az login`" instructions.

### 4.2 Cascading Dropdowns

Each dropdown triggers re-fetch of the level below:

1. **Subscription** dropdown → fetches accounts for that subscription.
2. **Account** dropdown → fetches deployments for that account.
3. **Deployment** cards → user selects one → "Analyze" button enables.

Use `st.selectbox` for subscriptions and accounts. Use custom HTML/CSS cards with `st.radio` for deployments.

### 4.3 Deployment Card Design

```
┌──────────────────────────────────────────────┐
│ ● gpt-4o-global                    Standard  │
│   Model: gpt-4o                              │
│   Capacity: 80,000 TPM                       │
├──────────────────────────────────────────────┤
│ ○ gpt-4o-mini-prod            ProvisionedMgd │
│   Model: gpt-4o-mini                         │
│   Capacity: 50 PTUs                          │
│   ⚡ Already on PTU                           │
└──────────────────────────────────────────────┘
```

- Radio selection (single-choice).
- Badge color: Standard = blue (`#0078D4`), ProvisionedManaged = green (`#00d4aa`).
- "Already on PTU" hint for ProvisionedManaged deployments.

---

## 5. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Azure SDK not installed in user's env | Medium | Blocks live mode | Lazy imports + clear install message; demo mode unaffected |
| Slow subscription/account listing (many resources) | Low | Poor UX (>10s load) | Cache results; show spinners; paginate if needed |
| User lacks RBAC permissions | Medium | Discovery fails | Show specific role requirements and Azure portal link |
| Credential token expires mid-session | Low | API calls fail | Catch `ClientAuthenticationError`, prompt re-login |
| Rate limiting on ARM API calls | Very Low | Temporary failures | Built-in retry in Azure SDK; backoff handled by SDK |

---

## 6. Rollout Plan

### Phase 1: MVP (This PR)

- Cascading discovery: Subscriptions → Accounts → Deployments.
- Deployment cards with metadata.
- Full analysis pipeline from live data.
- Graceful SDK-not-installed fallback.

### Phase 2: Polish (Follow-up)

- Remember last-used subscription/account/deployment in `st.session_state` across sessions (via query params or local storage).
- "Refresh" button to re-discover resources without page reload.
- Show deployment-level quick stats (last 24h TPM, throttle rate) on the card before full analysis.

### Phase 3: Advanced (Future)

- Multi-deployment selection for side-by-side comparison.
- Scheduled analysis (daily email with PTU recommendation changes).
- Integration with Azure Advisor recommendations.

---

## 7. Implementation Checklist

- [x] PRD written and approved
- [ ] Create `ptu_advisor/discovery.py` with `authenticate()`, `list_subscriptions()`, `list_ai_accounts()`, `list_deployments()` 
- [ ] Add `SubscriptionInfo`, `AccountInfo` dataclasses to discovery module
- [ ] Rewrite "Connect to Azure" section in `app.py` welcome page with cascading dropdowns
- [ ] Implement deployment card rendering (HTML/CSS + `st.radio`)
- [ ] Route "Analyze" button to `load_live_data()` with discovered resource coordinates
- [ ] Update sidebar to show live deployment info when in live mode
- [ ] Update footer to show "Live: deployment-name" instead of "Demo: ..."
- [ ] Add SDK-not-installed graceful fallback
- [ ] Manual end-to-end test with real Azure subscription

---

## 8. Requirement IDs & Traceability

| Requirement ID | Description | Primary Files | Test Coverage | KPI |
|---|---|---|---|---|
| `REQ-UX-201` | Zero manual input discovery flow | `dashboard/app.py`, `discovery.py` | `test_discovery.py::test_cascading_discovery_flow` | Time-to-selection |
| `REQ-DATA-202` | Subscription/account/deployment discovery correctness | `discovery.py` | `test_discovery.py::test_list_*` | First-run success rate |
| `REQ-SEC-203` | Read-only behavior with no mutation operations | `discovery.py`, auth integration | static + integration checks | Security compliance |
| `REQ-UX-204` | Graceful fallback when SDKs absent | `dashboard/app.py` | `test_smoke.py::test_demo_mode_without_sdk` | Demo availability |
| `REQ-OBS-205` | Discovery/auth failure telemetry emitted | UI + discovery layer | telemetry validation | Error triage speed |

## 9. Performance Budgets

| Interaction | Target | Measurement |
|---|---|---|
| Connect to Azure → first deployment list | ≤ 10s p95 | `ui.discovery.time_ms` |
| Subscription switch → account list refresh | ≤ 2s p95 | `ui.discovery.accounts_ms` |
| Account switch → deployment list refresh | ≤ 2s p95 | `ui.discovery.deployments_ms` |

## 10. Observability Plan

Required events:

- `azure_connect_started`
- `azure_connect_succeeded`
- `azure_connect_failed`
- `discovery_subscriptions_loaded`
- `discovery_accounts_loaded`
- `discovery_deployments_loaded`
- `analysis_run_started`

Required dimensions:

- `tenant_id_hash`
- `subscription_count`
- `account_count`
- `deployment_count`
- `error_type` (on failures)
- `policy_version`

## 11. Security & Privacy Addendum

- No tokens or secrets persisted to export files or UI state snapshots.
- Telemetry must hash tenant identifiers before emission.
- Only minimum metadata needed for UX and diagnostics is persisted in session state.

## 12. Definition of Done (Feature)

- [ ] `REQ-*` requirements mapped to tests and passing
- [ ] Discovery flow validated in multi-subscription and single-subscription tenants
- [ ] SDK-missing fallback verified with explicit install guidance
- [ ] RBAC failure UX validated with actionable remediation text
- [ ] Latency budgets measured and documented (p50/p95)
- [ ] Telemetry events validated for success + failure paths
