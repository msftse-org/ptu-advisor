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

type EventPayloadMap = {
  assumption_changed: AssumptionChangedPayload
  cost_recalculated: CostRecalculatedPayload
  break_even_marker_rendered: BreakEvenMarkerRenderedPayload
  break_even_unavailable: BreakEvenUnavailablePayload
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
