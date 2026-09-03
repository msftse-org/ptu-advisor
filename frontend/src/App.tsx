import { lazy, Suspense, useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api'
import { useChartZoom } from './charts/use-chart-zoom'
import type {
  AccountInfo,
  AnalysisMode,
  AnalysisResponse,
  AuthStatus,
  ConsolidationCharts,
  ConsolidationSummary,
  DeploymentInfo,
  DeploymentPreview,
  DeploymentTypeOption,
  FocusTopic,
  PricingRegion,
  SubscriptionInfo,
} from './types'
import { calculateBreakEvenRange } from './calculator'
import { AnalyticalWidget } from './AnalyticalWidget'
import { RecommendationIcon } from './RecommendationIcon'
import {
  emitAssumptionChanged,
  emitCostRecalculated,
  emitBreakEvenMarkerRendered,
  emitBreakEvenUnavailable,
  emitAzureConnectStarted,
  emitAzureConnectSucceeded,
  emitAzureConnectFailed,
  emitDiscoverySubscriptionsLoaded,
  emitDiscoveryAccountsLoaded,
  emitDiscoveryDeploymentsLoaded,
  emitAnalysisRunStarted,
  emitPerformanceBudgetExceeded,
  PERF_BUDGET,
  hashTenantId,
  emitCacheTelemetry,
} from './telemetry'

const TokenVolumeChart = lazy(() => import('./charts/TokenVolumeChart').then((module) => ({ default: module.TokenVolumeChart })))
const RequestOutcomesChart = lazy(() => import('./charts/RequestOutcomesChart').then((module) => ({ default: module.RequestOutcomesChart })))
const DailyCostChart = lazy(() => import('./charts/DailyCostChart').then((module) => ({ default: module.DailyCostChart })))
const ThrottleChart = lazy(() => import('./charts/ThrottleChart').then((module) => ({ default: module.ThrottleChart })))
const TpmBandChart = lazy(() => import('./charts/TpmBandChart').then((module) => ({ default: module.TpmBandChart })))
const CostCurveChart = lazy(() => import('./charts/CostCurveChart').then((module) => ({ default: module.CostCurveChart })))
const LatencyOverlayChart = lazy(() => import('./charts/LatencyOverlayChart').then((module) => ({ default: module.LatencyOverlayChart })))
const PromptCacheVolumeChart = lazy(() => import('./charts/PromptCacheChart').then((module) => ({ default: module.PromptCacheVolumeChart })))
const CacheEfficiencyChart = lazy(() => import('./charts/PromptCacheChart').then((module) => ({ default: module.CacheEfficiencyChart })))
const ExportReport = lazy(() => import('./ExportReport').then((module) => ({ default: module.ExportReport })))

type Mode = 'demo' | 'live'

const RESERVATION_OPTIONS = [
  'Hourly — No Commitment',
  'Monthly Commitment (Estimated 64% off)',
  '1-Year Commitment (Estimated 69% off)',
] as const

const RESERVATION_OPTION_LABELS: Record<(typeof RESERVATION_OPTIONS)[number], string> = {
  'Hourly — No Commitment': 'Hourly · No commitment',
  'Monthly Commitment (Estimated 64% off)': 'Monthly · Est. 64% off',
  '1-Year Commitment (Estimated 69% off)': '1 year · Est. 69% off',
}

const FALLBACK_PRICING_REGIONS: PricingRegion[] = [
  { name: 'eastus', display_name: 'East US', multiplier: 1.0, zone: 'US' },
]

const FALLBACK_DEPLOYMENT_TYPES: DeploymentTypeOption[] = [
  { name: 'global', label: 'Global', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.0 },
  { name: 'data_zone', label: 'Data Zone', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.1 },
  { name: 'regional', label: 'Regional', increment: 50, default_min_ptu: 50, base_hourly_rate: 2.0 },
]

/** Human-readable labels for snake_case safety verdicts */
const VERDICT_LABELS: Record<string, string> = {
  safe: 'Safe',
  efficient_but_risky: 'Efficient but Risky',
  not_justified: 'Not Justified',
  insufficient_data: 'Insufficient Data',
}
/** Convert snake_case verdict to CSS class suffix (underscores → hyphens) */
const verdictCssClass = (v: string) => v.replace(/_/g, '-')

/* ── PTU Calculator model catalog ── */
const CALC_MODELS = [
  { id: 'gpt-4o', label: 'GPT-4o', tpmPerPtu: 2500, tokenRates: { global: [2.50, 1.25, 10.00], data_zone: [2.75, 1.375, 11.00], regional: [2.75, 1.375, 11.00] }, outputRatio: 4, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', tpmPerPtu: 37000, tokenRates: { global: [0.15, 0.075, 0.60], data_zone: [0.165, 0.0825, 0.66], regional: [0.165, 0.0825, 0.66] }, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-4.1', label: 'GPT-4.1', tpmPerPtu: 3000, tokenRates: { global: [2.00, 0.50, 8.00], data_zone: [2.20, 0.55, 8.80], regional: [2.20, 0.55, 8.80] }, outputRatio: 4, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'gpt-4.1-mini', label: 'GPT-4.1 Mini', tpmPerPtu: 14900, tokenRates: { global: [0.40, 0.10, 1.60], data_zone: [0.44, 0.11, 1.76], regional: [0.44, 0.11, 1.76] }, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-4.1-nano', label: 'GPT-4.1 Nano', tpmPerPtu: 59400, tokenRates: { global: [0.10, 0.025, 0.40], data_zone: [0.11, 0.0275, 0.44], regional: [0.11, 0.0275, 0.44] }, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-5', label: 'GPT-5', tpmPerPtu: 4750, tokenRates: { global: [1.25, 0.125, 10.00], data_zone: [1.375, 0.1375, 11.00], regional: [1.25, 1.25, 10.00] }, outputRatio: 8, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'o3-mini', label: 'o3-mini', tpmPerPtu: 2500, tokenRates: { global: [1.10, 0.55, 4.40], data_zone: [1.21, 0.605, 4.84], regional: [1.21, 0.605, 4.84] }, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'o4-mini', label: 'o4-mini', tpmPerPtu: 5400, tokenRates: { global: [1.10, 0.275, 4.40], data_zone: [1.21, 0.303, 4.84], regional: [1.21, 0.303, 4.84] }, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
] as const

/** Current cost-model policy version — surfaces in telemetry (PRD §10). */
const POLICY_VERSION = 'v3.1'

type CalcScenario = { name: string; term: string; cost: number; ptuUnits: number }
type TimeWindow = { start: string; end: string }
type RunAnalysisOptions = {
  preserveCurrent?: boolean
  timeWindow?: TimeWindow | null
  updateCharts?: boolean
}

function formatNumber(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`
  }
  return `${Math.round(value)}`
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function formatCurrencyPrecise(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/** Adaptive date label: date-only when dense, date+time when sparse. */
function formatDateLabel(iso: string): string {
  const d = new Date(iso)
  const mon = d.getMonth() + 1
  const day = d.getDate()
  return `${mon}/${day}`
}

/** Build a smart tick formatter that adapts to data density and date range. */
function makeSmartDateFormatter(timestamps: string[]) {
  if (timestamps.length === 0) return formatDateLabel
  const first = new Date(timestamps[0]).getTime()
  const last = new Date(timestamps[timestamps.length - 1]).getTime()
  const spanHours = (last - first) / (1000 * 60 * 60)
  const dense = timestamps.length > 80

  return (iso: string) => {
    const d = new Date(iso)
    const mon = d.getMonth() + 1
    const day = d.getDate()
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    if (spanHours <= 24) return `${hh}:${mm}`
    if (spanHours <= 168 && !dense) return `${mon}/${day} ${hh}:${mm}`
    return `${mon}/${day}`
  }
}

function formatDeploymentTitle(deployment: DeploymentInfo): string {
  const modelName = deployment.model?.trim() || 'Unknown model'
  if (deployment.name.trim().toLowerCase() === modelName.toLowerCase()) {
    return deployment.name
  }
  return `${deployment.name} · ${modelName}`
}

function getDeploymentMetaParts(deployment: DeploymentInfo): { sku: string; capacity: string } {
  return {
    sku: deployment.sku_type?.trim() || 'n/a',
    capacity: String(deployment.sku_capacity ?? 'n/a'),
  }
}

/** Group deployments by model_family, keeping eligible families first. */
function groupDeploymentsByFamily(items: DeploymentInfo[]): { family: string; deployments: DeploymentInfo[]; allIneligible: boolean }[] {
  const familyMap = new Map<string, DeploymentInfo[]>()
  for (const dep of items) {
    const family = dep.model_family || 'Other'
    if (!familyMap.has(family)) familyMap.set(family, [])
    familyMap.get(family)!.push(dep)
  }
  const groups = Array.from(familyMap.entries()).map(([family, deps]) => ({
    family,
    deployments: deps.sort((a, b) => a.name.localeCompare(b.name)),
    allIneligible: deps.every((d) => !d.ptu_eligible),
  }))
  // Eligible families first (alphabetical), then ineligible families (alphabetical)
  groups.sort((a, b) => {
    if (a.allIneligible !== b.allIneligible) return a.allIneligible ? 1 : -1
    return a.family.localeCompare(b.family)
  })
  return groups
}

function formatSubscriptionTitle(subscription: SubscriptionInfo): string {
  return subscription.display_name || subscription.label || subscription.subscription_id
}

function getSubscriptionStateView(state?: string): { label: string; tone: 'enabled' | 'disabled' | 'unknown' } {
  const normalized = (state || '').trim().toLowerCase()
  if (normalized === 'enabled') {
    return { label: 'Enabled', tone: 'enabled' }
  }
  if (normalized === 'disabled') {
    return { label: 'Disabled', tone: 'disabled' }
  }
  return { label: state?.trim() || 'Unknown', tone: 'unknown' }
}

function toReadableParagraphs(text: string): string[] {
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\*\*/g, '')
    .split('\n')
    .map((line) =>
      line
        .replace(/\p{Extended_Pictographic}/gu, '')
        .replace(/[•▪◦]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim(),
    )
    .filter(Boolean)
}

function toTitleCaseLabel(input: string): string {
  const normalized = input.replace(/[_-]+/g, ' ').trim()
  const acronyms = new Set(['tpm', 'p50', 'p95', 'p99', 'cv', 'ptu', 'payg', 'sla', 'roi'])

  return normalized
    .split(/\s+/)
    .map((segment) => {
      const lowered = segment.toLowerCase()
      if (acronyms.has(lowered)) return lowered.toUpperCase()
      return lowered.charAt(0).toUpperCase() + lowered.slice(1)
    })
    .join(' ')
}

function describeMetricKey(key: string): string {
  const normalized = key.toLowerCase()
  const descriptions: Record<string, string> = {
    cv: 'Coefficient of variation. Lower values usually mean steadier traffic.',
    p50: 'Median value across the analysis window.',
    p95: '95th percentile value, representing busy periods.',
    p99: '99th percentile value, representing peak spikes.',
    avg_tpm: 'Average throughput in tokens per minute.',
    peak_tpm: 'High-end throughput used for capacity planning.',
    throttling_rate: 'Rate of HTTP 429 responses observed in the window.',
    throttling_rate_pct: 'Percent of requests throttled with HTTP 429.',
    sustained_utilization_rate: 'Share of intervals with sustained material load.',
    active_hours_percentage: 'Percent of hours with meaningful traffic.',
    business_hours_concentration: 'Traffic concentration during business hours.',
    weekend_vs_weekday_ratio: 'Relative traffic intensity on weekends vs weekdays.',
    peak_to_average_ratio: 'Burstiness measure comparing peak and average load.',
  }

  if (descriptions[normalized]) return descriptions[normalized]
  if (normalized.includes('ratio')) return 'Ratio metric; values above 1 indicate stronger concentration or burstiness.'
  if (normalized.includes('pct') || normalized.includes('percent')) return 'Percentage metric within the analyzed period.'
  if (normalized.includes('tpm')) return 'Throughput metric measured in tokens per minute.'
  return `Observed metric for ${toTitleCaseLabel(key)}.`
}

function formatDimensionMetricValue(key: string, value: number): string {
  const normalized = key.toLowerCase()
  const absValue = Math.abs(value)

  if (normalized.includes('pct') || normalized.includes('percent') || normalized.endsWith('_percentage')) {
    return `${new Intl.NumberFormat('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value)}%`
  }

  if ((normalized.includes('rate') || normalized === 'cv') && absValue <= 1) {
    return `${new Intl.NumberFormat('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value * 100)}%`
  }

  if (normalized.includes('ratio')) {
    return `${new Intl.NumberFormat('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value)}x`
  }

  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 0,
    maximumFractionDigits: absValue >= 1000 ? 0 : 2,
  }).format(value)
}

function LoadingSpinner() {
  return (
    <div className="loading-overlay">
      <div className="loading-spinner" />
      <span className="loading-text">Analyzing deployment metrics</span>
      <div className="loading-pulse">
        <span /><span /><span />
      </div>
    </div>
  )
}

function ThinkingOverlay() {
  return (
    <div className="thinking-overlay">
      <div className="thinking-pill">
        <div className="loading-spinner thinking-spinner" />
        <span>Updating analysis…</span>
      </div>
    </div>
  )
}

function RecBadge({ recommendation }: { recommendation: string }) {
  if (recommendation === 'ptu_recommended') {
    return <span className="rec-badge rec-badge-positive" role="status" aria-label="PTU Recommended"><RecommendationIcon kind="recommended" />PTU Recommended</span>
  }
  if (recommendation === 'ptu_not_recommended') {
    return <span className="rec-badge rec-badge-negative" role="status" aria-label="Stay on PAYG"><RecommendationIcon kind="info" />Stay on PAYG</span>
  }
  if (recommendation === 'insufficient_data') {
    return <span className="rec-badge rec-badge-insufficient" role="status" aria-label="Insufficient Data"><RecommendationIcon kind="insufficient" />Insufficient Data</span>
  }
  return <span className="rec-badge rec-badge-borderline" role="status" aria-label="Borderline"><RecommendationIcon kind="borderline" />Borderline</span>
}

function dimScoreClass(score: string): string {
  const s = score.toLowerCase()
  if (s === 'positive') return 'dim-score dim-score-positive'
  if (s === 'negative') return 'dim-score dim-score-negative'
  if (s === 'neutral') return 'dim-score dim-score-neutral'
  return 'dim-score dim-score-insufficient'
}

function InfoTip({ text }: { text: string }) {
  const tooltipId = useId()
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [tooltipAlign, setTooltipAlign] = useState<'left' | 'center' | 'right'>('right')

  const updateTooltipPlacement = () => {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const margin = 12
    const bubbleWidth = Math.min(window.innerWidth <= 560 ? 260 : 300, window.innerWidth - margin * 2)
    const leftFits = rect.left - 7 + bubbleWidth <= window.innerWidth - margin
    const rightFits = rect.right + 7 - bubbleWidth >= margin
    const prefersLeft = rect.left + rect.width / 2 < window.innerWidth / 2

    if (prefersLeft && leftFits) setTooltipAlign('left')
    else if (!prefersLeft && rightFits) setTooltipAlign('right')
    else if (leftFits) setTooltipAlign('left')
    else if (rightFits) setTooltipAlign('right')
    else setTooltipAlign('center')
  }

  return (
    <span
      ref={triggerRef}
      className="info-tip"
      data-tooltip-align={tooltipAlign}
      aria-label={`Info: ${text}`}
      aria-describedby={tooltipId}
      role="button"
      tabIndex={0}
      onMouseEnter={updateTooltipPlacement}
      onFocus={updateTooltipPlacement}
    >
      <span className="info-tip-icon" aria-hidden="true">
        i
      </span>
      <span className="tip-bubble" id={tooltipId} role="tooltip">
        <span className="tip-bubble-label">Metric guidance</span>
        <span className="tip-bubble-content">{text}</span>
      </span>
    </span>
  )
}

function WidgetHeader({ title, tip, onExpand, helpContent }: { title: string; tip: string; onExpand?: () => void; helpContent?: string }) {
  const [showHelp, setShowHelp] = useState(false)
  return (
    <>
      <h4 className="widget-header" aria-label={`Hover to inspect exact values for ${title}`}>
        <span>{title}</span>
        <span className="widget-header-actions">
          {helpContent && (
            <button
              className="chart-help-btn"
              onClick={() => setShowHelp(!showHelp)}
              aria-label="Help: hybrid model explanation"
              aria-expanded={showHelp}
              title="How the hybrid model works"
            >
              ?
            </button>
          )}
          {onExpand && (
            <button className="chart-expand-btn" onClick={onExpand} aria-label={`Expand ${title}`} title="Expand chart">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" />
              </svg>
            </button>
          )}
          <InfoTip text={tip} />
        </span>
      </h4>
      {helpContent && showHelp && (
        <div className="hybrid-help-panel" role="region" aria-label="Hybrid model explanation">
          <p>{helpContent}</p>
        </div>
      )}
    </>
  )
}

/** Overlay shown inside a chart card when there is no data to render. */
function ChartEmpty({ height }: { height: number }) {
  return (
    <div className="chart-empty-state" style={{ height }}>
      No data to display
    </div>
  )
}

function FormulaBlock({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="formula-lines">
      {lines.map((line, i) => (
        <div key={i} className={`formula-line${i % 2 === 1 ? ' formula-line-alt' : ''}`}>
          <span className="formula-line-num">{i + 1}</span>
          <code className="formula-line-text">{line || '\u00A0'}</code>
        </div>
      ))}
    </div>
  )
}

/** Displays the pricing source as a small badge (live / cached / fallback / manual). */
function PricingSourceBadge({ source, asOf }: { source: string; asOf?: string }) {
  const config: Record<string, { icon: string; label: string; className: string }> = {
    live:     { icon: '\u2713', label: 'Live pricing',     className: 'pricing-badge pricing-badge-live' },
    cached:   { icon: '\u23F1', label: 'Cached pricing',   className: 'pricing-badge pricing-badge-cached' },
    fallback: { icon: '\u26A0', label: 'Fallback pricing', className: 'pricing-badge pricing-badge-fallback' },
    manual:   { icon: '\u270E', label: 'Custom rates',     className: 'pricing-badge pricing-badge-manual' },
  }
  const c = config[source] ?? config.fallback
  const dateStr = asOf ? new Date(asOf).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : ''
  return (
    <span className={c.className} title={dateStr ? `${c.label} as of ${dateStr}` : c.label}>
      {c.icon} {c.label}{dateStr ? ` (${dateStr})` : ''}
    </span>
  )
}

function FormStateMessage({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="form-state-message" role="status" aria-live="polite">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  )
}

function DeferredResult({ children, label = 'Loading visualization…', inline = false }: { children: ReactNode; label?: string; inline?: boolean }) {
  return (
    <Suspense fallback={<div className={`deferred-result${inline ? ' deferred-result-inline' : ''}`} role="status">{label}</div>}>
      {children}
    </Suspense>
  )
}

function App() {
  const reservationDescriptionId = useId()
  const [mode, setMode] = useState<Mode>('live')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const resultsRef = useRef<HTMLElement>(null)
  const hadAnalysisRef = useRef(false)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  const [calculationDetailsOpen, setCalculationDetailsOpen] = useState(false)

  // Chart zoom state — ECharts dataZoom
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null)
  const [granularityMinutes, setGranularityMinutes] = useState<1 | 5 | 15 | 30>(5)
  const [baseAnalysis, setBaseAnalysis] = useState<AnalysisResponse | null>(null)

  const [lookbackDays, setLookbackDays] = useState(14)
  const [reservationType, setReservationType] = useState<string>('Monthly Commitment (Estimated 64% off)')
  const [baselinePtu, setBaselinePtu] = useState<number | null>(null)
  const [focusTopics, setFocusTopics] = useState<FocusTopic[]>([])
  const [focusTopic, setFocusTopic] = useState('Cost Reduction')
  const [pricingRegions, setPricingRegions] = useState<PricingRegion[]>([])
  const [deploymentTypeOptions, setDeploymentTypeOptions] = useState<DeploymentTypeOption[]>([])
  const [selectedRegion, setSelectedRegion] = useState('eastus')
  const [selectedDeploymentType, setSelectedDeploymentType] = useState<'global' | 'data_zone' | 'regional'>('global')
  const [includeThrottle, setIncludeThrottle] = useState(false)

  // ── Pricing override state (Phase 2: Advanced Pricing) ──
  const [paygInputOverride, setPaygInputOverride] = useState<number | null>(null)
  const [paygOutputOverride, setPaygOutputOverride] = useState<number | null>(null)
  const [ptuHourlyOverride, setPtuHourlyOverride] = useState<number | null>(null)
  const [cacheMode, setCacheMode] = useState<'auto' | 'disabled' | 'override'>('auto')
  const [cacheMatchRateOverride, setCacheMatchRateOverride] = useState<number | null>(null)
  const [cachedInputRateOverride, setCachedInputRateOverride] = useState<number | null>(null)

  const [subscriptions, setSubscriptions] = useState<SubscriptionInfo[]>([])
  const [subscriptionsLoading, setSubscriptionsLoading] = useState(false)
  const [subscriptionId, setSubscriptionId] = useState(() => localStorage.getItem('ptu_last_subscription') || '')
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)
  const tenantIdHashRef = useRef('')
  const authAttemptKeyRef = useRef('')

  const [accounts, setAccounts] = useState<AccountInfo[]>([])
  const [accountKey, setAccountKey] = useState(() => localStorage.getItem('ptu_last_account') || '')

  const [deployments, setDeployments] = useState<DeploymentInfo[]>([])
  const [deploymentName, setDeploymentName] = useState(() => localStorage.getItem('ptu_last_deployment') || '')
  const [expandedWhyDeployment, setExpandedWhyDeployment] = useState<string | null>(null)

  // Persist last discovery selections to localStorage (PRD §7 — remember last selection)
  useEffect(() => { if (subscriptionId) localStorage.setItem('ptu_last_subscription', subscriptionId) }, [subscriptionId])
  useEffect(() => { if (accountKey) localStorage.setItem('ptu_last_account', accountKey) }, [accountKey])
  useEffect(() => { if (deploymentName) localStorage.setItem('ptu_last_deployment', deploymentName) }, [deploymentName])

  // Refresh discovery: increment key to re-trigger fetch effects
  const [discoveryKey, setDiscoveryKey] = useState(0)
  const refreshDiscovery = useCallback(() => {
    api.refreshDiscoveryCache().catch(() => {})  // best-effort backend cache clear
    setSubscriptions([])
    setAccounts([])
    setDeployments([])
    setSubscriptionId('')
    setAccountKey('')
    setDeploymentName('')
    setError('')
    setDiscoveryKey((k) => k + 1)
  }, [])

  // ── App-level view: Deployment Advisor vs PTU Calculator ──
  const [activeView, setActiveView] = useState<'advisor' | 'calculator'>('advisor')

  // ── Consolidation mode state ──
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('single')
  const [selectedDeployments, setSelectedDeployments] = useState<string[]>([])
  const [selectedModelGroup, setSelectedModelGroup] = useState<string | null>(null)
  const [consolidationSummary, setConsolidationSummary] = useState<ConsolidationSummary | null>(null)
  const [deploymentPreviews, setDeploymentPreviews] = useState<DeploymentPreview[]>([])
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── PTU Calculator form state ──
  const [calcModel, setCalcModel] = useState('gpt-4o')
  const [calcAvgTpm, setCalcAvgTpm] = useState(50000)
  const [calcPeakTpm, setCalcPeakTpm] = useState(120000)
  const [calcOutputPct, setCalcOutputPct] = useState(40)
  const [calcCachePct, setCalcCachePct] = useState(0)
  const [calcPeakHours, setCalcPeakHours] = useState(4)
  const [calcRegion, setCalcRegion] = useState('eastus')
  const [calcDeployType, setCalcDeployType] = useState<'global' | 'data_zone' | 'regional'>('global')

  // ── ECharts zoom state (replaces old drag-to-zoom) ──
  const chartTimestamps = useMemo(() => analysis?.charts.tokens.timestamps ?? [], [analysis])
  const { zoomState, onDataZoom, resetZoom, getReAnalyzeWindow } = useChartZoom(chartTimestamps)

  // ── Consolidation: group deployments by (model, sku_type) ──
  const deploymentGroups = useMemo(() => {
    const groups: Record<string, DeploymentInfo[]> = {}
    for (const d of deployments) {
      const key = `${d.model}::${d.sku_type}`
      if (!groups[key]) groups[key] = []
      groups[key].push(d)
    }
    return groups
  }, [deployments])

  /** Deployments grouped by model family for the single deployment picker. */
  const deploymentFamilyGroups = useMemo(() => groupDeploymentsByFamily(deployments), [deployments])

  /** Show a transient toast notification that auto-dismisses after 3 seconds. */
  const showToast = useCallback((message: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToastMessage(message)
    toastTimerRef.current = setTimeout(() => setToastMessage(null), 3000)
  }, [])

  /** Toggle a deployment checkbox within a model group (consolidation mode). */
  const toggleConsolidationDeployment = useCallback((deployName: string, groupKey: string) => {
    // If selecting in a different group, switch group and start fresh
    if (selectedModelGroup !== groupKey) {
      setSelectedModelGroup(groupKey)
      setSelectedDeployments([deployName])
      showToast('Switched model group — previous selection cleared. PTU capacity is model-specific.')
      return
    }
    // Same group — toggle the checkbox
    setSelectedDeployments((prev) =>
      prev.includes(deployName) ? prev.filter((n) => n !== deployName) : [...prev, deployName]
    )
  }, [selectedModelGroup, showToast])

  /** Reset consolidation state when switching analysis mode. */
  const handleAnalysisModeChange = useCallback((newMode: AnalysisMode) => {
    setAnalysisMode(newMode)
    setSelectedDeployments([])
    setSelectedModelGroup(null)
    setConsolidationSummary(null)
    setAnalysis(null)
    if (newMode !== 'consolidation') setDeploymentPreviews([])
  }, [])

  // Fetch lightweight preview data when entering consolidation mode (demo only — live requires workspace)
  useEffect(() => {
    if (analysisMode !== 'consolidation') return
    if (mode !== 'demo') { setDeploymentPreviews([]); return }
    let cancelled = false
    api.deploymentPreview({ mode: 'demo', focusTopic: focusTopic, lookbackDays: lookbackDays })
      .then((items) => { if (!cancelled) setDeploymentPreviews(items) })
      .catch(() => { if (!cancelled) setDeploymentPreviews([]) })
    return () => { cancelled = true }
  }, [analysisMode, mode, focusTopic, lookbackDays])

  useEffect(() => {
    api.focusTopics()
      .then((items) => {
        setFocusTopics(items)
        if (items.length > 0) {
          setFocusTopic((current) => current || items[0].name)
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api.pricingOptions()
      .then((options) => {
        setPricingRegions(options.regions.length > 0 ? options.regions : FALLBACK_PRICING_REGIONS)
        setDeploymentTypeOptions(options.deployment_types.length > 0 ? options.deployment_types : FALLBACK_DEPLOYMENT_TYPES)
      })
      .catch((e: Error) => {
        const message = e.message || ''
        if (message.includes('Not Found') || message.includes('{"detail":"Not Found"}')) {
          setPricingRegions(FALLBACK_PRICING_REGIONS)
          setDeploymentTypeOptions(FALLBACK_DEPLOYMENT_TYPES)
          return
        }
        setError(e.message)
      })
  }, [])

  useEffect(() => {
    if (mode !== 'live') {
      tenantIdHashRef.current = ''
      authAttemptKeyRef.current = ''
      setAuthStatus(null)
      return
    }
    let cancelled = false
    const attemptKey = `${mode}|${discoveryKey}`
    if (authAttemptKeyRef.current !== attemptKey) {
      authAttemptKeyRef.current = attemptKey
      emitAzureConnectStarted({ policy_version: POLICY_VERSION, tenant_id_hash: '' })
    }
    api.authStatus()
      .then((status) => {
        if (cancelled) return
        setAuthStatus(status)
        const tidHash = hashTenantId(status.tenant_id || '')
        tenantIdHashRef.current = tidHash
        if (status.authenticated) {
          emitAzureConnectSucceeded({ policy_version: POLICY_VERSION, tenant_id_hash: tidHash, display_name: status.display_name })
        } else {
          emitAzureConnectFailed({ policy_version: POLICY_VERSION, tenant_id_hash: tidHash, error_type: status.error || 'auth_failed' })
        }
      })
      .catch((e) => {
        if (cancelled) return
        tenantIdHashRef.current = ''
        setAuthStatus({ authenticated: false, display_name: '', email: '', tenant_id: '', error: 'Failed to check authentication status.' })
        emitAzureConnectFailed({ policy_version: POLICY_VERSION, tenant_id_hash: '', error_type: e instanceof Error ? e.message : 'network_error' })
      })
      return () => { cancelled = true }
  }, [mode, discoveryKey])

  useEffect(() => {
    if (mode !== 'live') {
      return
    }
    let cancelled = false
    setSubscriptionsLoading(true)
    const t0 = performance.now()
    api.subscriptions()
      .then((items) => {
        if (cancelled) return
        const elapsed = performance.now() - t0
        setSubscriptions(items)
        emitDiscoverySubscriptionsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, subscription_count: items.length })
        if (elapsed > PERF_BUDGET.FULL_DISCOVERY_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, operation: 'subscriptions_load', budget_ms: PERF_BUDGET.FULL_DISCOVERY_MS, actual_ms: elapsed })
        }
        if (items.length > 0) {
          setSubscriptionId((current) => current || items[0].subscription_id)
        }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setSubscriptionsLoading(false) })
    return () => { cancelled = true }
  }, [mode, discoveryKey])

  useEffect(() => {
    if (mode !== 'live' || !subscriptionId) {
      return
    }
    setAccounts([])
    setAccountKey('')
    setDeployments([])
    setDeploymentName('')

    let cancelled = false
    const t0 = performance.now()
    api.accounts(subscriptionId)
      .then((items) => {
        if (cancelled) return
        const elapsed = performance.now() - t0
        setAccounts(items)
        emitDiscoveryAccountsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, account_count: items.length })
        if (elapsed > PERF_BUDGET.CACHED_CHANGE_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, operation: 'accounts_load', budget_ms: PERF_BUDGET.CACHED_CHANGE_MS, actual_ms: elapsed })
        }
        if (items.length > 0) {
          const first = `${items[0].resource_group}|${items[0].name}`
          setAccountKey(first)
        }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [mode, subscriptionId])

  const selectedAccount = useMemo(() => {
    return accounts.find((a) => `${a.resource_group}|${a.name}` === accountKey) ?? null
  }, [accounts, accountKey])

  useEffect(() => {
    if (!selectedAccount) return
    const location = selectedAccount.location.toLowerCase().replace(/\s+/g, '')
    if (pricingRegions.some((region) => region.name === location)) {
      setSelectedRegion(location)
    }
  }, [selectedAccount, pricingRegions])

  useEffect(() => {
    if (mode !== 'live' || !subscriptionId || !selectedAccount) {
      return
    }
    setDeployments([])
    setDeploymentName('')

    let cancelled = false
    const t0 = performance.now()
    api.deployments(subscriptionId, selectedAccount.resource_group, selectedAccount.name)
      .then((items) => {
        if (cancelled) return
        const elapsed = performance.now() - t0
        // Sort: PTU-eligible first, then alphabetical within each group
        const sorted = [...items].sort((a, b) => {
          if (a.ptu_eligible !== b.ptu_eligible) return a.ptu_eligible ? -1 : 1
          return a.name.localeCompare(b.name)
        })
        setDeployments(sorted)
        emitDiscoveryDeploymentsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, deployment_count: sorted.length })
        if (elapsed > PERF_BUDGET.CACHED_CHANGE_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, operation: 'deployments_load', budget_ms: PERF_BUDGET.CACHED_CHANGE_MS, actual_ms: elapsed })
        }
        // Auto-select the first eligible deployment
        const firstEligible = sorted.find((d) => d.ptu_eligible)
        if (firstEligible) {
          setDeploymentName(firstEligible.name)
        } else if (sorted.length > 0) {
          setDeploymentName('')  // No eligible deployments — don't select any
        }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [mode, subscriptionId, selectedAccount])

  const runAnalysis = useCallback(async ({ preserveCurrent = false, timeWindow = null, updateCharts = true }: RunAnalysisOptions = {}) => {
    setLoading(true)
    setError('')
    emitAnalysisRunStarted({ policy_version: POLICY_VERSION, tenant_id_hash: tenantIdHashRef.current, mode })
    if (!preserveCurrent) {
      setAnalysis(null)
      setBaseAnalysis(null)
      setBaselinePtu(null) // Reset so next analysis picks its own default
      resetZoom()
      setSelectedTimestamp(null)
      setConsolidationSummary(null)
    }
    try {
      // Only send baseline_ptu when known (after first analysis sets the default)
      const ptuParam = baselinePtu != null ? { baseline_ptu: baselinePtu } : {}
      const windowParams = timeWindow ? { window_start: timeWindow.start, window_end: timeWindow.end } : {}
      const overrideParams: Record<string, number | string> = { cache_mode: cacheMode }
      if (paygInputOverride != null) overrideParams.payg_input_rate_override = paygInputOverride
      if (paygOutputOverride != null) overrideParams.payg_output_rate_override = paygOutputOverride
      if (ptuHourlyOverride != null) overrideParams.ptu_hourly_rate_override = ptuHourlyOverride
      if (cacheMode === 'override' && cacheMatchRateOverride != null) overrideParams.cache_match_rate_override_pct = cacheMatchRateOverride
      if (cachedInputRateOverride != null) overrideParams.cached_input_rate_override = cachedInputRateOverride

      // ── Consolidation mode ──
      if (analysisMode === 'consolidation') {
        if (mode === 'demo') {
          const result = await api.analyzeConsolidation({
            mode: 'demo',
            focus_topic: focusTopic,
            lookback_days: lookbackDays,
            granularity_minutes: granularityMinutes,
            reservation_type: reservationType,
            region: selectedRegion,
            deployment_type: selectedDeploymentType,
            include_throttle: includeThrottle,
            ...windowParams,
            ...ptuParam,
            ...overrideParams,
          })
          if (baselinePtu == null) {
            setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
          }
          setConsolidationSummary(result.consolidation_summary)
          if (updateCharts || !analysis) {
            setAnalysis(result)
            setBaseAnalysis(result)
          } else {
            setAnalysis((current) => {
              if (!current) return result
              return { ...current, recommendation: result.recommendation, confidence: result.confidence, summary: result.summary, explanation: result.explanation, what_would_change: result.what_would_change, data_quality: result.data_quality, analysis_period: result.analysis_period, dimensions: result.dimensions, metrics: result.metrics, cost_analysis: result.cost_analysis, insights: result.insights, charts: { ...current.charts, daily_cost: result.charts.daily_cost, cost_curves: result.charts.cost_curves, prompt_cache: result.charts.prompt_cache } }
            })
          }
          return
        }

        // Live consolidation
        if (!subscriptionId || !selectedAccount || selectedDeployments.length < 2) {
          throw new Error('Please select subscription, account, and at least 2 deployments.')
        }
        const result = await api.analyzeConsolidation({
          mode: 'live',
          lookback_days: lookbackDays,
          granularity_minutes: granularityMinutes,
          subscription_id: subscriptionId,
          resource_group: selectedAccount.resource_group,
          workspace: selectedAccount.name,
          deployments: selectedDeployments,
          focus_topic: focusTopic,
          reservation_type: reservationType,
          region: selectedRegion,
          deployment_type: selectedDeploymentType,
          include_throttle: includeThrottle,
          ...windowParams,
          ...ptuParam,
          ...overrideParams,
        })
        if (baselinePtu == null) {
          setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
        }
        setConsolidationSummary(result.consolidation_summary)
        if (updateCharts || !analysis) {
          setAnalysis(result)
          setBaseAnalysis(result)
        } else {
          setAnalysis((current) => {
            if (!current) return result
            return { ...current, recommendation: result.recommendation, confidence: result.confidence, summary: result.summary, explanation: result.explanation, what_would_change: result.what_would_change, data_quality: result.data_quality, analysis_period: result.analysis_period, dimensions: result.dimensions, metrics: result.metrics, cost_analysis: result.cost_analysis, insights: result.insights, charts: { ...current.charts, cost_curves: result.charts.cost_curves, prompt_cache: result.charts.prompt_cache } }
          })
        }
        return
      }

      // ── Single deployment mode (existing flow) ──
      if (mode === 'demo') {
        const result = await api.analyze({
          mode: 'demo',
          focus_topic: focusTopic,
          lookback_days: lookbackDays,
          granularity_minutes: granularityMinutes,
          reservation_type: reservationType,
          region: selectedRegion,
          deployment_type: selectedDeploymentType,
          include_throttle: includeThrottle,
          ...windowParams,
          ...ptuParam,
          ...overrideParams,
        })
        // Initialise the PTU slider on first analysis load
        if (baselinePtu == null) {
          setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
        }
        if (updateCharts || !analysis) {
          setAnalysis(result)
          setBaseAnalysis(result)
        } else {
          setAnalysis((current) => {
            if (!current) return result
            return {
              ...current,
              recommendation: result.recommendation,
              confidence: result.confidence,
              summary: result.summary,
              explanation: result.explanation,
              what_would_change: result.what_would_change,
              data_quality: result.data_quality,
              analysis_period: result.analysis_period,
              dimensions: result.dimensions,
              metrics: result.metrics,
              cost_analysis: result.cost_analysis,
              insights: result.insights,
              charts: {
                ...current.charts,
                daily_cost: result.charts.daily_cost,
                cost_curves: result.charts.cost_curves,
                prompt_cache: result.charts.prompt_cache,
              },
            }
          })
        }
        return
      }

      if (!subscriptionId || !selectedAccount || !deploymentName) {
        throw new Error('Please select subscription, account, and deployment.')
      }

      const result = await api.analyze({
        mode: 'live',
        lookback_days: lookbackDays,
        granularity_minutes: granularityMinutes,
        subscription_id: subscriptionId,
        resource_group: selectedAccount.resource_group,
        workspace: selectedAccount.name,
        deployment: deploymentName,
        focus_topic: focusTopic,
        reservation_type: reservationType,
        region: selectedRegion,
        deployment_type: selectedDeploymentType,
        include_throttle: includeThrottle,
        ...windowParams,
        ...ptuParam,
        ...overrideParams,
      })
      // Initialise the PTU slider on first analysis load
      if (baselinePtu == null) {
        setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
      }
      if (updateCharts || !analysis) {
        setAnalysis(result)
        setBaseAnalysis(result)
      } else {
        setAnalysis((current) => {
          if (!current) return result
          return {
            ...current,
            recommendation: result.recommendation,
            confidence: result.confidence,
            summary: result.summary,
            explanation: result.explanation,
            what_would_change: result.what_would_change,
            data_quality: result.data_quality,
            analysis_period: result.analysis_period,
            dimensions: result.dimensions,
            metrics: result.metrics,
            cost_analysis: result.cost_analysis,
            insights: result.insights,
            charts: {
              ...current.charts,
              cost_curves: result.charts.cost_curves,
              prompt_cache: result.charts.prompt_cache,
            },
          }
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }, [
    mode,
    analysisMode,
    focusTopic,
    lookbackDays,
    granularityMinutes,
    reservationType,
    baselinePtu,
    selectedRegion,
    selectedDeploymentType,
    includeThrottle,
    subscriptionId,
    selectedAccount,
    deploymentName,
    selectedDeployments,
    analysis,
    paygInputOverride,
    paygOutputOverride,
    ptuHourlyOverride,
    cacheMode,
    cacheMatchRateOverride,
    cachedInputRateOverride,
    resetZoom,
  ])

  const previousAssumptionKey = useRef('')
  const previousAssumptionParts = useRef<Record<string, string | number>>({})

  useEffect(() => {
    if (!analysis) {
      previousAssumptionKey.current = ''
      previousAssumptionParts.current = {}
      return
    }

    const zoomWindow = getReAnalyzeWindow()

    const parts: Record<string, string | number> = {
      reservationType,
      baselinePtu: baselinePtu ?? analysis.cost_analysis.hybrid.default_baseline_ptu,
      selectedRegion,
      selectedDeploymentType,
      granularityMinutes,
      includeThrottle: includeThrottle ? 1 : 0,
      paygInputOverride: paygInputOverride ?? -1,
      paygOutputOverride: paygOutputOverride ?? -1,
      ptuHourlyOverride: ptuHourlyOverride ?? -1,
      cacheMode,
      cacheMatchRateOverride: cacheMatchRateOverride ?? -1,
      cachedInputRateOverride: cachedInputRateOverride ?? -1,
    }
    const currentKey = `${reservationType}|${baselinePtu}|${selectedRegion}|${selectedDeploymentType}|${granularityMinutes}|${includeThrottle}|${paygInputOverride}|${paygOutputOverride}|${ptuHourlyOverride}|${cacheMode}|${cacheMatchRateOverride}|${cachedInputRateOverride}`
    if (!previousAssumptionKey.current) {
      previousAssumptionKey.current = currentKey
      previousAssumptionParts.current = parts
      return
    }

    if (previousAssumptionKey.current === currentKey || loading) {
      return
    }
    if (
      cacheMode === 'override'
      && (
        cacheMatchRateOverride == null
        || cacheMatchRateOverride < 0
        || cacheMatchRateOverride > 100
      )
    ) {
      return
    }

    // Detect which field(s) changed and emit telemetry
    const prev = previousAssumptionParts.current
    for (const field of Object.keys(parts)) {
      if (prev[field] !== parts[field]) {
        emitAssumptionChanged({
          policy_version: POLICY_VERSION,
          recommendation: analysis.recommendation,
          model_name: analysis.metrics.model_name,
          deployment_type: selectedDeploymentType,
          changed_field: field,
          old_value: prev[field] ?? '',
          new_value: parts[field],
          reservation_term: reservationType,
          baseline_ptu: baselinePtu ?? analysis.cost_analysis.hybrid.default_baseline_ptu,
        })
      }
    }

    previousAssumptionKey.current = currentKey
    previousAssumptionParts.current = parts
    const timer = setTimeout(() => {
      runAnalysis({ preserveCurrent: true, timeWindow: zoomWindow ? { start: zoomWindow.window_start, end: zoomWindow.window_end } : null, updateCharts: !zoomWindow })
    }, 250)

    return () => clearTimeout(timer)
  }, [analysis, reservationType, baselinePtu, selectedRegion, selectedDeploymentType, granularityMinutes, includeThrottle, paygInputOverride, paygOutputOverride, ptuHourlyOverride, cacheMode, cacheMatchRateOverride, cachedInputRateOverride, loading, runAnalysis, getReAnalyzeWindow])

  const previousCacheTelemetryKey = useRef('')
  useEffect(() => {
    const cache = analysis?.cost_analysis.cache_impact
    if (!analysis || !cache) return
    const key = `${cache.source}|${cache.quality}|${cache.coverage_pct}|${cache.ptu_avoided}`
    if (previousCacheTelemetryKey.current === key) return
    previousCacheTelemetryKey.current = key
    const coverage_bucket = cache.coverage_pct <= 0 ? '0' : cache.coverage_pct < 50 ? '1-49' : cache.coverage_pct < 80 ? '50-79' : '80-100'
    const ptu_avoided_bucket = cache.ptu_avoided <= 0 ? '0' : cache.ptu_avoided <= 5 ? '1-5' : cache.ptu_avoided <= 15 ? '6-15' : '16+'
    emitCacheTelemetry(cache.quality === 'limited' || cache.quality === 'unavailable' ? 'cache_data_limited' : 'cache_adjustment_applied', {
      policy_version: POLICY_VERSION,
      recommendation: analysis.recommendation,
      model_name: analysis.metrics.model_name,
      deployment_type: analysis.cost_analysis.pricing.deployment_type,
      cache_source: cache.source,
      cache_quality: cache.quality,
      coverage_bucket,
      ptu_avoided_bucket,
    })
  }, [analysis])

  // ── Telemetry: cost_recalculated ──
  const hasInsufficientCostData = analysis?.cost_analysis.status === 'insufficient_data'
    || analysis?.recommendation === 'insufficient_data'

  const previousCostKey = useRef('')
  useEffect(() => {
    if (!analysis || loading || hasInsufficientCostData) return
    const ca = analysis.cost_analysis
    const costKey = `${ca.payg.payg_total}|${ca.hybrid.hybrid_total}|${ca.comparison.savings}|${ca.hybrid.baseline_ptu}`
    if (previousCostKey.current === costKey) return
    previousCostKey.current = costKey

    emitCostRecalculated({
      policy_version: POLICY_VERSION,
      recommendation: analysis.recommendation,
      model_name: analysis.metrics.model_name,
      deployment_type: ca.pricing.deployment_type,
      payg_monthly: ca.payg.payg_total,
      hybrid_monthly: ca.hybrid.hybrid_total,
      savings: ca.comparison.savings,
      savings_pct: ca.comparison.savings_pct,
      baseline_ptu: ca.hybrid.baseline_ptu,
      reservation_term: ca.pricing.reservation_type,
    })
  }, [analysis, loading, hasInsufficientCostData])

  useEffect(() => {
    if (!expandedChart) return
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpandedChart(null) }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [expandedChart])

  useEffect(() => {
    const enteringResults = analysis !== null && !hadAnalysisRef.current
    hadAnalysisRef.current = analysis !== null
    if (!enteringResults) return

    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    resultsRef.current?.focus({ preventScroll: true })
  }, [analysis])

  const recommendationClass = useMemo(() => {
    if (!analysis) return ''
    if (analysis.recommendation === 'ptu_recommended') return 'rec-positive'
    if (analysis.recommendation === 'ptu_not_recommended') return 'rec-negative'
    if (analysis.recommendation === 'insufficient_data') return 'rec-insufficient'
    return 'rec-borderline'
  }, [analysis])

  /** Adaptive X-axis tick formatter based on data density and date span. */
  const smartDateFmt = useMemo(() => {
    if (!analysis) return formatDateLabel
    const ts = analysis.charts.tokens.timestamps
    return ts.length > 0 ? makeSmartDateFormatter(ts) : formatDateLabel
  }, [analysis])

  const tokenChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.tokens
    return series.timestamps.map((ts, idx) => ({
      time: ts,
      prompt: series.prompt[idx] ?? 0,
      completion: series.completion[idx] ?? 0,
      total: series.total[idx] ?? 0,
    }))
  }, [analysis])

  const requestsChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.requests
    return series.timestamps.map((ts, idx) => ({
      time: ts,
      successful: series.successful[idx] ?? 0,
      throttled: series.throttled[idx] ?? 0,
      total: series.total[idx] ?? 0,
    }))
  }, [analysis])

  const dailyCostChartData = useMemo(() => {
    if (!analysis) return []
    const dc = analysis.charts.daily_cost
    return dc.dates.map((date, idx) => ({
      time: date,
      input_cost: dc.input_cost[idx] ?? 0,
      output_cost: dc.output_cost[idx] ?? 0,
      total_cost: dc.total_cost[idx] ?? 0,
      avg: dc.avg_daily_cost,
      ptu_ref: dc.ptu_daily_cost,
    }))
  }, [analysis])

  const throttleChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.throttling
    return series.timestamps.map((ts, idx) => ({
      time: ts,
      throttled: series.values[idx] ?? 0,
    }))
  }, [analysis])

  const promptCacheTotals = useMemo(() => {
    const promptCache = analysis?.charts.prompt_cache
    if (!promptCache) return { active: 0, cached: 0, total: 0, cachedSharePct: 0 }
    const active = promptCache.active_prompt_tokens.reduce((total, value) => total + value, 0)
    const cached = promptCache.cached_prompt_tokens.reduce((total, value) => total + value, 0)
    const total = active + cached
    return {
      active,
      cached,
      total,
      cachedSharePct: total > 0 ? (cached / total) * 100 : 0,
    }
  }, [analysis])

  const cacheImpactView = useMemo(() => {
    const impact = analysis?.cost_analysis.cache_impact
    const telemetry = analysis?.metrics.cache_match_rate
    return {
      available: impact != null,
      applied: impact?.applied ?? false,
      source: impact?.source ?? telemetry?.source ?? analysis?.charts.prompt_cache?.source ?? 'unavailable',
      quality: impact?.quality ?? telemetry?.quality ?? 'unavailable',
      coveragePct: impact?.coverage_pct ?? telemetry?.coverage_pct ?? 0,
      ptuAvoided: impact?.ptu_avoided ?? 0,
      normalizedTpmReductionPct: impact?.normalized_tpm_reduction_pct ?? 0,
    }
  }, [analysis])

  const tpmChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.tpm
    const refTpm = analysis.charts.cost_curves.break_even_tpm ?? series.p25
    return series.timestamps.map((ts, idx) => ({
      time: ts,
      tpm: series.values[idx] ?? 0,
      avg: series.avg,
      refLine: refTpm,
    }))
  }, [analysis])

  /** Label for the TPM reference line (break-even or P25). */
  const tpmRefLabel = useMemo(() => {
    if (!analysis) return 'P25'
    return analysis.charts.cost_curves.break_even_tpm ? 'Break-even' : 'P25'
  }, [analysis])

  const costCurveData = useMemo(() => {
    if (!analysis) return []
    const c = analysis.charts.cost_curves
    return c.sustained_tpm.map((x, idx) => ({
      sustainedTpm: x,
      payg: c.payg_monthly[idx] ?? 0,
      hybrid: c.ptu_spill_monthly[idx] ?? 0,
    }))
  }, [analysis])

  // ── Per-deployment chart data (consolidation mode only) ──
  const perDepCharts = useMemo<ConsolidationCharts | null>(() => {
    if (!analysis || !consolidationSummary) return null
    const charts = analysis.charts as ConsolidationCharts
    // Guard: only if per_deployment data is present
    if (!charts.tokens?.per_deployment) return null
    return charts
  }, [analysis, consolidationSummary])

  // ── Auto re-analyze when zoom window changes (debounced) ──
  const previousZoomKey = useRef('')
  useEffect(() => {
    if (!analysis || !zoomState.isDirty) {
      previousZoomKey.current = ''
      return
    }
    const win = getReAnalyzeWindow()
    if (!win) return
    const key = `${win.window_start}|${win.window_end}`
    if (previousZoomKey.current === key || loading) return
    previousZoomKey.current = key
    const timer = setTimeout(() => {
      runAnalysis({ preserveCurrent: true, timeWindow: { start: win.window_start, end: win.window_end }, updateCharts: false })
    }, 500)
    return () => clearTimeout(timer)
  }, [analysis, zoomState, loading, getReAnalyzeWindow, runAnalysis])

  const getChartHeight = useCallback((chartKey: string, baseHeight: number) => {
    if (expandedChart !== chartKey) return baseHeight
    return Math.max(420, window.innerHeight - 180)
  }, [expandedChart])

  const recommendationTitle = useMemo(() => {
    if (!analysis) return ''
    if (analysis.recommendation === 'ptu_recommended') return 'Recommendation: Use PTU baseline with spillover'
    if (analysis.recommendation === 'ptu_not_recommended') return 'Recommendation: Stay on PAYG for now'
    if (analysis.recommendation === 'insufficient_data') return 'Recommendation unavailable: More traffic data required'
    return 'Recommendation: Borderline — validate before committing'
  }, [analysis])

  const recommendationSummary = useMemo(() => {
    if (!analysis) return ''
    if (analysis.recommendation === 'ptu_recommended') {
      return 'PTU is recommended. Your current workload and cost profile favor baseline PTU with spillover.'
    }
    if (analysis.recommendation === 'ptu_not_recommended') {
      return 'PTU is not recommended. Your current workload characteristics are better suited for PAYG.'
    }
    if (analysis.recommendation === 'insufficient_data') {
      return 'No token usage was observed in this window. Collect representative traffic before comparing PTU and PAYG.'
    }
    return 'PTU and PAYG are currently close. Validate with additional data before committing.'
  }, [analysis])

  const selectedRegionMeta = useMemo(() => {
    return pricingRegions.find((region) => region.name === selectedRegion) ?? null
  }, [pricingRegions, selectedRegion])

  const selectedDeploymentTypeMeta = useMemo(() => {
    return deploymentTypeOptions.find((item) => item.name === selectedDeploymentType) ?? null
  }, [deploymentTypeOptions, selectedDeploymentType])

  const breakEvenStatus = useMemo(() => {
    if (!analysis || hasInsufficientCostData) return null
    const cc = analysis.charts.cost_curves
    const selectedPtu = cc.selected_ptu
    const avgTpm = analysis.metrics.avg_tpm
    const safetyVerdict = analysis.cost_analysis.commitment_safety?.safety_verdict
    const safetyLabel = safetyVerdict ? (VERDICT_LABELS[safetyVerdict] ?? safetyVerdict) : 'unknown'
    const reason = cc.break_even_reason

    if (!cc.break_even_tpm || avgTpm <= 0) {
      if (reason === 'ptu_always_cheaper') {
        return { tone: 'positive' as const, breakEvenTpm: null as number | null, avgTpm, distancePct: 0, selectedPtu, text: `PTU is cheaper than PAYG at all usage levels for ${selectedPtu} PTU. Safety verdict: ${safetyLabel}.` }
      }
      return { tone: 'negative' as const, breakEvenTpm: null as number | null, avgTpm, distancePct: 0, selectedPtu, text: `No economic break-even exists for ${selectedPtu} PTU in the no-spillover range. At your usage level, PAYG is more cost-effective for this commitment size. Safety verdict: ${safetyLabel}.` }
    }

    const breakEven = cc.break_even_tpm
    const upperBreakEven = cc.upper_break_even_tpm
    if (upperBreakEven) {
      const insideRange = avgTpm >= breakEven && avgTpm <= upperBreakEven
      const range = `${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })}-${upperBreakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM`
      const distancePct = avgTpm < breakEven
        ? ((avgTpm - breakEven) / breakEven) * 100
        : avgTpm > upperBreakEven
          ? ((avgTpm - upperBreakEven) / upperBreakEven) * 100
          : Math.abs(avgTpm - breakEven) <= Math.abs(upperBreakEven - avgTpm)
            ? ((avgTpm - breakEven) / breakEven) * 100
            : ((avgTpm - upperBreakEven) / upperBreakEven) * 100
      return {
        tone: insideRange ? 'positive' as const : 'negative' as const,
        breakEvenTpm: breakEven,
        avgTpm,
        distancePct,
        selectedPtu,
        text: `Economic break-even range for ${selectedPtu} PTU is ${range}. Your avg TPM is ${insideRange ? 'inside' : 'outside'} that range, so the economic signal favors ${insideRange ? 'PTU' : 'PAYG'}. Safety verdict: ${safetyLabel}.`,
      }
    }
    const distancePct = ((avgTpm - breakEven) / breakEven) * 100
    if (distancePct > 10) {
      return { tone: 'positive' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is ${distancePct.toFixed(0)}% above that threshold, so the economic signal favors PTU. Safety verdict: ${safetyLabel}.` }
    }
    if (distancePct >= -10) {
      return { tone: 'neutral' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is near that threshold, so the economic signal is marginal. Safety verdict: ${safetyLabel}.` }
    }
    return { tone: 'negative' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is ${Math.abs(distancePct).toFixed(0)}% below that threshold, so the economic signal favors PAYG. Safety verdict: ${safetyLabel}.` }
  }, [analysis, hasInsufficientCostData])

  // ── Telemetry: break_even_marker_rendered / break_even_unavailable ──
  useEffect(() => {
    if (!breakEvenStatus || !analysis) return
    const dims = {
      policy_version: POLICY_VERSION,
      recommendation: analysis.recommendation,
      model_name: analysis.metrics.model_name,
      deployment_type: analysis.cost_analysis.pricing.deployment_type,
    }
    if (breakEvenStatus.breakEvenTpm != null) {
      emitBreakEvenMarkerRendered({
        ...dims,
        break_even_tpm: breakEvenStatus.breakEvenTpm,
        upper_break_even_tpm: analysis.charts.cost_curves.upper_break_even_tpm ?? null,
        avg_tpm: breakEvenStatus.avgTpm,
        distance_pct: breakEvenStatus.distancePct,
        tone: breakEvenStatus.tone as 'positive' | 'neutral' | 'negative',
      })
    } else {
      emitBreakEvenUnavailable({
        ...dims,
        selected_ptu: breakEvenStatus.selectedPtu,
        reason: 'break_even_exceeds_ptu_capacity',
      })
    }
  }, [breakEvenStatus, analysis])

  const differenceSummary = useMemo(() => {
    if (!analysis) return ''
    const savings = analysis.cost_analysis.comparison.savings
    const savingsPct = analysis.cost_analysis.comparison.savings_pct
    if (savings > 0) {
      return `PTU saves ${formatCurrency(Math.abs(savings))} (${savingsPct.toFixed(1)}%)`
    }
    if (savings < 0) {
      return `PTU costs ${formatCurrency(Math.abs(savings))} more (${Math.abs(savingsPct).toFixed(1)}%)`
    }
    return 'No material cost difference'
  }, [analysis])

  const currentBaselinePtu = analysis?.cost_analysis.hybrid.baseline_ptu ?? null
  const recommendedBaselinePtu = analysis?.cost_analysis.hybrid.default_baseline_ptu ?? null
  const maxViableBaselinePtu = analysis?.cost_analysis.hybrid.max_viable_baseline_ptu ?? null
  const showHeadroomAction = !!analysis && !!maxViableBaselinePtu && !!recommendedBaselinePtu && maxViableBaselinePtu > recommendedBaselinePtu
  const exploringHeadroom = !!analysis && !!currentBaselinePtu && !!recommendedBaselinePtu && currentBaselinePtu !== recommendedBaselinePtu

  // ── PTU Calculator computation ──
  const calcResult = useMemo(() => {
    const model = CALC_MODELS.find((m) => m.id === calcModel)
    if (!model || calcAvgTpm <= 0 || calcPeakTpm <= 0) return null

    const regionCfg = pricingRegions.find((r) => r.name === calcRegion) ?? FALLBACK_PRICING_REGIONS[0]
    const deployCfg = deploymentTypeOptions.find((d) => d.name === calcDeployType) ?? FALLBACK_DEPLOYMENT_TYPES[0]

    const MINUTES_PER_MONTH = 43200
    const HOURS_PER_MONTH = 720

    const inputFrac = (100 - calcOutputPct) / 100
    const outputFrac = calcOutputPct / 100

    const scopedTokenRates = model.tokenRates[calcDeployType]
    const [inputRate, configuredCachedInputRate, outputRate] = scopedTokenRates
    const cachedInputRate = calcDeployType === 'regional' && calcRegion !== 'eastus'
      ? inputRate
      : configuredCachedInputRate
    const activeInputFrac = inputFrac * (1 - calcCachePct / 100)
    const cachedInputFrac = inputFrac * (calcCachePct / 100)
    // Blended PAYG rate per 1M tokens including cached-input discount.
    const blendedRate = activeInputFrac * inputRate + cachedInputFrac * cachedInputRate + outputFrac * outputRate

    // PAYG monthly cost (avg TPM sustained 24/7)
    const monthlyTokens = calcAvgTpm * MINUTES_PER_MONTH
    const paygMonthly = (monthlyTokens / 1_000_000) * blendedRate

    // Effective multiplier: input tokens are 1:1, output tokens cost more PTU capacity
    const effectiveMult = activeInputFrac + outputFrac * model.outputRatio

    // PTU sizing parameters
    const increment = calcDeployType === 'regional' ? model.regionalInc : model.globalInc
    const minPtu = calcDeployType === 'regional' ? model.regionalMin : model.globalMin
    const baseRate = deployCfg.base_hourly_rate
    const regionMult = regionCfg.multiplier

    // Full PTU — sized to cover peak traffic entirely
    const effectivePeak = calcPeakTpm * effectiveMult
    const ptuFullRaw = effectivePeak / model.tpmPerPtu
    const ptuFull = Math.max(minPtu, Math.ceil(ptuFullRaw / increment) * increment)
    const ptuFullBase = ptuFull * baseRate * regionMult * HOURS_PER_MONTH

    const ptuOnDemand = ptuFullBase
    const ptu1Year = ptuFullBase * 0.75
    const ptu3Year = ptuFullBase * 0.55

    // Hybrid PTU — sized to avg, overflow spills to PAYG
    const effectiveAvg = calcAvgTpm * effectiveMult
    const ptuBaseRaw = effectiveAvg / model.tpmPerPtu
    const ptuBase = Math.max(minPtu, Math.ceil(ptuBaseRaw / increment) * increment)
    const ptuCapacityRaw = (ptuBase * model.tpmPerPtu) / effectiveMult
    const overflowTpm = Math.max(0, calcPeakTpm - ptuCapacityRaw)
    const overflowTokensMonthly = overflowTpm * 60 * calcPeakHours * 30
    // Spillover is conservatively priced as uncached because a separate
    // Standard target deployment can have different cache locality.
    const uncachedBlendedRate = inputFrac * inputRate + outputFrac * outputRate
    const overflowCost = (overflowTokensMonthly / 1_000_000) * uncachedBlendedRate

    const hybridBase = ptuBase * baseRate * regionMult * HOURS_PER_MONTH
    const hybridOnDemand = hybridBase + overflowCost
    const hybrid1Year = hybridBase * 0.75 + overflowCost
    const hybrid3Year = hybridBase * 0.55 + overflowCost

    // Break-even: analytical fixed-PTU formula (v3 model)
    // In the flat phase: PAYG = tpm × 43200 / 1M × rate, PTU = ptu_fixed
    // Cross: tpm = ptu_fixed × 1M / (43200 × rate)
    const ptuFixed = ptuBase * baseRate * regionMult * HOURS_PER_MONTH
    const breakEvenByTerm = [
      { term: 'On-Demand', discount: 1 },
      { term: '1-Year', discount: 0.75 },
      { term: '3-Year', discount: 0.55 },
    ].map(({ term, discount }) => ({
      term,
      ...calculateBreakEvenRange({
        ptuFixed: ptuFixed * discount,
        ptuCapacityRaw,
        paygRatePerMillion: blendedRate,
        spilloverRatePerMillion: uncachedBlendedRate,
      }),
    }))
    const { lower: breakEvenTpm, upper: upperBreakEvenTpm } = breakEvenByTerm[0]

    const scenarios: CalcScenario[] = [
      { name: 'PAYG', term: '\u2014', cost: paygMonthly, ptuUnits: 0 },
      { name: 'Full PTU', term: 'On-Demand', cost: ptuOnDemand, ptuUnits: ptuFull },
      { name: 'Full PTU', term: '1-Year', cost: ptu1Year, ptuUnits: ptuFull },
      { name: 'Full PTU', term: '3-Year', cost: ptu3Year, ptuUnits: ptuFull },
      { name: 'Hybrid', term: 'On-Demand', cost: hybridOnDemand, ptuUnits: ptuBase },
      { name: 'Hybrid', term: '1-Year', cost: hybrid1Year, ptuUnits: ptuBase },
      { name: 'Hybrid', term: '3-Year', cost: hybrid3Year, ptuUnits: ptuBase },
    ]

    const cheapest = scenarios.reduce((a, b) => (a.cost < b.cost ? a : b))
    const savings = paygMonthly - cheapest.cost
    const savingsPct = paygMonthly > 0 ? (savings / paygMonthly) * 100 : 0

    return {
      scenarios,
      cheapest,
      savings,
      savingsPct,
      paygMonthly,
      breakEvenTpm,
      upperBreakEvenTpm,
      breakEvenByTerm,
      ptuFull,
      ptuBase,
      ptuCapacityRaw,
      overflowTpm,
      blendedRate,
      monthlyTokens,
    }
  }, [calcModel, calcAvgTpm, calcPeakTpm, calcOutputPct, calcCachePct, calcPeakHours, calcRegion, calcDeployType, pricingRegions, deploymentTypeOptions])

  return (
    <div className="app-shell">
      {toastMessage && (
        <div className="toast-notification" role="status" aria-live="polite">
          <span>{toastMessage}</span>
          <button type="button" className="toast-dismiss" onClick={() => setToastMessage(null)} aria-label="Dismiss">&times;</button>
        </div>
      )}
      <main className={`container ${analysis ? 'results-container' : 'workspace-container'}`} aria-label="PTU Advisor workspace">
        {!analysis && (
          <header className="workspace-header" aria-label="PTU Advisor analysis workspace">
            <div className="workspace-brand">
              <span className="workspace-mark" aria-hidden="true">PTU</span>
              <h1>PTU Advisor</h1>
            </div>
            <p>Model observed traffic, compare commitment options, and make a defensible capacity decision.</p>
          </header>
        )}

        {!analysis && (
          <section className="panel panel-v2">
            <div className="panel-switcher">
              <button type="button" className={`panel-tab${activeView === 'advisor' ? ' active' : ''}`} onClick={() => setActiveView('advisor')} aria-pressed={activeView === 'advisor'}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8z"/><path d="M8 5v3l2 1"/></svg>
                Deployment Advisor
              </button>
              <button type="button" className={`panel-tab${activeView === 'calculator' ? ' active' : ''}`} onClick={() => setActiveView('calculator')} aria-pressed={activeView === 'calculator'}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="1" width="10" height="14" rx="1.5"/><path d="M5.5 4h5"/><path d="M5.5 7h1.5M9 7h1.5"/><path d="M5.5 10h1.5M9 10h1.5"/><path d="M5.5 13h1.5M9 13h1.5"/></svg>
                PTU Calculator
              </button>
            </div>

            {activeView === 'advisor' && (<div className="advisor-v2">
            <div className="panel-header">
              <div className="panel-step-indicator">
                <span className="step-dot step-active" />
                <span className="step-line" />
                <span className="step-dot" />
              </div>
              <div>
                <h2>Configure Analysis</h2>
                <p className="caption">Select a data source to begin your cost analysis.</p>
              </div>
            </div>

            <div className="mode-toggle advisor-mode-toggle">
              <button type="button" className={mode === 'live' ? 'active' : ''} onClick={() => setMode('live')} aria-pressed={mode === 'live'}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8z"/><path d="M8 5v3l2 1"/></svg>
                Connect to Azure
              </button>
              <button type="button" className={mode === 'demo' ? 'active' : ''} onClick={() => setMode('demo')} aria-pressed={mode === 'demo'}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h8M6 8h8M6 13h8"/><circle cx="2.5" cy="3" r="1" fill="currentColor"/><circle cx="2.5" cy="8" r="1" fill="currentColor"/><circle cx="2.5" cy="13" r="1" fill="currentColor"/></svg>
                Demo Mode
              </button>
            </div>

            {/* Auth Status Banner (PRD §4.1) */}
            {mode === 'live' && authStatus && (
              <div className={`auth-status-banner ${authStatus.authenticated ? 'auth-status-ok' : 'auth-status-error'}`} role="status" aria-live="polite">
                {authStatus.authenticated ? (
                  <>
                    <span className="auth-status-icon" aria-hidden="true">{'\u2713'}</span>
                    <span>Signed in as <strong>{authStatus.email || authStatus.display_name}</strong>{authStatus.tenant_id ? ` \u00B7 Tenant: ${authStatus.tenant_id.slice(0, 8)}\u2026` : ''}</span>
                  </>
                ) : (
                  <>
                    <span className="auth-status-icon" aria-hidden="true">{'\u2717'}</span>
                    <span>{authStatus.error || 'Not authenticated. Please run `az login` in your terminal, then refresh this page.'}</span>
                  </>
                )}
                <button type="button" className="refresh-discovery-btn" onClick={refreshDiscovery} title="Re-discover Azure resources (clears cache)">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M1 1v5h5"/><path d="M3.51 10a5 5 0 1 0 .49-5.37L1 7.5"/></svg>
                  Refresh
                </button>
              </div>
            )}

            <div className="form-grid advisor-form-grid">
              {mode === 'demo' ? (
                <>
                  <label>
                    Focus Topic
                    <select value={focusTopic} onChange={(e) => setFocusTopic(e.target.value)}>
                      {focusTopics.map((topic) => (
                        <option key={topic.name} value={topic.name}>
                          {topic.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <fieldset>
                    <legend>Analysis Mode</legend>
                    <div className="mode-toggle">
                      <button type="button" className={analysisMode === 'single' ? 'active' : ''} onClick={() => handleAnalysisModeChange('single')} aria-pressed={analysisMode === 'single'}>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="5"/><path d="M8 5v3l2 1"/></svg>
                        Single Deployment
                      </button>
                      <button type="button" className={analysisMode === 'consolidation' ? 'active' : ''} onClick={() => handleAnalysisModeChange('consolidation')} aria-pressed={analysisMode === 'consolidation'}>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="1.5" width="5" height="5" rx="1"/><rect x="9.5" y="1.5" width="5" height="5" rx="1"/><rect x="5.5" y="9.5" width="5" height="5" rx="1"/></svg>
                        Consolidation
                      </button>
                    </div>
                  </fieldset>
                </>
              ) : (
                <>
                  <fieldset>
                    <legend>Subscription</legend>
                    <div className="deployments-box subscription-box">
                      {subscriptionsLoading && subscriptions.length === 0 && (
                        <FormStateMessage
                          title="Loading subscriptions\u2026"
                          detail="Discovering Azure subscriptions for your account."
                        />
                      )}
                      {!subscriptionsLoading && subscriptions.length === 0 && (
                        <FormStateMessage
                          title="No subscriptions found"
                          detail="Confirm Azure sign-in and that this account has at least one enabled subscription."
                        />
                      )}
                      {subscriptions.map((subscription) => {
                        const stateView = getSubscriptionStateView(subscription.state)
                        return (
                          <label
                            key={subscription.subscription_id}
                            className={`radio-option deployment-option ${subscriptionId === subscription.subscription_id ? 'is-selected' : ''}`}
                          >
                            <input
                              type="radio"
                              name="subscription"
                              checked={subscriptionId === subscription.subscription_id}
                              onChange={() => setSubscriptionId(subscription.subscription_id)}
                            />
                            <span className="deployment-text">
                              <span className="deployment-title">{formatSubscriptionTitle(subscription)}</span>
                              <span className="deployment-meta subscription-meta">
                                <span className="subscription-id-chip">{subscription.subscription_id || 'n/a'}</span>
                                <span className={`subscription-state-chip state-${stateView.tone}`}>{stateView.label}</span>
                              </span>
                            </span>
                          </label>
                        )
                      })}
                    </div>
                  </fieldset>

                  <fieldset>
                    <legend>Azure OpenAI Account</legend>
                    <div className="radio-group">
                      {!subscriptionId && (
                        <FormStateMessage
                          title="Select a subscription"
                          detail="Choose a subscription first to load Azure OpenAI accounts."
                        />
                      )}
                      {subscriptionId && accounts.length === 0 && (
                        <FormStateMessage
                          title="No Azure OpenAI accounts found"
                          detail="No account is available in the selected subscription."
                        />
                      )}
                      {accounts.map((account) => {
                        const key = `${account.resource_group}|${account.name}`
                        return (
                          <label
                            key={key}
                            className={`radio-option deployment-option account-option ${accountKey === key ? 'is-selected' : ''}`}
                          >
                            <input
                              type="radio"
                              name="account"
                              checked={accountKey === key}
                              onChange={() => setAccountKey(key)}
                            />
                            <span className="deployment-text">
                              <span className="deployment-title">{account.name}</span>
                              <span className="deployment-meta account-meta">
                                <span className="account-rg-chip">{account.resource_group}</span>
                              </span>
                            </span>
                          </label>
                        )
                      })}
                    </div>
                  </fieldset>

                  <fieldset>
                    <legend>Deployment</legend>

                    {/* Analysis Mode Toggle */}
                    <div className="mode-toggle">
                      <button type="button" className={analysisMode === 'single' ? 'active' : ''} onClick={() => handleAnalysisModeChange('single')} aria-pressed={analysisMode === 'single'}>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="5"/><path d="M8 5v3l2 1"/></svg>
                        Single Deployment
                      </button>
                      <button type="button" className={analysisMode === 'consolidation' ? 'active' : ''} onClick={() => handleAnalysisModeChange('consolidation')} aria-pressed={analysisMode === 'consolidation'}>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="1.5" width="5" height="5" rx="1"/><rect x="9.5" y="1.5" width="5" height="5" rx="1"/><rect x="5.5" y="9.5" width="5" height="5" rx="1"/></svg>
                        Consolidation
                      </button>
                    </div>

                    {analysisMode === 'single' ? (
                      /* ── Single deployment picker (radio buttons, grouped by model family) ── */
                      <div className="deployments-box">
                        {!selectedAccount && (
                          <FormStateMessage
                            title="Select an account"
                            detail="Choose an Azure OpenAI account to load deployments."
                          />
                        )}
                        {selectedAccount && deployments.length === 0 && (
                          <FormStateMessage
                            title="No deployments found"
                            detail="Create a deployment in this account, then rerun analysis."
                          />
                        )}
                        {selectedAccount && deployments.length > 0 && !deployments.some((d) => d.ptu_eligible) && (
                          <div className="no-eligible-banner">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 10.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                            <div>
                              <strong>No PTU-Eligible Deployments</strong>
                              <p>This account has {deployments.length} deployment{deployments.length !== 1 ? 's' : ''}, but none use models that support Provisioned Throughput Units.</p>
                              <p>PTU-eligible models: GPT-4o, GPT-4.1, GPT-5, o1, o3-mini, o4-mini (and their variants).</p>
                              <p>Deploy a supported model to use PTU Advisor analysis, or switch to Demo Mode to explore the tool.</p>
                            </div>
                          </div>
                        )}
                        {deploymentFamilyGroups.map(({ family, deployments: familyDeps, allIneligible }) => (
                          <div key={family} className={`family-group${allIneligible ? ' is-all-ineligible' : ''}`} data-family={family}>
                            <div className="family-group-header">
                              <span className="family-group-label">{family}</span>
                              <span className="family-group-count">
                                {familyDeps.length} deployment{familyDeps.length !== 1 ? 's' : ''}
                                {allIneligible && <span className="eligibility-chip ineligible" style={{ marginLeft: 6 }}>PTU Not Available</span>}
                              </span>
                            </div>
                            {familyDeps.map((deployment) => {
                              const meta = getDeploymentMetaParts(deployment)
                              const isIneligible = !deployment.ptu_eligible
                              const isAlreadyPtu = /provisioned/i.test(deployment.sku_type || '')
                              const isWhyExpanded = expandedWhyDeployment === deployment.name
                              return (
                                <div key={deployment.name} className="family-group-item">
                                  <label
                                    className={`radio-option deployment-option${deploymentName === deployment.name ? ' is-selected' : ''}${isIneligible ? ' is-ineligible' : ''}`}
                                    title={isIneligible ? `PTU is not available for ${deployment.model}. Provisioned Throughput Units are only supported for select Azure OpenAI chat and reasoning models.` : undefined}
                                  >
                                    <input
                                      type="radio"
                                      name="deployment"
                                      checked={deploymentName === deployment.name}
                                      disabled={isIneligible}
                                      onChange={() => setDeploymentName(deployment.name)}
                                    />
                                    <span className="deployment-text">
                                      <span className="deployment-title">{formatDeploymentTitle(deployment)}</span>
                                      <span className="deployment-meta deployment-labels">
                                        <span className="deployment-chip">SKU: {meta.sku}</span>
                                        <span className="deployment-chip">Capacity: {meta.capacity}</span>
                                        {isIneligible
                                          ? <span className="eligibility-chip ineligible">PTU Not Available</span>
                                          : isAlreadyPtu
                                            ? <span className="eligibility-chip already-ptu">Already on PTU</span>
                                            : <span className="eligibility-chip eligible">PTU Eligible</span>
                                        }
                                      </span>
                                      {isAlreadyPtu && !isIneligible && (
                                        <span className="ptu-validate-hint">Analyze to validate sizing</span>
                                      )}
                                    </span>
                                  </label>
                                  {isIneligible && (
                                    <button
                                      type="button"
                                      className="why-toggle"
                                      aria-expanded={isWhyExpanded}
                                      onClick={(e) => { e.preventDefault(); setExpandedWhyDeployment(isWhyExpanded ? null : deployment.name) }}
                                    >
                                      {isWhyExpanded ? 'Hide details' : 'Why?'}
                                    </button>
                                  )}
                                  {isIneligible && isWhyExpanded && (
                                    <div className="why-panel" role="note">
                                      <p>{deployment.ineligibility_reason || 'This model does not support Provisioned Throughput Units. PTU is available for select Azure OpenAI chat and reasoning models.'}</p>
                                      <p className="why-panel-eligible">PTU-eligible models: GPT-4o, GPT-4.1, GPT-5, o1, o3-mini, o4-mini (and their variants).</p>
                                      <a className="why-panel-link" href="https://learn.microsoft.com/azure/ai-services/openai/concepts/provisioned-throughput" target="_blank" rel="noopener noreferrer">Learn more</a>
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    ) : (
                      /* ── Consolidation picker (grouped checkboxes) ── */
                      <div className="consolidation-picker">
                        <p className="consolidation-picker-hint">Select 2 or more deployments of the same model to consolidate. Deployments are grouped by model — you can only select within one group.</p>
                        {!selectedAccount && (
                          <FormStateMessage
                            title="Select an account"
                            detail="Choose an Azure OpenAI account to load deployments."
                          />
                        )}
                        {selectedAccount && deployments.length === 0 && (
                          <FormStateMessage
                            title="No deployments found"
                            detail="Create a deployment in this account, then rerun analysis."
                          />
                        )}
                        {Object.entries(deploymentGroups).map(([groupKey, groupDeployments]) => {
                          const [model, skuType] = groupKey.split('::')
                          const isSingletonGroup = groupDeployments.length < 2
                          const isActiveGroup = selectedModelGroup === groupKey
                          const isOtherGroupActive = selectedModelGroup != null && selectedModelGroup !== groupKey
                          const groupAllIneligible = groupDeployments.every((d) => !d.ptu_eligible)
                          return (
                            <div key={groupKey} className={`consolidation-group${isActiveGroup ? ' is-active-group' : ''}${isSingletonGroup ? ' is-singleton' : ''}${isOtherGroupActive ? ' is-dimmed' : ''}${groupAllIneligible ? ' is-all-ineligible' : ''}`}>
                              <div className="consolidation-group-header" title="PTU capacity is model-specific — only same-model, same-SKU deployments can share a PTU allocation.">
                                <span className="consolidation-group-label">{model} · {skuType || 'Standard'}</span>
                                <span className="consolidation-group-count">
                                  {groupDeployments.length} deployment{groupDeployments.length !== 1 ? 's' : ''}
                                  {groupAllIneligible && <span className="eligibility-chip ineligible" style={{ marginLeft: 6 }}>PTU Not Available</span>}
                                </span>
                              </div>
                              {groupDeployments.map((deployment) => {
                                const meta = getDeploymentMetaParts(deployment)
                                const isChecked = selectedDeployments.includes(deployment.name)
                                const isIneligible = !deployment.ptu_eligible
                                const isDisabled = isIneligible || isSingletonGroup || (isOtherGroupActive && !isChecked)
                                return (
                                  <label
                                    key={deployment.name}
                                    className={`checkbox-option deployment-option ${isChecked ? 'is-selected' : ''}${isDisabled ? ' is-disabled' : ''}${isIneligible ? ' is-ineligible' : ''}`}
                                    title={isIneligible ? `PTU is not available for ${deployment.model}. Provisioned Throughput Units are only supported for select Azure OpenAI chat and reasoning models.` : isSingletonGroup ? 'Only 1 deployment — nothing to consolidate' : undefined}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      disabled={isDisabled}
                                      onChange={() => toggleConsolidationDeployment(deployment.name, groupKey)}
                                    />
                                    <span className="deployment-text">
                                      <span className="deployment-title">{formatDeploymentTitle(deployment)}</span>
                                      <span className="deployment-meta deployment-labels">
                                        <span className="deployment-chip">SKU: {meta.sku}</span>
                                        <span className="deployment-chip">Capacity: {meta.capacity}</span>
                                        {isIneligible
                                          ? <span className="eligibility-chip ineligible">PTU Not Available</span>
                                          : <span className="eligibility-chip eligible">PTU Eligible</span>
                                        }
                                        {(() => {
                                          // Post-analysis data (from consolidation summary) takes precedence
                                          const depSummary = consolidationSummary?.individual_deployments.find((d) => d.name === deployment.name)
                                          if (depSummary) return (
                                            <>
                                              <span className="deployment-chip deployment-chip-metric">{formatNumber(depSummary.avg_tpm)} TPM avg</span>
                                              <span className="deployment-chip deployment-chip-metric">{depSummary.throttling_rate_pct.toFixed(1)}% 429</span>
                                            </>
                                          )
                                          // Pre-analysis preview data (from lightweight endpoint)
                                          const preview = deploymentPreviews.find((p) => p.name === deployment.name)
                                          if (preview) return (
                                            <>
                                              <span className="deployment-chip deployment-chip-preview" title="Estimated from preview — run analysis for precise values">{formatNumber(preview.avg_tpm)} TPM avg</span>
                                              <span className="deployment-chip deployment-chip-preview" title="Estimated from preview — run analysis for precise values">{preview.throttling_rate_pct.toFixed(1)}% 429</span>
                                            </>
                                          )
                                          return null
                                        })()}
                                      </span>
                                    </span>
                                  </label>
                                )
                              })}
                              {isSingletonGroup && (
                                <span className="consolidation-singleton-note">Only 1 deployment — nothing to consolidate</span>
                              )}
                            </div>
                          )
                        })}
                        {selectedDeployments.length > 0 && selectedModelGroup && (
                          <div className="consolidation-selection-summary">
                            Selected: {selectedDeployments.length} of {deploymentGroups[selectedModelGroup]?.length ?? 0} deployments
                            {consolidationSummary && (
                              <span className="consolidation-selection-tpm"> · {formatNumber(consolidationSummary.combined_avg_tpm)} TPM combined avg</span>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </fieldset>
                </>
              )}

              <label className="slider-label">
                Lookback Days: <strong>{lookbackDays}</strong>
                <input
                  type="range"
                  min={1}
                  max={30}
                  value={lookbackDays}
                  onChange={(e) => setLookbackDays(Number(e.target.value))}
                />
              </label>

              <label>
                Graph Granularity
                <select
                  value={granularityMinutes}
                  onChange={(e) => setGranularityMinutes(Number(e.target.value) as 1 | 5 | 15 | 30)}
                  data-testid="granularity-select"
                >
                  <option value={1}>1 minute</option>
                  <option value={5}>5 minutes</option>
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                </select>
              </label>
            </div>

            {error && (
              <div className="error" role="alert" aria-live="assertive">
                <strong className="error-title">Unable to complete setup</strong>
                <p className="error-message">{error}</p>
                <button type="button" className="error-dismiss" onClick={() => setError('')}>
                  Dismiss
                </button>
              </div>
            )}

            <div className="advisor-actions">
              <button className="primary run-btn" onClick={() => runAnalysis()} disabled={loading || (analysisMode === 'consolidation' && mode === 'live' && selectedDeployments.length < 2) || (analysisMode === 'single' && mode === 'live' && !!deploymentName && !deployments.find((d) => d.name === deploymentName)?.ptu_eligible)}>
                {loading ? (
                  <><span className="run-btn-spinner" /> Analyzing...</>
                ) : analysisMode === 'consolidation' ? (
                  <><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="5,3 13,8 5,13" fill="currentColor" stroke="none"/></svg> Analyze Consolidation{mode === 'live' && selectedDeployments.length >= 2 ? ` (${selectedDeployments.length} deployments)` : ''}</>
                ) : (
                  <><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="5,3 13,8 5,13" fill="currentColor" stroke="none"/></svg> Run Analysis</>
                )}
              </button>
            </div>

            {loading && <LoadingSpinner />}
            </div>)}

            {activeView === 'calculator' && (<>
            <div className="panel-header">
              <div className="panel-step-indicator">
                <span className="step-dot step-active" />
                <span className="step-line step-line-done" />
                <span className="step-dot step-active" />
              </div>
              <div>
                <h2>PTU Calculator</h2>
                <p className="caption">Estimate costs from expected usage — no Azure connection needed.</p>
              </div>
            </div>

            <div className="calc-form-grid">
              <label>
                Model
                <select value={calcModel} onChange={e => setCalcModel(e.target.value)}>
                  {CALC_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </label>

              <label>
                Average TPM
                <input type="number" min={0} step={1000} value={calcAvgTpm} onChange={e => setCalcAvgTpm(Number(e.target.value))} placeholder="e.g. 50000" />
                <span className="field-hint">Sustained baseline tokens-per-minute</span>
              </label>

              <label>
                Peak TPM
                <input type="number" min={0} step={1000} value={calcPeakTpm} onChange={e => setCalcPeakTpm(Number(e.target.value))} placeholder="e.g. 120000" />
                <span className="field-hint">P95/P99 burst tokens-per-minute</span>
              </label>

              <label className="slider-label">
                Output Token Share: <strong>{calcOutputPct}%</strong>
                <input type="range" min={5} max={95} value={calcOutputPct} onChange={e => setCalcOutputPct(Number(e.target.value))} />
                <span className="field-hint">Input {100 - calcOutputPct}% / Output {calcOutputPct}%</span>
              </label>

              <label className="slider-label">
                Prompt Cache Match: <strong>{calcCachePct}%</strong>
                <input type="range" min={0} max={100} value={calcCachePct} onChange={e => setCalcCachePct(Number(e.target.value))} />
                <span className="field-hint">Cached prompt tokens reduce modeled utilization; fixed PTU cost changes only when fewer units are selected.</span>
              </label>

              <label className="slider-label">
                Peak Hours per Day: <strong>{calcPeakHours}h</strong>
                <input type="range" min={1} max={24} value={calcPeakHours} onChange={e => setCalcPeakHours(Number(e.target.value))} />
                <span className="field-hint">How many hours per day traffic exceeds average</span>
              </label>

              <label>
                Region
                <select value={calcRegion} onChange={e => setCalcRegion(e.target.value)}>
                  {(pricingRegions.length ? pricingRegions : FALLBACK_PRICING_REGIONS).map(r => (
                    <option key={r.name} value={r.name}>{r.display_name} ({r.multiplier}x)</option>
                  ))}
                </select>
              </label>

              <label>
                Deployment Type
                <select value={calcDeployType} onChange={e => setCalcDeployType(e.target.value as 'global' | 'data_zone' | 'regional')}>
                  {(deploymentTypeOptions.length ? deploymentTypeOptions : FALLBACK_DEPLOYMENT_TYPES).map(d => (
                    <option key={d.name} value={d.name}>{d.label}</option>
                  ))}
                </select>
              </label>
            </div>

            {calcResult && (
              <div className="calc-results">
                <div className={`calc-rec-banner ${calcResult.savings > 0 ? 'calc-rec-saves' : 'calc-rec-payg'}`}>
                  <div className="calc-rec-icon">{calcResult.savings > 0 ? '\u2713' : '\u2192'}</div>
                  <div className="calc-rec-body">
                    <strong>
                      {calcResult.savings > 0
                        ? `${calcResult.cheapest.name} ${calcResult.cheapest.term} recommended`
                        : 'PAYG is optimal at this usage level'}
                    </strong>
                    <span>
                      {calcResult.savings > 0
                        ? `$${calcResult.cheapest.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo — saves $${calcResult.savings.toLocaleString(undefined, { maximumFractionDigits: 0 })} (${calcResult.savingsPct.toFixed(1)}%) vs PAYG`
                        : `$${calcResult.paygMonthly.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo estimated`}
                    </span>
                  </div>
                </div>

                <div className="table-scroll-region" role="region" aria-label="PTU strategy comparison table" tabIndex={0}>
                  <table className="calc-scenario-table" aria-label="PTU strategy comparison">
                    <thead>
                      <tr>
                        <th>Strategy</th>
                        <th>Commitment</th>
                        <th>PTU Units</th>
                        <th>Monthly Cost</th>
                        <th>vs PAYG</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calcResult.scenarios.map((s, i) => {
                        const diff = calcResult.paygMonthly - s.cost
                        const isCheapest = s === calcResult.cheapest
                        return (
                          <tr key={i} className={isCheapest ? 'calc-row-best' : ''}>
                            <td>{s.name}</td>
                            <td>{s.term}</td>
                            <td>{s.ptuUnits || '\u2014'}</td>
                            <td>${s.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                            <td className={diff > 0 ? 'calc-savings' : diff < 0 ? 'calc-more' : ''}>
                              {i === 0 ? '\u2014' : diff > 0 ? `-$${diff.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `+$${Math.abs(diff).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="calc-details-row">
                  <div className="calc-detail-card">
                    <span className="calc-detail-label">Break-Even TPM by Commitment</span>
                    <dl className="calc-break-even-list">
                      {calcResult.breakEvenByTerm.map(({ term, lower, upper }) => (
                        <div className="calc-break-even-row" key={term}>
                          <dt>{term}</dt>
                          <dd>{lower ? `${lower.toLocaleString(undefined, { maximumFractionDigits: 0 })}${upper ? ` - ${upper.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : ''}` : 'N/A'}</dd>
                        </div>
                      ))}
                    </dl>
                    <span className="calc-detail-sub">Sustained TPM where Hybrid PTU equals PAYG cost</span>
                  </div>
                  <div className="calc-detail-card">
                    <span className="calc-detail-label">Full PTU Sizing</span>
                    <span className="calc-detail-value">{calcResult.ptuFull} PTU</span>
                    <span className="calc-detail-sub">Covers peak {calcPeakTpm.toLocaleString()} TPM</span>
                  </div>
                  <div className="calc-detail-card">
                    <span className="calc-detail-label">Hybrid PTU Sizing</span>
                    <span className="calc-detail-value">{calcResult.ptuBase} PTU</span>
                    <span className="calc-detail-sub">Covers avg {calcAvgTpm.toLocaleString()} TPM + PAYG overflow</span>
                  </div>
                  <div className="calc-detail-card">
                    <span className="calc-detail-label">PAYG Blended Rate</span>
                    <span className="calc-detail-value">${calcResult.blendedRate.toFixed(2)}/1M</span>
                    <span className="calc-detail-sub">{100 - calcOutputPct}% input / {calcOutputPct}% output mix</span>
                  </div>
                </div>
              </div>
            )}
            </>)}

          </section>
        )}

        <footer className="app-footer">
          <span>PTU Advisor</span>
          <span className="footer-sep">{"\u00B7"}</span>
          <span>Azure OpenAI Capacity Planning</span>
        </footer>

        {analysis && (
          <section ref={resultsRef} className="results results-v2" style={{ position: 'relative' }} aria-label="Analysis results" tabIndex={-1}>
            {loading && <ThinkingOverlay />}
            <div className={`result-banner ${recommendationClass}`}>
              <div className="result-banner-top">
                <RecBadge recommendation={analysis.recommendation} />
                {mode === 'demo' && (
                  <span className="demo-provenance" title="Results use generated sample telemetry, not production Azure data.">
                    Synthetic demo data
                  </span>
                )}
                <p className="confidence">Confidence score: {(analysis.confidence * 100).toFixed(1)}%</p>
                {!hasInsufficientCostData && <DeferredResult label="Preparing export…" inline><ExportReport
                  analysis={analysis}
                  baseAnalysis={baseAnalysis}
                  isZoomed={zoomState.isDirty}
                  consolidationSummary={consolidationSummary}
                  tokenSnapshotContext={
                    mode === 'demo'
                      ? { mode: 'demo', focusTopic, days: lookbackDays, interval: 'PT1M', cache_mode: cacheMode, cache_match_rate_override_pct: cacheMatchRateOverride }
                      : (subscriptionId && selectedAccount && analysis.metrics.deployment_name)
                        ? {
                            mode: 'live',
                            days: lookbackDays,
                            interval: 'PT1M',
                            subscription_id: subscriptionId,
                            resource_group: selectedAccount.resource_group,
                            workspace: selectedAccount.name,
                            deployment: analysis.metrics.deployment_name,
                            cache_mode: cacheMode,
                            cache_match_rate_override_pct: cacheMatchRateOverride,
                          }
                        : undefined
                  }
                /></DeferredResult>}
              </div>
              <h2 className="result-banner-title">{recommendationTitle}</h2>
              <p className="result-banner-summary">{recommendationSummary}</p>
            </div>

            <nav className="analysis-section-nav" aria-label="Analysis sections">
              <a href="#overview">Overview</a>
              <a href="#evidence">Evidence</a>
              <a href="#economics">Economics</a>
              <a href="#rationale">Rationale</a>
            </nav>

            <section className="decision-snapshot" aria-label="Decision snapshot">
              <div className="decision-snapshot-item">
                <span>PAYG monthly</span>
                <strong>{hasInsufficientCostData ? 'Not available' : formatCurrency(analysis.cost_analysis.payg.payg_total)}</strong>
              </div>
              <div className="decision-snapshot-item">
                <span>PTU + spillover</span>
                <strong>{hasInsufficientCostData ? 'Not available' : formatCurrency(analysis.cost_analysis.hybrid.hybrid_total)}</strong>
              </div>
              <div className="decision-snapshot-item">
                <span>Monthly difference</span>
                <strong>{hasInsufficientCostData ? 'Not available' : differenceSummary}</strong>
              </div>
              <div className="decision-snapshot-item">
                <span>Commitment safety</span>
                <strong>
                  {analysis.cost_analysis.commitment_safety
                    ? VERDICT_LABELS[analysis.cost_analysis.commitment_safety.safety_verdict] ?? toTitleCaseLabel(analysis.cost_analysis.commitment_safety.safety_verdict)
                    : 'Not available'}
                </strong>
              </div>
            </section>

            {/* ── Consolidation Summary Card ── */}
            {consolidationSummary && (
              <article className="consolidation-summary-card">
                <div className="consolidation-summary-header">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="1" width="6" height="6" rx="1.5"/><rect x="11" y="1" width="6" height="6" rx="1.5"/><rect x="6" y="11" width="6" height="6" rx="1.5"/><path d="M4 7v2.5a1.5 1.5 0 001.5 1.5h2M14 7v2.5a1.5 1.5 0 01-1.5 1.5h-2"/></svg>
                  <span>Consolidation Analysis — {consolidationSummary.deployment_count} {consolidationSummary.model_name} deployments</span>
                </div>

                <div className="consolidation-deployments-grid">
                  {consolidationSummary.individual_deployments.map((dep) => (
                    <div key={dep.name} className="consolidation-dep-card">
                      <strong className="consolidation-dep-name">{dep.name}</strong>
                      <div className="consolidation-dep-stats">
                        <span>Avg TPM: {formatNumber(dep.avg_tpm)}</span>
                        <span>Peak TPM: {formatNumber(dep.peak_tpm)}</span>
                        <span>Throttling: {dep.throttling_rate_pct.toFixed(1)}%</span>
                        <span>Requests: {formatNumber(dep.total_requests)}</span>
                        <span>PAYG: {formatCurrency(dep.payg_monthly_cost)}/mo</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="consolidation-combined-stats">
                  <span>Combined: Avg TPM {formatNumber(consolidationSummary.combined_avg_tpm)}</span>
                  <span className="consolidation-stat-sep">{"\u00B7"}</span>
                  <span>Peak TPM {formatNumber(consolidationSummary.combined_peak_tpm)}</span>
                  <span className="consolidation-stat-sep">{"\u00B7"}</span>
                  <span>Throttling {consolidationSummary.combined_throttling_rate_pct.toFixed(1)}%</span>
                </div>

                {/* ── Consolidation Warnings ── */}
                {consolidationSummary.warnings.length > 0 && (
                  <div className="consolidation-warnings" data-testid="consolidation-warnings">
                    {consolidationSummary.warnings.map((w, i) => (
                      <div key={i} className="consolidation-warning-item">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#d4a017" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1.5L1.5 13h13L8 1.5z"/><path d="M8 6v3"/><circle cx="8" cy="11" r="0.5" fill="#d4a017" stroke="none"/></svg>
                        <span>{w}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className={`consolidation-verdict ${consolidationSummary.savings > 0 ? 'consolidation-verdict-positive' : 'consolidation-verdict-negative'}`}>
                  {consolidationSummary.all_on_ptu ? (
                    <p>All selected deployments already use PTU. {consolidationSummary.savings > 0 ? (
                      <>Consolidating onto a single PTU allocation saves an estimated <strong>{formatCurrency(consolidationSummary.savings)}/month ({consolidationSummary.savings_pct.toFixed(1)}%)</strong> vs the current combined PTU spend.</>
                    ) : (
                      <>The current separate PTU allocations are already cost-effective. Consolidation would cost <strong>{formatCurrency(Math.abs(consolidationSummary.savings))}/month</strong> more.</>
                    )}</p>
                  ) : consolidationSummary.savings > 0 ? (
                    <p>Consolidating these deployments onto a single PTU saves an estimated <strong>{formatCurrency(consolidationSummary.savings)}/month ({consolidationSummary.savings_pct.toFixed(1)}%)</strong> vs running each on PAYG.</p>
                  ) : (
                    <p>Consolidation does not save money here. Individual PAYG is more cost-effective by <strong>{formatCurrency(Math.abs(consolidationSummary.savings))}/month</strong>.</p>
                  )}
                </div>

                <div className="consolidation-cost-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Individual PAYG</th>
                        <th>Consolidated PTU + Spillover</th>
                        <th>Savings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {consolidationSummary.individual_deployments.map((dep) => (
                        <tr key={dep.name} className="consolidation-cost-row-deployment">
                          <td className="consolidation-cost-indent">{dep.name}</td>
                          <td>{formatCurrency(dep.payg_monthly_cost)}</td>
                          <td className="consolidation-cost-na">—</td>
                          <td className="consolidation-cost-na">—</td>
                        </tr>
                      ))}
                      <tr className="consolidation-cost-row-total">
                        <td><strong>Monthly Cost</strong></td>
                        <td><strong>{formatCurrency(consolidationSummary.individual_payg_total)}</strong></td>
                        <td><strong>{formatCurrency(consolidationSummary.consolidated_hybrid_cost)}</strong></td>
                        <td className={consolidationSummary.savings > 0 ? 'consolidation-savings-positive' : 'consolidation-savings-negative'}>
                          <strong>{consolidationSummary.savings > 0 ? '-' : '+'}{formatCurrency(Math.abs(consolidationSummary.savings))} ({Math.abs(consolidationSummary.savings_pct).toFixed(1)}%)</strong>
                        </td>
                      </tr>
                      <tr>
                        <td>Annual Savings</td>
                        <td colSpan={2} className="consolidation-cost-na">—</td>
                        <td className={consolidationSummary.savings > 0 ? 'consolidation-savings-positive' : 'consolidation-savings-negative'}>
                          {consolidationSummary.savings > 0 ? '-' : '+'}{formatCurrency(Math.abs(consolidationSummary.savings * 12))}/yr
                        </td>
                      </tr>
                      {analysis.cost_analysis.commitment_safety && (
                        <tr>
                          <td>Spillover Traffic</td>
                          <td className="consolidation-cost-na">N/A</td>
                          <td>{analysis.cost_analysis.commitment_safety.spillover_pct.toFixed(1)}%</td>
                          <td className="consolidation-cost-na">—</td>
                        </tr>
                      )}
                      {analysis.cost_analysis.comparison.break_even_tpm && (
                        <tr>
                          <td>Break-Even TPM</td>
                          <td colSpan={3}>{formatNumber(analysis.cost_analysis.comparison.break_even_tpm)}{analysis.cost_analysis.comparison.upper_break_even_tpm ? ` - ${formatNumber(analysis.cost_analysis.comparison.upper_break_even_tpm)}` : ''} TPM</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </article>
            )}

            <h3 className="section-title section-title-with-icon stagger-1" id="overview"><span className="stagger-1">At a Glance</span></h3>
            <div className="glance-grid stagger-2">
              <article className="glance-card glance-card-scope" aria-label="Deployment scope">
                <span className="glance-label">Scope <InfoTip text="Deployment analyzed in this run." /></span>
                <span className="glance-value glance-value-text">{analysis.metrics.deployment_name}</span>
                <span className="glance-sub">{analysis.metrics.model_name}</span>
              </article>
              <article className="glance-card">
                <span className="glance-label">Typical Throughput <InfoTip text="Average tokens-per-minute across the selected lookback period." /></span>
                <span className="glance-value">{formatNumber(analysis.metrics.avg_tpm)}</span>
                <span className="glance-sub">tokens / min avg</span>
              </article>
              <article className="glance-card">
                <span className="glance-label">Busy-Hour Throughput <InfoTip text="95th percentile throughput used for capacity pressure and PTU sizing guidance." /></span>
                <span className="glance-value">{formatNumber(analysis.metrics.peak_tpm)}</span>
                <span className="glance-sub">P95 tokens / min</span>
              </article>
              <article className="glance-card">
                <span className="glance-label">Total Tokens <InfoTip text="Total tokens processed (prompt + completion) within the selected timeframe." /></span>
                <span className="glance-value">{formatNumber(analysis.metrics.total_tokens)}</span>
                <span className="glance-sub">{analysis.metrics.total_tokens_millions.toFixed(1)}M tokens</span>
              </article>
              <article className="glance-card">
                <span className="glance-label">Daily Avg Tokens <InfoTip text="Average tokens processed per day over the lookback period." /></span>
                <span className="glance-value">{formatNumber(analysis.metrics.total_tokens / analysis.metrics.lookback_days)}</span>
                <span className="glance-sub">tokens / day</span>
              </article>
              <article className={`glance-card${analysis.metrics.throttling_rate_pct > 5 ? ' glance-alert' : ''}`}>
                <span className="glance-label">Rate-Limit Events <InfoTip text="Percent of requests receiving HTTP 429 rate-limit responses." /></span>
                <span className="glance-value">{analysis.metrics.throttling_rate_pct.toFixed(2)}%</span>
                <span className="glance-sub">HTTP 429 rate</span>
              </article>
              {analysis.metrics.cache_match_rate?.available && (
                <article className="glance-card">
                  <span className="glance-label">Prompt Cache Hit Rate <InfoTip text="Average percentage of input tokens served from the prompt cache. Provisioned deployments deduct cached prompt tokens from utilization; Standard deployments use the resolved cached-input rate. Fixed PTU cost changes only when fewer PTUs are selected." /></span>
                  <span className="glance-value">{analysis.metrics.cache_match_rate.avg_pct.toFixed(1)}%</span>
                  <span className="glance-sub">avg context-token cache match</span>
                </article>
              )}
            </div>

            <h3 className="section-title section-title-with-icon stagger-3" id="evidence"><span className="stagger-3">Evidence</span></h3>
            {zoomState.isDirty && (
              <div className="zoom-indicator stagger-3">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="4.5"/><path d="M13 13l-3.5-3.5"/><path d="M6 4v4M4 6h4"/></svg>
                <span>Zoomed to custom window{zoomState.windowStart && zoomState.windowEnd ? `: ${smartDateFmt(zoomState.windowStart)} — ${smartDateFmt(zoomState.windowEnd)}` : ''}</span>
                <button className="zoom-reset-btn" onClick={resetZoom}>Reset Zoom</button>
                {loading && <span className="zoom-reanalyze-status">Updating…</span>}
              </div>
            )}
            {!zoomState.isDirty && (
              <p className="zoom-hint stagger-3">Use the slider below each chart or scroll-wheel to zoom in</p>
            )}
            <div className="chart-grid chart-grid-v2 stagger-4">
              <AnalyticalWidget
                title="Token Volume Over Time"
                headline={formatNumber(analysis.metrics.total_tokens)}
                metricLabel="total tokens"
                context={`${formatNumber(analysis.metrics.total_tokens / Math.max(analysis.metrics.lookback_days, 1))} avg / day`}
                summary={`${analysis.metrics.total_tokens.toLocaleString()} total tokens across ${analysis.metrics.lookback_days} days; ${Math.round(analysis.metrics.total_tokens / Math.max(analysis.metrics.lookback_days, 1)).toLocaleString()} average tokens per day.`}
                tooltip={<InfoTip text="Shows prompt tokens (input) and completion tokens (output) consumed per interval. Spikes indicate bursts of usage. A flat, high line suggests steady workload — a good PTU candidate." />}
                onExpand={() => setExpandedChart(expandedChart === 'tokens' ? null : 'tokens')}
                expanded={expandedChart === 'tokens'}
                className={expandedChart === 'tokens' ? 'is-chart-expanded' : ''}
              >
                {tokenChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <DeferredResult><TokenVolumeChart
                  timestamps={analysis!.charts.tokens.timestamps}
                  prompt={analysis!.charts.tokens.prompt}
                  completion={analysis!.charts.tokens.completion}
                  total={analysis!.charts.tokens.total}
                  height={getChartHeight('tokens', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                  groupId="time-sync"
                  perDeployment={perDepCharts?.tokens.per_deployment}
                /></DeferredResult>
                )}
              </AnalyticalWidget>

              <AnalyticalWidget
                title="Request Outcomes"
                headline={formatNumber(analysis.metrics.total_requests)}
                metricLabel="total requests"
                context={`${analysis.metrics.throttling_rate_pct.toFixed(2)}% HTTP 429`}
                status={analysis.metrics.throttled_requests > 0 ? { label: 'Rate limits observed', tone: 'warning' } : { label: 'No rate limits', tone: 'positive' }}
                summary={`${analysis.metrics.total_requests.toLocaleString()} total requests; ${analysis.metrics.throttled_requests.toLocaleString()} rate-limited responses; ${analysis.metrics.throttling_rate_pct.toFixed(2)}% HTTP 429 rate.`}
                tooltip={<InfoTip text="Displays successful API calls vs HTTP 429 (rate-limited) responses per interval. High 429 counts signal capacity pressure — PTU eliminates these by reserving dedicated throughput." />}
                onExpand={() => setExpandedChart(expandedChart === 'requests' ? null : 'requests')}
                expanded={expandedChart === 'requests'}
                className={expandedChart === 'requests' ? 'is-chart-expanded' : ''}
              >
                {requestsChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <DeferredResult><RequestOutcomesChart
                  timestamps={analysis!.charts.requests.timestamps}
                  successful={analysis!.charts.requests.successful}
                  throttled={analysis!.charts.requests.throttled}
                  height={getChartHeight('requests', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                  perDeployment={perDepCharts?.requests.per_deployment}
                /></DeferredResult>
                )}
              </AnalyticalWidget>

              <AnalyticalWidget
                title="Daily Deployment Cost"
                headline={formatCurrency(analysis.charts.daily_cost.total_cost.reduce((total, value) => total + value, 0))}
                metricLabel="period cost"
                context={`${formatCurrency(analysis.charts.daily_cost.avg_daily_cost)} avg / day`}
                summary={`${formatCurrencyPrecise(analysis.charts.daily_cost.total_cost.reduce((total, value) => total + value, 0))} period cost; ${formatCurrencyPrecise(analysis.charts.daily_cost.avg_daily_cost)} average cost per day.`}
                tooltip={<InfoTip text="Stacked bars show daily input and output token costs at PAYG rates. The dashed lines mark average daily spend and what a PTU baseline would cost per day — compare bars to lines to see if PTU saves money." />}
                onExpand={() => setExpandedChart(expandedChart === 'dailyCost' ? null : 'dailyCost')}
                expanded={expandedChart === 'dailyCost'}
                className={expandedChart === 'dailyCost' ? 'is-chart-expanded' : ''}
              >
                {dailyCostChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <DeferredResult><DailyCostChart
                  timestamps={analysis!.charts.daily_cost.dates}
                  inputCost={analysis!.charts.daily_cost.input_cost}
                  outputCost={analysis!.charts.daily_cost.output_cost}
                  avgDailyCost={analysis!.charts.daily_cost.avg_daily_cost}
                  ptuDailyCost={analysis!.charts.daily_cost.ptu_daily_cost}
                  height={getChartHeight('dailyCost', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                /></DeferredResult>
                )}
              </AnalyticalWidget>

              <AnalyticalWidget
                title="Rate-Limit Events (429)"
                headline={formatNumber(analysis.metrics.throttled_requests)}
                metricLabel="throttled requests"
                context={`${analysis.metrics.throttling_rate_pct.toFixed(2)}% of requests`}
                status={analysis.metrics.throttled_requests > 0 ? { label: 'Capacity pressure', tone: 'warning' } : { label: 'No events', tone: 'positive' }}
                summary={`${analysis.metrics.throttled_requests.toLocaleString()} throttled requests; ${analysis.metrics.throttling_rate_pct.toFixed(2)}% of all requests received HTTP 429 responses.`}
                tooltip={<InfoTip text="Shows the count of HTTP 429 rate-limit responses per interval. Frequent spikes mean your traffic regularly exceeds PAYG quota, causing retries and latency. PTU provisioning removes this bottleneck." />}
                onExpand={() => setExpandedChart(expandedChart === 'throttle' ? null : 'throttle')}
                expanded={expandedChart === 'throttle'}
                className={expandedChart === 'throttle' ? 'is-chart-expanded' : ''}
              >
                {throttleChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <DeferredResult><ThrottleChart
                  timestamps={analysis!.charts.throttling.timestamps}
                  throttled={analysis!.charts.throttling.values}
                  height={getChartHeight('throttle', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                  perDeployment={perDepCharts?.throttling.per_deployment}
                /></DeferredResult>
                )}
              </AnalyticalWidget>

              <div className="prompt-cache-composition" role="group" aria-label="Prompt cache evidence">
                <AnalyticalWidget
                  title="Prompt Cache Volume"
                  headline={formatNumber(promptCacheTotals.cached)}
                  metricLabel="cached prompt tokens"
                  context={`${promptCacheTotals.cachedSharePct.toFixed(1)}% of ${formatNumber(promptCacheTotals.total)} total`}
                  summary={`${Math.round(promptCacheTotals.cached).toLocaleString()} cached prompt tokens and ${Math.round(promptCacheTotals.active).toLocaleString()} active prompt tokens across the selected period; cached tokens are ${promptCacheTotals.cachedSharePct.toFixed(1)}% of ${Math.round(promptCacheTotals.total).toLocaleString()} total prompt tokens.`}
                  tooltip={<InfoTip text="Shows active and cached prompt tokens on one shared token scale. Stacked volume preserves the total prompt workload while separating tokens served from cache." />}
                  onExpand={() => setExpandedChart(expandedChart === 'promptCacheVolume' ? null : 'promptCacheVolume')}
                  expanded={expandedChart === 'promptCacheVolume'}
                  className={expandedChart === 'promptCacheVolume' ? 'is-chart-expanded' : ''}
                >
                  {!analysis.charts.prompt_cache?.timestamps.length || (analysis.charts.prompt_cache.cached_prompt_tokens.length === 0 && analysis.charts.prompt_cache.active_prompt_tokens.length === 0) ? <ChartEmpty height={260} /> : (
                    <DeferredResult><PromptCacheVolumeChart
                      timestamps={analysis.charts.prompt_cache.timestamps}
                      cachedPromptTokens={analysis.charts.prompt_cache.cached_prompt_tokens}
                      activePromptTokens={analysis.charts.prompt_cache.active_prompt_tokens}
                      height={getChartHeight('promptCacheVolume', 260)}
                      zoomState={zoomState}
                      onDataZoom={onDataZoom}
                      selectedTimestamp={selectedTimestamp}
                    /></DeferredResult>
                  )}
                </AnalyticalWidget>

                <AnalyticalWidget
                  title="Cache Efficiency"
                  headline={analysis.metrics.cache_match_rate?.available ? `${analysis.metrics.cache_match_rate.avg_pct.toFixed(1)}%` : 'N/A'}
                  metricLabel="average cache match"
                  context={`${cacheImpactView.coveragePct.toFixed(1)}% telemetry coverage`}
                  status={cacheImpactView.applied ? { label: 'Applied to model', tone: 'positive' } : { label: 'Context only', tone: 'neutral' }}
                  summary={`${analysis.metrics.cache_match_rate?.available ? `${analysis.metrics.cache_match_rate.avg_pct.toFixed(1)}%` : 'Unavailable'} average prompt cache match with ${cacheImpactView.coveragePct.toFixed(1)}% telemetry coverage; ${cacheImpactView.ptuAvoided} PTU avoided after capacity rounding and ${cacheImpactView.normalizedTpmReductionPct.toFixed(1)}% normalized load reduction. Source ${cacheImpactView.source}; quality ${cacheImpactView.quality}; ${cacheImpactView.applied ? 'applied to the model' : 'not applied to the model'}.`}
                  tooltip={<InfoTip text="Shows aggregate and per-deployment cache-match percentages on a fixed 0–100% scale. Coverage and evidence quality determine whether the cache benefit is applied to sizing." />}
                  onExpand={() => setExpandedChart(expandedChart === 'cacheEfficiency' ? null : 'cacheEfficiency')}
                  expanded={expandedChart === 'cacheEfficiency'}
                  className={expandedChart === 'cacheEfficiency' ? 'is-chart-expanded' : ''}
                >
                  <dl className="cache-efficiency-facts" role="list" aria-label="Cache efficiency facts">
                    <div role="listitem"><dt>Coverage</dt><dd>{cacheImpactView.coveragePct.toFixed(1)}%</dd></div>
                    <div role="listitem"><dt>PTU avoided</dt><dd>{cacheImpactView.ptuAvoided} PTU</dd></div>
                    <div role="listitem"><dt>Load reduction</dt><dd>{cacheImpactView.normalizedTpmReductionPct.toFixed(1)}%</dd></div>
                    <div role="listitem"><dt>Source</dt><dd>{toTitleCaseLabel(cacheImpactView.source)}</dd></div>
                    <div role="listitem"><dt>Quality</dt><dd>{toTitleCaseLabel(cacheImpactView.quality)}</dd></div>
                    <div role="listitem"><dt>Model impact</dt><dd>{cacheImpactView.applied ? 'Applied' : 'Context only'}</dd></div>
                  </dl>
                  {!cacheImpactView.available ? (
                    <div className="cache-telemetry-warning" role="alert" aria-label="Cache telemetry warning">
                      <strong>Cache sizing impact unavailable; telemetry is shown as context only and no cache benefit is included in sizing.</strong>
                    </div>
                  ) : (cacheImpactView.source === 'unavailable' || cacheImpactView.source === 'disabled') ? (
                    <div className="cache-telemetry-warning" role="alert" aria-label="Cache telemetry warning">
                      <strong>{cacheImpactView.source === 'disabled' ? 'Cache modeling is disabled; primary estimate assumes no cache benefit.' : 'Cache telemetry unavailable; primary estimate assumes no cache benefit.'}</strong>
                    </div>
                  ) : cacheImpactView.quality === 'limited' && !cacheImpactView.applied ? (
                    <div className="cache-telemetry-warning" role="alert" aria-label="Cache telemetry warning">
                      <strong>Limited cache evidence is contextual only; primary sizing and recommendation assume no cache benefit.</strong>
                    </div>
                  ) : cacheImpactView.quality === 'limited' ? (
                    <div className="cache-telemetry-warning" role="alert" aria-label="Cache telemetry warning">
                      <strong>Limited consolidation evidence is applied conservatively; missing deployment traffic receives zero cache benefit.</strong>
                    </div>
                  ) : null}
                  {!analysis.charts.prompt_cache?.timestamps.length || analysis.charts.prompt_cache.match_rate_pct.every(value => value == null) ? <ChartEmpty height={260} /> : (
                    <DeferredResult><CacheEfficiencyChart
                      timestamps={analysis.charts.prompt_cache.timestamps}
                      matchRatePct={analysis.charts.prompt_cache.match_rate_pct}
                      source={analysis.charts.prompt_cache.source}
                      height={getChartHeight('cacheEfficiency', 260)}
                      zoomState={zoomState}
                      onDataZoom={onDataZoom}
                      selectedTimestamp={selectedTimestamp}
                      perDeployment={perDepCharts?.prompt_cache.per_deployment}
                    /></DeferredResult>
                  )}
                </AnalyticalWidget>
              </div>
            </div>

            <AnalyticalWidget
              title={`Throughput Band (TPM vs Avg/${tpmRefLabel})`}
              headline={formatNumber(analysis.metrics.avg_tpm)}
              metricLabel="average TPM"
              context={`P95 ${formatNumber(analysis.metrics.peak_tpm)} TPM`}
              summary={`${Math.round(analysis.metrics.avg_tpm).toLocaleString()} average tokens per minute; ${Math.round(analysis.metrics.peak_tpm).toLocaleString()} P95 tokens per minute.`}
              tooltip={<InfoTip text={analysis.charts.cost_curves.upper_break_even_tpm ? 'Shows actual TPM against the average and the lower/upper economic break-even range. Traffic inside that range favors PTU; traffic outside favors PAYG.' : `Shows actual tokens-per-minute over time against the average and ${tpmRefLabel} reference.`} />}
              onExpand={() => setExpandedChart(expandedChart === 'tpm' ? null : 'tpm')}
              expanded={expandedChart === 'tpm'}
              className={`wide-card${expandedChart === 'tpm' ? ' is-chart-expanded' : ''}`}
            >
              {tpmChartData.length === 0 ? <ChartEmpty height={280} /> : (
              <DeferredResult><TpmBandChart
                timestamps={analysis!.charts.tpm.timestamps}
                tpm={analysis!.charts.tpm.values}
                avg={analysis!.charts.tpm.avg}
                refLine={analysis!.charts.cost_curves.break_even_tpm ?? analysis!.charts.tpm.p25}
                refLabel={tpmRefLabel}
                upperRefLine={analysis!.charts.cost_curves.upper_break_even_tpm ?? null}
                height={getChartHeight('tpm', 280)}
                zoomState={zoomState}
                onDataZoom={onDataZoom}
                selectedTimestamp={selectedTimestamp}
                perDeployment={perDepCharts?.tpm.per_deployment}
              /></DeferredResult>
              )}
            </AnalyticalWidget>

            {perDepCharts?.latency && (
            <article className="chart-card wide-card">
              <WidgetHeader title="Latency Overlay (P50 / P95)" tip="Shows per-deployment P95 latency as solid lines and combined P50/P95 as dashed white lines. Use this to identify which deployments contribute most to overall latency." />
              <DeferredResult><LatencyOverlayChart
                timestamps={perDepCharts.latency.timestamps}
                combined={perDepCharts.latency.combined}
                perDeployment={perDepCharts.latency.per_deployment}
                height={280}
                zoomState={zoomState}
                onDataZoom={onDataZoom}
                selectedTimestamp={selectedTimestamp}
              /></DeferredResult>
            </article>
            )}

            <h3 className="section-title section-title-with-icon stagger-5"><span className="stagger-5">Traffic Shape Signals</span></h3>
            <div className="metrics-grid">
              <article className="metric-card">
                <h3>Burstiness (P95 / Avg) <InfoTip text="Lower values indicate a steadier workload that is easier to size." /></h3>
                <p>{analysis.metrics.utilization.peak_to_average_ratio.toFixed(2)}x</p>
              </article>
              <article className="metric-card">
                <h3>Sustained Load <InfoTip text="Percent of intervals above 30% of peak load." /></h3>
                <p>{analysis.metrics.utilization.sustained_utilization_rate.toFixed(0)}%</p>
              </article>
              <article className="metric-card">
                <h3>Hours with Material Traffic <InfoTip text="Share of hours with meaningful traffic." /></h3>
                <p>{analysis.metrics.utilization.active_hours_percentage.toFixed(0)}%</p>
              </article>
              <article className="metric-card">
                <h3>Business-Hour Concentration <InfoTip text="Share of traffic concentrated in 9 AM–6 PM." /></h3>
                <p>{analysis.metrics.utilization.business_hours_concentration.toFixed(0)}%</p>
              </article>
            </div>

            <h3 className="section-title section-title-with-icon stagger-6" id="economics"><span className="stagger-6">Financial Decision</span> <PricingSourceBadge source={analysis.cost_analysis.pricing.pricing_source} asOf={analysis.cost_analysis.pricing.pricing_as_of} /></h3>

            {hasInsufficientCostData ? (
              <article className="insufficient-cost-data" role="status">
                <h4>More traffic data required</h4>
                <p>No token usage was observed in the selected window. Cost, savings, commitment safety, and break-even results are withheld until representative traffic is available.</p>
              </article>
            ) : (<>

            {analysis.cost_analysis.pricing.pricing_source === 'fallback' && (
              <div className="pricing-fallback-banner" role="alert">
                <strong>Using default pricing</strong> — live pricing unavailable. Cost figures are based on static fallback rates and may not reflect current Azure pricing.
              </div>
            )}
            {analysis.cost_analysis.pricing.cached_input_pricing_source === 'conservative' && (
              <div className="pricing-fallback-banner" role="alert">
                <strong>Cached-input discount unavailable</strong> — cached prompt tokens are priced at the standard input rate for a conservative estimate.
              </div>
            )}
            {analysis.cost_analysis.pricing.cached_input_pricing_source === 'fallback' && analysis.cost_analysis.pricing.pricing_source !== 'fallback' && (
              <div className="pricing-fallback-banner" role="status">
                <strong>Cached-input rate from verified fallback</strong> — standard and PTU rates are live, while cached-input cost uses the model- and scope-specific fallback meter.
              </div>
            )}
            {analysis.cost_analysis.pricing.ptu_pricing_source === 'fallback' && analysis.cost_analysis.pricing.pricing_source === 'live' && (
              <div className="pricing-fallback-banner" role="status">
                <strong>PTU rate from verified fallback</strong> — token rates, including cached input, are live; the PTU hourly meter was unavailable.
              </div>
            )}
            <article className="chart-card cost-controls-card cost-controls-card-v2">
              <WidgetHeader title="Assumptions" tip="Adjust PTU pricing term and baseline coverage, then recompute costs and recommendation." />
              <div className="cost-controls cost-controls-v2">
                <label>
                  Azure Region
                  <select value={selectedRegion} onChange={(e) => setSelectedRegion(e.target.value)}>
                    {pricingRegions.map((region) => (
                      <option key={region.name} value={region.name}>
                        {region.display_name} ({region.multiplier.toFixed(2)}x)
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Deployment Type
                  <select
                    value={selectedDeploymentType}
                    onChange={(e) => setSelectedDeploymentType(e.target.value as 'global' | 'data_zone' | 'regional')}
                  >
                    {deploymentTypeOptions.map((deploymentType) => (
                      <option key={deploymentType.name} value={deploymentType.name}>
                        {deploymentType.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  PTU Pricing Term
                  <select
                    value={reservationType}
                    onChange={(e) => setReservationType(e.target.value)}
                    aria-describedby={reservationDescriptionId}
                    title={reservationType}
                  >
                    {RESERVATION_OPTIONS.map((term) => (
                      <option key={term} value={term}>
                        {RESERVATION_OPTION_LABELS[term]}
                      </option>
                    ))}
                  </select>
                  <span id={reservationDescriptionId} className="visually-hidden">
                    Selected term: {reservationType}
                  </span>
                </label>

                <label className="slider-label">
                  PTU Baseline Coverage ({analysis.cost_analysis.hybrid.baseline_ptu} PTU)
                  <input
                    type="range"
                    min={analysis.cost_analysis.pricing.ptu_minimum}
                    max={analysis.cost_analysis.hybrid.max_baseline_ptu}
                    step={analysis.cost_analysis.pricing.ptu_increment}
                    value={baselinePtu ?? analysis.cost_analysis.hybrid.default_baseline_ptu}
                    onChange={(e) => setBaselinePtu(Number(e.target.value))}
                  />
                  <span className="slider-range-labels">
                    <span>{analysis.cost_analysis.pricing.ptu_minimum} PTU</span>
                    <span>{analysis.cost_analysis.hybrid.max_baseline_ptu} PTU</span>
                  </span>
                </label>

                <div className="baseline-context">
                  <strong>
                    {analysis.cost_analysis.hybrid.baseline_ptu} PTU → {formatNumber(analysis.cost_analysis.hybrid.baseline_tpm)} TPM capacity
                  </strong>
                  <span>
                    {selectedDeploymentTypeMeta?.label || analysis.cost_analysis.pricing.deployment_type_label} · {selectedRegionMeta?.display_name || analysis.cost_analysis.pricing.region_display_name}
                    {' '}
                    ({(analysis.cost_analysis.pricing.region_multiplier ?? 1).toFixed(2)}x)
                  </span>
                </div>

                {(showHeadroomAction || exploringHeadroom) && (
                  <div className="baseline-helper-row">
                    <span className="baseline-helper-text">
                      {exploringHeadroom
                        ? `Exploring ${currentBaselinePtu} PTU instead of the recommended ${recommendedBaselinePtu} PTU baseline.`
                        : `Explore headroom: up to ${maxViableBaselinePtu} PTU still saves more than 5%.`}
                    </span>
                    <div className="baseline-helper-actions">
                      {showHeadroomAction && currentBaselinePtu !== maxViableBaselinePtu && (
                        <button
                          type="button"
                          className="secondary baseline-helper-button"
                          onClick={() => setBaselinePtu(maxViableBaselinePtu)}
                          disabled={loading}
                        >
                          Explore headroom
                        </button>
                      )}
                      {exploringHeadroom && currentBaselinePtu !== recommendedBaselinePtu && (
                        <button
                          type="button"
                          className="secondary baseline-helper-button"
                          onClick={() => setBaselinePtu(recommendedBaselinePtu)}
                          disabled={loading}
                        >
                          Reset to recommended
                        </button>
                      )}
                    </div>
                  </div>
                )}

                <div className="assumption-status" aria-live="polite">
                  {loading ? 'Updating calculations…' : 'Changes apply automatically after each adjustment'}
                </div>

                <details className="advanced-pricing-section">
                  <summary>Advanced Pricing <InfoTip text="Override the auto-resolved rates to model custom pricing agreements, EAs, or what-if scenarios. Leave blank to use auto-resolved rates." /></summary>
                  <div className="advanced-pricing-grid">
                    <label>
                      PAYG Input Rate ($/1M tokens)
                      <input
                        type="number"
                        min={0}
                        step={0.01}
                        placeholder={analysis.cost_analysis.pricing?.payg_input_rate_per_million?.toFixed(2) ?? '0.00'}
                        value={paygInputOverride ?? ''}
                        onChange={(e) => setPaygInputOverride(e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </label>
                    <label>
                      PAYG Output Rate ($/1M tokens)
                      <input
                        type="number"
                        min={0}
                        step={0.01}
                        placeholder={analysis.cost_analysis.pricing?.payg_output_rate_per_million?.toFixed(2) ?? '0.00'}
                        value={paygOutputOverride ?? ''}
                        onChange={(e) => setPaygOutputOverride(e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </label>
                    <label>
                      PTU Hourly Rate ($/PTU/hr)
                      <input
                        type="number"
                        min={0}
                        step={0.01}
                        placeholder={analysis.cost_analysis.pricing?.ptu_hourly_rate?.toFixed(2) ?? '0.00'}
                        value={ptuHourlyOverride ?? ''}
                        onChange={(e) => setPtuHourlyOverride(e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </label>
                    <label>
                      Cache calculation mode
                      <select
                        aria-label="Cache calculation mode"
                        value={cacheMode}
                        onChange={(e) => {
                          const value = e.target.value as 'auto' | 'disabled' | 'override'
                          setCacheMode(value)
                          if (value !== 'override') setCacheMatchRateOverride(null)
                        }}
                      >
                        <option value="auto">Auto - use observed telemetry</option>
                        <option value="disabled">No cache benefit</option>
                        <option value="override">Manual override</option>
                      </select>
                    </label>
                    {cacheMode === 'override' && (
                      <label>
                        Assumed cache match rate (%)
                        <input
                          aria-label="Assumed cache match rate"
                          type="number"
                          min={0}
                          max={100}
                          step={0.1}
                          value={cacheMatchRateOverride ?? ''}
                          onChange={(e) => setCacheMatchRateOverride(e.target.value === '' ? null : Number(e.target.value))}
                        />
                      </label>
                    )}
                    <label>
                      Cached Input Rate ($/1M tokens)
                      <input
                        type="number"
                        min={0}
                        step={0.01}
                        placeholder={analysis.cost_analysis.pricing.payg_cached_input_rate_per_million?.toFixed(2) ?? '0.00'}
                        value={cachedInputRateOverride ?? ''}
                        onChange={(e) => setCachedInputRateOverride(e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </label>
                    {(paygInputOverride != null || paygOutputOverride != null || ptuHourlyOverride != null || cachedInputRateOverride != null || cacheMode !== 'auto') && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => { setPaygInputOverride(null); setPaygOutputOverride(null); setPtuHourlyOverride(null); setCachedInputRateOverride(null); setCacheMode('auto'); setCacheMatchRateOverride(null) }}
                      >
                        Reset to auto-resolved rates
                      </button>
                    )}
                  </div>
                </details>
              </div>
            </article>

            <details
              className="calculation-details"
              onToggle={(event) => setCalculationDetailsOpen(event.currentTarget.open)}
            >
              <summary className="calculation-details-summary">
                <span className="calculation-details-summary-icon">
                  <RecommendationIcon kind="info" className="calculation-details-icon" />
                </span>
                <span className="calculation-details-summary-copy">
                  <strong className="section-title calc-section-title" role="heading" aria-level={3}>Calculation Details</strong>
                  <span className="calculation-details-summary-description">Actual rates, token volumes, and step-by-step cost math</span>
                </span>
                <span className="calculation-details-affordance">{calculationDetailsOpen ? 'Collapse' : 'Expand'}</span>
              </summary>
              <label className="throttle-toggle">
                <input type="checkbox" checked={includeThrottle} onChange={(e) => setIncludeThrottle(e.target.checked)} />
                <span>Include throttle impact in PAYG cost</span>
                <InfoTip text="When enabled, PAYG cost includes estimated retry overhead from throttled requests (429s). This models the hidden cost of retries and queuing under capacity pressure." />
              </label>
              <div className="formula-grid calc-emphasis">
                <article className="chart-card">
                  <WidgetHeader title="PAYG Math" tip="Line-by-line PAYG monthly cost derivation from average throughput." />
                  <FormulaBlock text={analysis.cost_analysis.formula_blocks.payg} />
                </article>
                <article className="chart-card">
                  <WidgetHeader title="PTU + Spillover Math" tip="Line-by-line hybrid cost derivation from baseline PTU plus overflow tokens." />
                  <FormulaBlock text={analysis.cost_analysis.formula_blocks.hybrid} />
                </article>
              </div>
            </details>

            <AnalyticalWidget
              title={`Cost Explorer — Does my traffic justify ${analysis.charts.cost_curves.selected_ptu} PTU?`}
              ariaLabel="Cost Explorer analytical widget"
              headline={`${analysis.charts.cost_curves.selected_ptu} PTU`}
              metricLabel="selected baseline"
              context={RESERVATION_OPTION_LABELS[reservationType as keyof typeof RESERVATION_OPTION_LABELS] ?? reservationType}
              status={analysis.cost_analysis.commitment_safety
                ? {
                    label: VERDICT_LABELS[analysis.cost_analysis.commitment_safety.safety_verdict] ?? analysis.cost_analysis.commitment_safety.safety_verdict,
                    tone: analysis.cost_analysis.commitment_safety.safety_verdict === 'safe' ? 'positive' : analysis.cost_analysis.commitment_safety.safety_verdict === 'not_justified' ? 'negative' : 'warning',
                  }
                : undefined}
              summary={`${analysis.charts.cost_curves.selected_ptu} PTU baseline under ${reservationType}. PAYG is ${formatCurrency(analysis.cost_analysis.payg.payg_total)} monthly and PTU plus spillover is ${formatCurrency(analysis.cost_analysis.hybrid.hybrid_total)} monthly.`}
              tooltip={<InfoTip text="X-axis shows sustained traffic (TPM). PAYG includes observed cached-input pricing. PTU + Spillover stays flat within PTU capacity, then conservatively prices spillover as uncached because a separate target may have different cache locality. The green line can therefore rise slightly faster and create an upper break-even." />}
              onExpand={() => setExpandedChart(expandedChart === 'cost' ? null : 'cost')}
              expanded={expandedChart === 'cost'}
              className={`wide-card cost-explorer-widget${expandedChart === 'cost' ? ' is-chart-expanded' : ''}`}
              helpContent={`The hybrid PTU + Spillover model commits a fixed number of Provisioned Throughput Units (PTU) to cover your baseline traffic at a predictable monthly cost. When traffic stays within PTU capacity, the cost is flat regardless of how much of that capacity you use. When traffic spikes above PTU capacity, the excess tokens automatically spill over to standard pay-as-you-go (PAYG) pricing. ${analysis.charts.cost_curves.upper_break_even_tpm ? 'PTU is cheaper only between the lower and upper break-even boundaries; above the upper boundary, uncached spillover makes PAYG cheaper again.' : 'The break-even point is where the fixed PTU commitment starts saving money compared to running everything on PAYG.'} The final recommendation is based on the full monthly workload shape, realized hybrid cost, and commitment-safety metrics, not solely on the average.`}
            >
              <div className="cost-comparison-strip" role="list" aria-label="Cost Explorer economics summary">
                <div className={`cost-comparison-fact${analysis.cost_analysis.payg.payg_total <= analysis.cost_analysis.hybrid.hybrid_total ? ' is-winner' : ''}`} role="listitem">
                  <span>PAYG monthly</span>
                  <strong>{formatCurrency(analysis.cost_analysis.payg.payg_total)}</strong>
                </div>
                <div className={`cost-comparison-fact${analysis.cost_analysis.hybrid.hybrid_total <= analysis.cost_analysis.payg.payg_total ? ' is-winner' : ''}`} role="listitem">
                  <span>PTU + spillover monthly</span>
                  <strong>{formatCurrency(analysis.cost_analysis.hybrid.hybrid_total)}</strong>
                </div>
                <div className="cost-comparison-fact" role="listitem">
                  <span>Monthly difference</span>
                  <strong>
                    {analysis.cost_analysis.comparison.savings > 0
                      ? `${formatCurrency(analysis.cost_analysis.comparison.savings)} saved`
                      : analysis.cost_analysis.comparison.savings < 0
                        ? `${formatCurrency(Math.abs(analysis.cost_analysis.comparison.savings))} more`
                        : 'Cost neutral'}
                  </strong>
                </div>
                <div className="cost-comparison-fact" role="listitem">
                  <span>Break-even range</span>
                  <strong>
                    {analysis.cost_analysis.comparison.break_even_tpm
                      ? `${Math.round(analysis.cost_analysis.comparison.break_even_tpm).toLocaleString()} TPM / ${analysis.cost_analysis.comparison.upper_break_even_tpm ? `${Math.round(analysis.cost_analysis.comparison.upper_break_even_tpm).toLocaleString()} TPM` : 'No upper bound'}`
                      : 'No break-even'}
                  </strong>
                </div>
              </div>
              {costCurveData.length === 0 ? <ChartEmpty height={300} /> : (<>
              <div
                className="cost-explorer-chart-frame"
                role="img"
                aria-label="PAYG and PTU plus spillover monthly cost by sustained throughput"
                aria-describedby="cost-explorer-chart-description"
              >
                <p className="visually-hidden" id="cost-explorer-chart-description">
                  PAYG costs {formatCurrency(analysis.cost_analysis.payg.payg_total)} per month. PTU plus spillover costs {formatCurrency(analysis.cost_analysis.hybrid.hybrid_total)} per month. {analysis.cost_analysis.comparison.break_even_tpm
                    ? `The lower break-even is ${Math.round(analysis.cost_analysis.comparison.break_even_tpm).toLocaleString()} TPM and ${analysis.cost_analysis.comparison.upper_break_even_tpm ? `the upper break-even is ${Math.round(analysis.cost_analysis.comparison.upper_break_even_tpm).toLocaleString()} TPM` : 'there is no upper break-even'}.`
                    : 'There is no economic break-even in the modeled range.'}
                </p>
                <DeferredResult><CostCurveChart
                  sustainedTpm={analysis.charts.cost_curves.sustained_tpm}
                  payg={analysis.charts.cost_curves.payg_monthly}
                  hybrid={analysis.charts.cost_curves.ptu_spill_monthly}
                  breakEvenTpm={analysis.charts.cost_curves.break_even_tpm ?? null}
                  upperBreakEvenTpm={analysis.charts.cost_curves.upper_break_even_tpm ?? null}
                  breakEvenCost={analysis.charts.cost_curves.break_even_tpm != null ? analysis.cost_analysis.hybrid.ptu_baseline_cost : null}
                  ptuFixedMonthly={analysis.cost_analysis.hybrid.ptu_baseline_cost}
                  ptuCapacityTpm={analysis.charts.cost_curves.ptu_capacity_tpm}
                  avgTpm={analysis.charts.cost_curves.avg_tpm}
                  selectedPtu={analysis.charts.cost_curves.selected_ptu}
                  paygAtAvg={analysis.charts.cost_curves.payg_at_avg}
                  hybridAtAvg={analysis.charts.cost_curves.hybrid_at_avg}
                  height={getChartHeight('cost', 300)}
                /></DeferredResult>
              </div>
              {breakEvenStatus && (
                <div className={`break-even-callout tone-${breakEvenStatus.tone}`}>
                  {breakEvenStatus.text}
                </div>
              )}
              </>)}
            </AnalyticalWidget>

            {/* Layer E: Commitment Safety Strip */}
            {analysis.cost_analysis.commitment_safety && (
            <div className={`commitment-safety-strip safety-${verdictCssClass(analysis.cost_analysis.commitment_safety.safety_verdict)}`}>
              <div className="safety-strip-items">
                <div className="safety-strip-item">
                  <span className="safety-strip-label">Savings Margin <InfoTip text="Percentage saved vs PAYG at current workload. Higher is better." /></span>
                  <strong>{analysis.cost_analysis.commitment_safety.savings_margin_pct.toFixed(1)}%</strong>
                </div>
                <div className="safety-strip-item">
                  <span className="safety-strip-label">Spillover <InfoTip text="Percentage of observed intervals where traffic exceeds PTU capacity." /></span>
                  <strong>{analysis.cost_analysis.commitment_safety.spillover_pct.toFixed(1)}%</strong>
                </div>
                <div className="safety-strip-item">
                  <span className="safety-strip-label">Capacity Coverage <InfoTip text="Percentage of intervals where all traffic fits within PTU commitment." /></span>
                  <strong>{analysis.cost_analysis.commitment_safety.capacity_coverage_pct.toFixed(1)}%</strong>
                </div>
                <div className="safety-strip-item safety-verdict-item">
                  <span className="safety-strip-label">Safety Verdict</span>
                  <strong>{VERDICT_LABELS[analysis.cost_analysis.commitment_safety.safety_verdict] ?? analysis.cost_analysis.commitment_safety.safety_verdict}</strong>
                </div>
              </div>
            </div>
            )}

            <article className="chart-card interpretation-card">
              <WidgetHeader title="Interpretation" tip="What this break-even point means for your current workload." />
              <p>{analysis.insights.break_even_message}</p>
              <ul>
                {analysis.insights.analysis_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </article>
            </>)}

            <h3 className="section-title section-title-with-icon stagger-7"><span className="stagger-7">Scoring Breakdown</span></h3>
            <p className="section-note">Each dimension includes a confidence score and key metrics with context tooltips.</p>
            <div className="dimension-grid">
              {analysis.dimensions.map((dim) => (
                <article className="chart-card dimension-card" key={dim.name} data-testid={`dimension-card-${dim.name.replace(/\s+/g, '-').toLowerCase()}`}>
                  <details className="dimension-details">
                    <summary>
                      <span className="dimension-title">{dim.name} <InfoTip text={dim.summary} /></span>
                      <span className={dimScoreClass(dim.score)}>{dim.score.toUpperCase()} · {(dim.confidence * 100).toFixed(0)}%</span>
                    </summary>
                    <p>{dim.summary}</p>
                    <p className="muted">{dim.explanation}</p>
                    {Object.keys(dim.key_metrics || {}).length > 0 && (
                      <div className="dimension-metrics">
                        {Object.entries(dim.key_metrics).map(([k, v]) => (
                          <div key={k} className="dimension-metric-item">
                            <span className="dimension-metric-label">{toTitleCaseLabel(k)} <InfoTip text={describeMetricKey(k)} /></span>
                            <strong>{typeof v === 'number' ? formatDimensionMetricValue(k, v) : String(v)}</strong>
                          </div>
                        ))}
                      </div>
                    )}
                  </details>
                </article>
              ))}
            </div>

            <article className="chart-card recommendation-context" data-testid="recommendation-context" id="rationale">
              <h3 className="section-title-with-icon"><span>Recommendation Rationale</span></h3>
              <div className="rationale-summary-grid">
                <div className="rationale-summary-item">
                  <span>Recommendation <InfoTip text="Current decision based on workload and cost signals." /></span>
                  <strong>{recommendationTitle.replace('Recommendation: ', '')}</strong>
                </div>
                <div className="rationale-summary-item">
                  <span>Confidence <InfoTip text="Model confidence in the recommendation using the four scoring dimensions." /></span>
                  <strong>{new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(analysis.confidence * 100)}%</strong>
                </div>
                <div className="rationale-summary-item">
                  <span>Average TPM <InfoTip text="Observed average tokens per minute for this deployment." /></span>
                  <strong>{new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(analysis.metrics.avg_tpm)}</strong>
                </div>
                <div className="rationale-summary-item">
                  <span>Break-even TPM <InfoTip text="Estimated TPM where PAYG and PTU + spillover costs become equal." /></span>
                  <strong>{analysis.cost_analysis.comparison.break_even_tpm ? `${formatNumber(analysis.cost_analysis.comparison.break_even_tpm)}${analysis.cost_analysis.comparison.upper_break_even_tpm ? ` - ${formatNumber(analysis.cost_analysis.comparison.upper_break_even_tpm)}` : ''}` : 'N/A'}</strong>
                </div>
              </div>
              <div className="context-grid">
                <div className="context-primary">
                  <h4>Why this recommendation fits</h4>
                  <div className="readable-block">
                    {toReadableParagraphs(analysis.explanation).map((line, idx) => (
                      <p key={`why-${idx}`}>{line}</p>
                    ))}
                  </div>
                </div>
                <div className="context-secondary">
                  <h4>What would change this call</h4>
                  <div className="readable-block">
                    {toReadableParagraphs(analysis.what_would_change).map((line, idx) => (
                      <p key={`change-${idx}`}>{line}</p>
                    ))}
                  </div>
                </div>
                <div className="context-secondary">
                  <h4>Data quality notes</h4>
                  <div className="readable-block">
                    {toReadableParagraphs(analysis.data_quality).map((line, idx) => (
                      <p key={`quality-${idx}`}>{line}</p>
                    ))}
                  </div>
                </div>
              </div>
            </article>

            {expandedChart && createPortal(
              <div className="chart-modal-backdrop" onClick={() => setExpandedChart(null)} />,
              document.body
            )}

            <button className="secondary stagger-8" onClick={() => { setExpandedChart(null); resetZoom(); setSelectedTimestamp(null); setBaseAnalysis(null); setAnalysis(null); setConsolidationSummary(null) }}>
              {"\u2190"} Back to Setup
            </button>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
