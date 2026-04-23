/**
 * Observability telemetry for Break-Even Cost Explorer.
 *
 * Emits structured events per PRD §10 (Observability Plan):
 *   - assumption_changed
 *   - cost_recalculated
 *   - break_even_marker_rendered
 *   - break_even_unavailable
 *
 * Each event carries the required dimensions:
 *   policy_version, recommendation, model_name, deployment_type
 *
 * In this standalone client-side app there is no backend analytics
 * service, so events are dispatched as CustomEvents on `window` and
 * logged to the console at DEBUG level.  This makes it straightforward
 * for a future integration (Application Insights, PostHog, etc.) to
 * subscribe via `window.addEventListener('ptu:telemetry', handler)`.
 */

// ── Types ──────────────────────────────────────────────────────────

export type TelemetryEventName =
  | 'assumption_changed'
  | 'cost_recalculated'
  | 'break_even_marker_rendered'
  | 'break_even_unavailable'
  | 'azure_connect_started'
  | 'azure_connect_succeeded'
  | 'azure_connect_failed'
  | 'discovery_subscriptions_loaded'
  | 'discovery_accounts_loaded'
  | 'discovery_deployments_loaded'
  | 'analysis_run_started'
  | 'performance_budget_exceeded'

/** Required dimensions attached to every event (PRD §10). */
export interface TelemetryDimensions {
  policy_version: string
  recommendation: string
  model_name: string
  deployment_type: string
}

/** Extra payload specific to each event type. */
export interface AssumptionChangedPayload extends TelemetryDimensions {
  changed_field: string
  old_value: string | number
  new_value: string | number
  reservation_term: string
  baseline_ptu: number
}

export interface CostRecalculatedPayload extends TelemetryDimensions {
  payg_monthly: number
  hybrid_monthly: number
  savings: number
  savings_pct: number
  baseline_ptu: number
  reservation_term: string
}

export interface BreakEvenMarkerRenderedPayload extends TelemetryDimensions {
  break_even_tpm: number
  avg_tpm: number
  distance_pct: number
  tone: 'positive' | 'neutral' | 'negative'
}

export interface BreakEvenUnavailablePayload extends TelemetryDimensions {
  selected_ptu: number
  reason: string
}

/** Discovery event dimensions (PRD §10). */
export interface DiscoveryDimensions {
  policy_version: string
  tenant_id_hash: string
}

export interface AzureConnectStartedPayload extends DiscoveryDimensions {}

export interface AzureConnectSucceededPayload extends DiscoveryDimensions {
  display_name: string
}

export interface AzureConnectFailedPayload extends DiscoveryDimensions {
  error_type: string
}

export interface DiscoverySubscriptionsLoadedPayload extends DiscoveryDimensions {
  subscription_count: number
}

export interface DiscoveryAccountsLoadedPayload extends DiscoveryDimensions {
  account_count: number
}

export interface DiscoveryDeploymentsLoadedPayload extends DiscoveryDimensions {
  deployment_count: number
}

export interface AnalysisRunStartedPayload extends DiscoveryDimensions {
  mode: 'demo' | 'live'
  model_name?: string
}

/** Performance budget exceeded event (PRD §9). */
export interface PerformanceBudgetExceededPayload extends DiscoveryDimensions {
  operation: string
  budget_ms: number
  actual_ms: number
}

type EventPayloadMap = {
  assumption_changed: AssumptionChangedPayload
  cost_recalculated: CostRecalculatedPayload
  break_even_marker_rendered: BreakEvenMarkerRenderedPayload
  break_even_unavailable: BreakEvenUnavailablePayload
  azure_connect_started: AzureConnectStartedPayload
  azure_connect_succeeded: AzureConnectSucceededPayload
  azure_connect_failed: AzureConnectFailedPayload
  discovery_subscriptions_loaded: DiscoverySubscriptionsLoadedPayload
  discovery_accounts_loaded: DiscoveryAccountsLoadedPayload
  discovery_deployments_loaded: DiscoveryDeploymentsLoadedPayload
  analysis_run_started: AnalysisRunStartedPayload
  performance_budget_exceeded: PerformanceBudgetExceededPayload
}

// ── Core emit function ─────────────────────────────────────────────

const TELEMETRY_PREFIX = 'ptu:telemetry'

