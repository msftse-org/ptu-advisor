import type {
  AccountInfo,
  AnalysisResponse,
  AuthStatus,
  ConsolidationResponse,
  DeploymentInfo,
  DeploymentPreview,
  PricingOptions,
  FocusTopic,
  SubscriptionInfo,
} from './types'

function toSnippet(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 180)
}

/**
 * Extract a user-friendly message from an HTTP error body.
 * FastAPI HTTPException returns JSON `{"detail":"..."}` — we prefer that.
 * Falls back to the raw text (truncated) or a generic status message.
 */
function extractErrorMessage(text: string, status: number): string {
  if (!text) return `Request failed (HTTP ${status})`
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // Not JSON — use raw text
  }
  return toSnippet(text) || `Request failed (HTTP ${status})`
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  const contentType = response.headers.get('content-type') ?? ''

  if (!response.ok) {
    const text = await response.text()
    throw new Error(extractErrorMessage(text, response.status))
  }

  if (!contentType.includes('application/json')) {
    const text = await response.text()
    throw new Error(`Expected JSON from ${url}, got ${contentType || 'unknown'}: ${toSnippet(text)}`)
  }

  try {
    return (await response.json()) as T
  } catch {
    const text = await response.text()
    throw new Error(`Invalid JSON from ${url}: ${toSnippet(text)}`)
  }
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const contentType = response.headers.get('content-type') ?? ''

  if (!response.ok) {
    const text = await response.text()
    throw new Error(extractErrorMessage(text, response.status))
  }

  if (!contentType.includes('application/json')) {
    const text = await response.text()
    throw new Error(`Expected JSON from ${url}, got ${contentType || 'unknown'}: ${toSnippet(text)}`)
  }

  try {
    return (await response.json()) as T
  } catch {
    const text = await response.text()
    throw new Error(`Invalid JSON from ${url}: ${toSnippet(text)}`)
  }
}

export const api = {
  authStatus: () => getJson<AuthStatus>('/api/discovery/auth-status'),
  refreshDiscoveryCache: () => postJson<{ status: string }>('/api/discovery/refresh', {}),
  focusTopics: () => getJson<FocusTopic[]>('/api/focus-topics'),
  pricingOptions: () => getJson<PricingOptions>('/api/pricing/options'),
  subscriptions: () => getJson<SubscriptionInfo[]>('/api/discovery/subscriptions'),
  accounts: (subscriptionId: string) =>
    getJson<AccountInfo[]>(`/api/discovery/accounts?subscription_id=${encodeURIComponent(subscriptionId)}`),
  deployments: (subscriptionId: string, resourceGroup: string, accountName: string) =>
    getJson<DeploymentInfo[]>(
      `/api/discovery/deployments?subscription_id=${encodeURIComponent(subscriptionId)}&resource_group=${encodeURIComponent(resourceGroup)}&account_name=${encodeURIComponent(accountName)}`,
    ),
  analyze: (payload: Record<string, unknown>) => postJson<AnalysisResponse>('/api/analyze', payload),
  analyzeConsolidation: (payload: Record<string, unknown>) =>
    postJson<ConsolidationResponse>('/api/analyze-consolidation', payload),
  deploymentPreview: (params: { mode: string; focusTopic?: string; lookbackDays?: number }) => {
    const qs = new URLSearchParams({ mode: params.mode })
    if (params.focusTopic) qs.set('focus_topic', params.focusTopic)
    if (params.lookbackDays != null) qs.set('lookback_days', String(params.lookbackDays))
    return getJson<DeploymentPreview[]>(`/api/deployments/preview?${qs}`)
  },
}
