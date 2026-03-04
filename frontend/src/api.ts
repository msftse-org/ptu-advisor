import type {
  AccountInfo,
  AnalysisResponse,
  DeploymentInfo,
  PricingOptions,
  FocusTopic,
  SubscriptionInfo,
} from './types'

function toSnippet(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 180)
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  const contentType = response.headers.get('content-type') ?? ''

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
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
    throw new Error(text || `Request failed: ${response.status}`)
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
}