/** Whether console debug output is enabled.  Can be toggled at runtime. */
let debugEnabled =
  typeof window !== 'undefined' &&
  (window.localStorage?.getItem('ptu_telemetry_debug') === '1' ||
    import.meta.env?.DEV === true)

export function setTelemetryDebug(enabled: boolean): void {
  debugEnabled = enabled
}

/**
 * Emit a telemetry event.
 *
 * 1. Dispatches a `ptu:telemetry` CustomEvent on `window` so
 *    external listeners can subscribe.
 * 2. Logs to `console.debug` when debug mode is enabled.
 */
export function emitTelemetry<E extends TelemetryEventName>(
  event: E,
  payload: EventPayloadMap[E],
): void {
  const envelope = {
    event,
    timestamp: new Date().toISOString(),
    ...payload,
  }

  // Dispatch CustomEvent for external subscribers
  if (typeof window !== 'undefined' && typeof CustomEvent !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(TELEMETRY_PREFIX, { detail: envelope }),
    )
  }

  if (debugEnabled) {
    // eslint-disable-next-line no-console
    console.debug(`[telemetry] ${event}`, envelope)
  }
}

// ── Convenience emitters ───────────────────────────────────────────

export function emitAssumptionChanged(
  payload: AssumptionChangedPayload,
): void {
  emitTelemetry('assumption_changed', payload)
}

export function emitCostRecalculated(
  payload: CostRecalculatedPayload,
): void {
  emitTelemetry('cost_recalculated', payload)
}

export function emitBreakEvenMarkerRendered(
  payload: BreakEvenMarkerRenderedPayload,
): void {
  emitTelemetry('break_even_marker_rendered', payload)
}

export function emitBreakEvenUnavailable(
  payload: BreakEvenUnavailablePayload,
): void {
  emitTelemetry('break_even_unavailable', payload)
}

// ── Discovery event emitters (PRD §10) ─────────────────────────────

/** Simple FNV-1a hash for privacy-safe tenant ID hashing (PRD §11). */
export function hashTenantId(tenantId: string): string {
  if (!tenantId) return ''
  let hash = 0x811c9dc5
  for (let i = 0; i < tenantId.length; i++) {
    hash ^= tenantId.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function emitAzureConnectStarted(
  payload: AzureConnectStartedPayload,
): void {
  emitTelemetry('azure_connect_started', payload)
}

export function emitAzureConnectSucceeded(
  payload: AzureConnectSucceededPayload,
): void {
  emitTelemetry('azure_connect_succeeded', payload)
}

export function emitAzureConnectFailed(
  payload: AzureConnectFailedPayload,
): void {
  emitTelemetry('azure_connect_failed', payload)
}

export function emitDiscoverySubscriptionsLoaded(
  payload: DiscoverySubscriptionsLoadedPayload,
): void {
  emitTelemetry('discovery_subscriptions_loaded', payload)
}

export function emitDiscoveryAccountsLoaded(
  payload: DiscoveryAccountsLoadedPayload,
): void {
  emitTelemetry('discovery_accounts_loaded', payload)
}

export function emitDiscoveryDeploymentsLoaded(
  payload: DiscoveryDeploymentsLoadedPayload,
): void {
  emitTelemetry('discovery_deployments_loaded', payload)
}

export function emitAnalysisRunStarted(
  payload: AnalysisRunStartedPayload,
): void {
  emitTelemetry('analysis_run_started', payload)
}

// ── Performance budget helpers (PRD §9) ────────────────────────────

/** Budget thresholds in milliseconds. */
export const PERF_BUDGET = {
  /** Full discovery flow: auth + subs + accounts + deployments. */
  FULL_DISCOVERY_MS: 10_000,
  /** Cached dropdown change (accounts or deployments reload). */
  CACHED_CHANGE_MS: 2_000,
} as const

export function emitPerformanceBudgetExceeded(
  payload: PerformanceBudgetExceededPayload,
): void {
  emitTelemetry('performance_budget_exceeded', payload)
  // Always warn in console regardless of debug flag — these are actionable
  // eslint-disable-next-line no-console
  console.warn(
    `[perf] ${payload.operation} exceeded budget: ${payload.actual_ms.toFixed(0)}ms > ${payload.budget_ms}ms`,
  )
}
