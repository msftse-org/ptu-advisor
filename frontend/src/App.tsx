import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api'
import {
  TokenVolumeChart,
  RequestOutcomesChart,
  DailyCostChart,
  ThrottleChart,
  TpmBandChart,
  CostCurveChart,
  LatencyOverlayChart,
  useChartZoom,
} from './charts'
import { ExportReport } from './ExportReport'
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
} from './telemetry'

type Mode = 'demo' | 'live'

const RESERVATION_OPTIONS = [
  'Hourly — No Commitment',
  'Monthly Commitment (Estimated 64% off)',
  '1-Year Commitment (Estimated 69% off)',
] as const

const FALLBACK_PRICING_REGIONS: PricingRegion[] = [
  { name: 'eastus', display_name: 'East US', multiplier: 1.0, zone: 'US' },
]

const FALLBACK_DEPLOYMENT_TYPES: DeploymentTypeOption[] = [
  { name: 'global', label: 'Global', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.0 },
  { name: 'data_zone', label: 'Data Zone', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.1 },
  { name: 'regional', label: 'Regional', increment: 50, default_min_ptu: 50, base_hourly_rate: 2.0 },
]

const APP_ICON_URL = 'https://cdn-icons-png.flaticon.com/512/1864/1864521.png'

/** Human-readable labels for snake_case safety verdicts */
const VERDICT_LABELS: Record<string, string> = {
  safe: 'Safe',
  efficient_but_risky: 'Efficient but Risky',
  not_justified: 'Not Justified',
}
/** Convert snake_case verdict to CSS class suffix (underscores → hyphens) */
const verdictCssClass = (v: string) => v.replace(/_/g, '-')

const LANDING_ICON_URLS = {
  usageAssessment: 'https://img.icons8.com/?size=96&id=0wd1lFcg9niE&format=png',
  costComparison: 'https://img.icons8.com/?size=96&id=peEJxLfmwJqr&format=png',
  recommendation: 'https://img.icons8.com/?size=96&id=KODlr2yUL7TT&format=png',
  calculator: 'https://img.icons8.com/?size=96&id=hUpjEYQjaJDL&format=png',
} as const

const RESULTS_ICON_URLS = {
  glance: 'https://img.icons8.com/?size=64&id=0wd1lFcg9niE&format=png',
  evidence: 'https://img.icons8.com/?size=64&id=3v3XjKKrjWMK&format=png',
  traffic: 'https://img.icons8.com/?size=64&id=spjDZODNvQqx&format=png',
  financial: 'https://img.icons8.com/?size=64&id=peEJxLfmwJqr&format=png',
  scoring: 'https://img.icons8.com/?size=64&id=6DLCmCMzHpAN&format=png',
  rationale: 'https://img.icons8.com/?size=64&id=KODlr2yUL7TT&format=png',
} as const



/* ── PTU Calculator model catalog ── */
const CALC_MODELS = [
  { id: 'gpt-4o', label: 'GPT-4o', tpmPerPtu: 2500, inputPer1M: 2.50, outputPer1M: 10.00, outputRatio: 3, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'gpt-4o-mini', label: 'GPT-4o Mini', tpmPerPtu: 37000, inputPer1M: 0.15, outputPer1M: 0.60, outputRatio: 3, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-4.1', label: 'GPT-4.1', tpmPerPtu: 4750, inputPer1M: 2.00, outputPer1M: 8.00, outputRatio: 4, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'gpt-4.1-mini', label: 'GPT-4.1 Mini', tpmPerPtu: 23750, inputPer1M: 0.40, outputPer1M: 1.60, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-4.1-nano', label: 'GPT-4.1 Nano', tpmPerPtu: 59400, inputPer1M: 0.10, outputPer1M: 0.40, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'gpt-5', label: 'GPT-5', tpmPerPtu: 3400, inputPer1M: 1.25, outputPer1M: 10.00, outputRatio: 8, globalMin: 15, regionalMin: 50, globalInc: 5, regionalInc: 50 },
  { id: 'o3-mini', label: 'o3-mini', tpmPerPtu: 14900, inputPer1M: 1.10, outputPer1M: 4.40, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
  { id: 'o4-mini', label: 'o4-mini', tpmPerPtu: 5400, inputPer1M: 1.10, outputPer1M: 4.40, outputRatio: 4, globalMin: 15, regionalMin: 25, globalInc: 5, regionalInc: 25 },
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

/** Adaptive date label: date-only when dense, date+time when sparse. */
function formatDateLabel(iso: string, _idx?: number, _allLabels?: string[]): string {
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
    return <span className="rec-badge rec-badge-positive">{"\u2713"} PTU Recommended</span>
  }
  if (recommendation === 'ptu_not_recommended') {
    return <span className="rec-badge rec-badge-negative">{"\u2014"} Stay on PAYG</span>
  }
  return <span className="rec-badge rec-badge-borderline">{"\u26A0"} Borderline</span>
}

function dimScoreClass(score: string): string {
  const s = score.toLowerCase()
  if (s === 'positive') return 'dim-score dim-score-positive'
  if (s === 'negative') return 'dim-score dim-score-negative'
  if (s === 'neutral') return 'dim-score dim-score-neutral'
  return 'dim-score dim-score-insufficient'
}

function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip" aria-label={`Info: ${text}`} role="note" tabIndex={0}>
      <span className="info-tip-icon" aria-hidden="true">
        i
      </span>
      <span className="tip-bubble">{text}</span>
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

function FeatureCard({
  title,
  description,
  icon,
  onClick,
  isActive,
  variant,
}: {
  title: string
  description: string
  icon: ReactNode
  onClick: () => void
  isActive: boolean
  variant?: 'default' | 'calculator'
}) {
  return (
    <button
      type="button"
      className={`feature-card${variant === 'calculator' ? ' feature-card-calc' : ''}${isActive ? ' is-active' : ''}`}
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={`${title}. ${description}`}
    >
      {icon}
      <h3>{title}</h3>
      <p>{description}</p>
    </button>
  )
}

function App() {
  const [mode, setMode] = useState<Mode>('live')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)

  // Chart zoom state — ECharts dataZoom
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null)
  const [granularityMinutes, setGranularityMinutes] = useState<1 | 5 | 15 | 30>(1)
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

  const [subscriptions, setSubscriptions] = useState<SubscriptionInfo[]>([])
  const [subscriptionsLoading, setSubscriptionsLoading] = useState(false)
  const [subscriptionId, setSubscriptionId] = useState(() => localStorage.getItem('ptu_last_subscription') || '')
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)

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
      setAuthStatus(null)
      return
    }
    emitAzureConnectStarted({ policy_version: POLICY_VERSION, tenant_id_hash: '' })
    api.authStatus()
      .then((status) => {
        setAuthStatus(status)
        const tidHash = hashTenantId(status.tenant_id || '')
        if (status.authenticated) {
          emitAzureConnectSucceeded({ policy_version: POLICY_VERSION, tenant_id_hash: tidHash, display_name: status.display_name })
        } else {
          emitAzureConnectFailed({ policy_version: POLICY_VERSION, tenant_id_hash: tidHash, error_type: status.error || 'auth_failed' })
        }
      })
      .catch((e) => {
        setAuthStatus({ authenticated: false, display_name: '', email: '', tenant_id: '', error: 'Failed to check authentication status.' })
        emitAzureConnectFailed({ policy_version: POLICY_VERSION, tenant_id_hash: '', error_type: e instanceof Error ? e.message : 'network_error' })
      })
  }, [mode, discoveryKey])

  useEffect(() => {
    if (mode !== 'live') {
      return
    }
    setSubscriptionsLoading(true)
    const t0 = performance.now()
    api.subscriptions()
      .then((items) => {
        const elapsed = performance.now() - t0
        setSubscriptions(items)
        emitDiscoverySubscriptionsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), subscription_count: items.length })
        if (elapsed > PERF_BUDGET.FULL_DISCOVERY_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), operation: 'subscriptions_load', budget_ms: PERF_BUDGET.FULL_DISCOVERY_MS, actual_ms: elapsed })
        }
        if (items.length > 0) {
          setSubscriptionId((current) => current || items[0].subscription_id)
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSubscriptionsLoading(false))
  }, [mode, discoveryKey])

  useEffect(() => {
    if (mode !== 'live' || !subscriptionId) {
      return
    }
    setAccounts([])
    setAccountKey('')
    setDeployments([])
    setDeploymentName('')

    const t0 = performance.now()
    api.accounts(subscriptionId)
      .then((items) => {
        const elapsed = performance.now() - t0
        setAccounts(items)
        emitDiscoveryAccountsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), account_count: items.length })
        if (elapsed > PERF_BUDGET.CACHED_CHANGE_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), operation: 'accounts_load', budget_ms: PERF_BUDGET.CACHED_CHANGE_MS, actual_ms: elapsed })
        }
        if (items.length > 0) {
          const first = `${items[0].resource_group}|${items[0].name}`
          setAccountKey(first)
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [mode, subscriptionId])

  const selectedAccount = useMemo(() => {
    return accounts.find((a) => `${a.resource_group}|${a.name}` === accountKey) ?? null
  }, [accounts, accountKey])

  useEffect(() => {
    if (mode !== 'live' || !subscriptionId || !selectedAccount) {
      return
    }
    setDeployments([])
    setDeploymentName('')

    // Sync the assumptions region to the account's actual Azure region
    const loc = selectedAccount.location.toLowerCase().replace(/\s+/g, '')
    if (pricingRegions.some((r) => r.name === loc)) {
      setSelectedRegion(loc)
    }

    const t0 = performance.now()
    api.deployments(subscriptionId, selectedAccount.resource_group, selectedAccount.name)
      .then((items) => {
        const elapsed = performance.now() - t0
        // Sort: PTU-eligible first, then alphabetical within each group
        const sorted = [...items].sort((a, b) => {
          if (a.ptu_eligible !== b.ptu_eligible) return a.ptu_eligible ? -1 : 1
          return a.name.localeCompare(b.name)
        })
        setDeployments(sorted)
        emitDiscoveryDeploymentsLoaded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), deployment_count: sorted.length })
        if (elapsed > PERF_BUDGET.CACHED_CHANGE_MS) {
          emitPerformanceBudgetExceeded({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), operation: 'deployments_load', budget_ms: PERF_BUDGET.CACHED_CHANGE_MS, actual_ms: elapsed })
        }
        // Auto-select the first eligible deployment
        const firstEligible = sorted.find((d) => d.ptu_eligible)
        if (firstEligible) {
          setDeploymentName(firstEligible.name)
        } else if (sorted.length > 0) {
          setDeploymentName('')  // No eligible deployments — don't select any
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [mode, subscriptionId, selectedAccount])

  const runAnalysis = useCallback(async ({ preserveCurrent = false, timeWindow = null, updateCharts = true }: RunAnalysisOptions = {}) => {
    setLoading(true)
    setError('')
    emitAnalysisRunStarted({ policy_version: POLICY_VERSION, tenant_id_hash: hashTenantId(authStatus?.tenant_id || ''), mode })
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
      const overrideParams: Record<string, number> = {}
      if (paygInputOverride != null) overrideParams.payg_input_rate_override = paygInputOverride
      if (paygOutputOverride != null) overrideParams.payg_output_rate_override = paygOutputOverride
      if (ptuHourlyOverride != null) overrideParams.ptu_hourly_rate_override = ptuHourlyOverride

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
              return { ...current, recommendation: result.recommendation, confidence: result.confidence, summary: result.summary, explanation: result.explanation, what_would_change: result.what_would_change, data_quality: result.data_quality, analysis_period: result.analysis_period, dimensions: result.dimensions, metrics: result.metrics, cost_analysis: result.cost_analysis, insights: result.insights, charts: { ...current.charts, daily_cost: result.charts.daily_cost } }
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
            return { ...current, recommendation: result.recommendation, confidence: result.confidence, summary: result.summary, explanation: result.explanation, what_would_change: result.what_would_change, data_quality: result.data_quality, analysis_period: result.analysis_period, dimensions: result.dimensions, metrics: result.metrics, cost_analysis: result.cost_analysis, insights: result.insights, charts: { ...current.charts, cost_curves: result.charts.cost_curves } }
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
    subscriptionId,
    selectedAccount,
    deploymentName,
    selectedDeployments,
    analysis,
    paygInputOverride,
    paygOutputOverride,
    ptuHourlyOverride,
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
    }
    const currentKey = `${reservationType}|${baselinePtu}|${selectedRegion}|${selectedDeploymentType}|${granularityMinutes}|${includeThrottle}|${paygInputOverride}|${paygOutputOverride}|${ptuHourlyOverride}`
    if (!previousAssumptionKey.current) {
      previousAssumptionKey.current = currentKey
      previousAssumptionParts.current = parts
      return
    }

    if (previousAssumptionKey.current === currentKey || loading) {
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
  }, [analysis, reservationType, baselinePtu, selectedRegion, selectedDeploymentType, granularityMinutes, includeThrottle, paygInputOverride, paygOutputOverride, ptuHourlyOverride, loading, runAnalysis, getReAnalyzeWindow])

  // ── Telemetry: cost_recalculated ──
  const previousCostKey = useRef('')
  useEffect(() => {
    if (!analysis || loading) return
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
  }, [analysis, loading])

  useEffect(() => {
    if (!expandedChart) return
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpandedChart(null) }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [expandedChart])

  const recommendationClass = useMemo(() => {
    if (!analysis) return ''
    if (analysis.recommendation === 'ptu_recommended') return 'rec-positive'
    if (analysis.recommendation === 'ptu_not_recommended') return 'rec-negative'
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
    return 'PTU and PAYG are currently close. Validate with additional data before committing.'
  }, [analysis])

  const selectedRegionMeta = useMemo(() => {
    return pricingRegions.find((region) => region.name === selectedRegion) ?? null
  }, [pricingRegions, selectedRegion])

  const selectedDeploymentTypeMeta = useMemo(() => {
    return deploymentTypeOptions.find((item) => item.name === selectedDeploymentType) ?? null
  }, [deploymentTypeOptions, selectedDeploymentType])

  const breakEvenStatus = useMemo(() => {
    if (!analysis) return null
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
    const distancePct = ((avgTpm - breakEven) / breakEven) * 100
    if (distancePct > 10) {
      return { tone: 'positive' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is ${distancePct.toFixed(0)}% above that threshold, so the economic signal favors PTU. Safety verdict: ${safetyLabel}.` }
    }
    if (distancePct >= -10) {
      return { tone: 'neutral' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is near that threshold, so the economic signal is marginal. Safety verdict: ${safetyLabel}.` }
    }
    return { tone: 'negative' as const, breakEvenTpm: breakEven, avgTpm, distancePct, selectedPtu, text: `Economic break-even for ${selectedPtu} PTU: ${breakEven.toLocaleString(undefined, { maximumFractionDigits: 0 })} TPM. Your avg TPM is ${Math.abs(distancePct).toFixed(0)}% below that threshold, so the economic signal favors PAYG. Safety verdict: ${safetyLabel}.` }
  }, [analysis])

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
    const HOURS_PER_MONTH = 730

    const inputFrac = (100 - calcOutputPct) / 100
    const outputFrac = calcOutputPct / 100

    // Blended PAYG rate per 1M tokens
    const blendedRate = inputFrac * model.inputPer1M + outputFrac * model.outputPer1M

    // PAYG monthly cost (avg TPM sustained 24/7)
    const monthlyTokens = calcAvgTpm * MINUTES_PER_MONTH
    const paygMonthly = (monthlyTokens / 1_000_000) * blendedRate

    // Effective multiplier: input tokens are 1:1, output tokens cost more PTU capacity
    const effectiveMult = inputFrac + outputFrac * model.outputRatio

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
    const overflowCost = (overflowTokensMonthly / 1_000_000) * blendedRate

    const hybridBase = ptuBase * baseRate * regionMult * HOURS_PER_MONTH
    const hybridOnDemand = hybridBase + overflowCost
    const hybrid1Year = hybridBase * 0.75 + overflowCost
    const hybrid3Year = hybridBase * 0.55 + overflowCost

    // Break-even: analytical fixed-PTU formula (v3 model)
    // In the flat phase: PAYG = tpm × 43200 / 1M × rate, PTU = ptu_fixed
    // Cross: tpm = ptu_fixed × 1M / (43200 × rate)
    let breakEvenTpm: number | null = null
    const ptuFixed = ptuBase * baseRate * regionMult * HOURS_PER_MONTH
    if (blendedRate > 0) {
      const flatBreakEven = (ptuFixed * 1_000_000) / (MINUTES_PER_MONTH * blendedRate)
      if (flatBreakEven <= ptuCapacityRaw) {
        breakEvenTpm = flatBreakEven
      }
      // Rising phase has the same per-TPM slope → lines are parallel → no cross.
    }

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
      ptuFull,
      ptuBase,
      ptuCapacityRaw,
      overflowTpm,
      blendedRate,
      monthlyTokens,
    }
  }, [calcModel, calcAvgTpm, calcPeakTpm, calcOutputPct, calcPeakHours, calcRegion, calcDeployType, pricingRegions, deploymentTypeOptions])

  return (
    <div className="app-shell">
      {toastMessage && (
        <div className="toast-notification" role="status" aria-live="polite">
          <span>{toastMessage}</span>
          <button type="button" className="toast-dismiss" onClick={() => setToastMessage(null)} aria-label="Dismiss">&times;</button>
        </div>
      )}
      <div className="container">
        {!analysis && (
          <>
            <header className="hero">
              <div className="hero-orb hero-orb-1" />
              <div className="hero-orb hero-orb-2" />
              <div className="hero-badge">Azure OpenAI</div>
              <div className="hero-title-row" aria-label="PTU Advisor logo and title">
                <img src={APP_ICON_URL} alt="PTU Advisor logo" className="top-left-brand-icon" />
                <h1>PTU Advisor</h1>
              </div>
              <p className="hero-subtitle">Assess PTU and PAYG economics for Azure OpenAI deployments using observed traffic and cost signals.</p>
              <div className="hero-trust">
                <span className="trust-item trust-item-insight"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 0l1.76 4.58L14 5.24l-3.82 3.18L11.36 14 7 11.09 2.64 14l1.18-5.58L0 5.24l5.24-.66L7 0z" fill="currentColor"/></svg> Metrics-backed guidance</span>
                <span className="trust-divider" />
                <span className="trust-item trust-item-assurance"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" fill="none"/><path d="M4 7l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg> Production-ready controls</span>
                <span className="trust-divider" />
                <span className="trust-item trust-item-clarity"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="3" width="12" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3" fill="none"/><path d="M1 6h12" stroke="currentColor" strokeWidth="1.3"/><circle cx="4" cy="8.5" r="1" fill="currentColor"/></svg> Cost and capacity visibility</span>
              </div>
            </header>

            <div className="features-showcase">
              <FeatureCard
                title="Usage Assessment"
                description="Connect your Azure account and analyze real deployment metrics over your chosen lookback window."
                onClick={() => setActiveView('advisor')}
                isActive={activeView === 'advisor'}
                icon={(
                  <div className="feature-icon feature-icon-analyze" aria-hidden="true">
                    <img src={LANDING_ICON_URLS.usageAssessment} alt="" className="feature-icon-image" loading="lazy" decoding="async" />
                  </div>
                )}
              />
              <FeatureCard
                title="Cost Scenario Comparison"
                description="Side-by-side PAYG vs PTU + spillover cost models with break-even analysis and savings projection."
                onClick={() => setActiveView('advisor')}
                isActive={activeView === 'advisor'}
                icon={(
                  <div className="feature-icon feature-icon-compare" aria-hidden="true">
                    <img src={LANDING_ICON_URLS.costComparison} alt="" className="feature-icon-image" loading="lazy" decoding="async" />
                  </div>
                )}
              />
              <FeatureCard
                title="Recommendation Rationale"
                description="Get a confidence-scored recommendation backed by 4-dimension scoring and financial modeling."
                onClick={() => setActiveView('advisor')}
                isActive={activeView === 'advisor'}
                icon={(
                  <div className="feature-icon feature-icon-recommend" aria-hidden="true">
                    <img src={LANDING_ICON_URLS.recommendation} alt="" className="feature-icon-image" loading="lazy" decoding="async" />
                  </div>
                )}
              />
              <FeatureCard
                title="PTU Calculator"
                description="Estimate PTU vs PAYG costs from usage estimates — no Azure connection required."
                onClick={() => setActiveView('calculator')}
                isActive={activeView === 'calculator'}
                variant="calculator"
                icon={(
                  <div className="feature-icon feature-icon-calc" aria-hidden="true">
                    <img src={LANDING_ICON_URLS.calculator} alt="" className="feature-icon-image" loading="lazy" decoding="async" />
                  </div>
                )}
              />
            </div>
          </>
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

                <table className="calc-scenario-table">
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

                <div className="calc-details-row">
                  <div className="calc-detail-card">
                    <span className="calc-detail-label">Break-Even TPM</span>
                    <span className="calc-detail-value">{calcResult.breakEvenTpm ? calcResult.breakEvenTpm.toLocaleString(undefined, { maximumFractionDigits: 0 }) : 'N/A'}</span>
                    <span className="calc-detail-sub">Sustained TPM where PTU = PAYG cost</span>
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
          <section className="results results-v2" style={{ position: 'relative' }}>
            {loading && <ThinkingOverlay />}
            <div className={`result-banner ${recommendationClass}`}>
              <div className="result-banner-top">
                <RecBadge recommendation={analysis.recommendation} />
                <p className="confidence">Confidence score: {(analysis.confidence * 100).toFixed(1)}%</p>
                <ExportReport analysis={analysis} baseAnalysis={baseAnalysis} isZoomed={zoomState.isDirty} consolidationSummary={consolidationSummary} />
              </div>
              <h2 className="result-banner-title">{recommendationTitle}</h2>
              <p className="result-banner-summary">{recommendationSummary}</p>
            </div>

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
                          <td colSpan={3}>{formatNumber(analysis.cost_analysis.comparison.break_even_tpm)} TPM</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </article>
            )}

            <h3 className="section-title section-title-with-icon stagger-1"><img src={RESULTS_ICON_URLS.glance} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-1">At a Glance</span></h3>
            <div className="glance-grid stagger-2">
              <article className="glance-card">
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
            </div>

            <h3 className="section-title section-title-with-icon stagger-3"><img src={RESULTS_ICON_URLS.evidence} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-3">Evidence</span></h3>
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
              <article className={`chart-card${expandedChart === 'tokens' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Token Volume Over Time" tip="Shows prompt tokens (input) and completion tokens (output) consumed per interval. Spikes indicate bursts of usage. A flat, high line suggests steady workload — a good PTU candidate." onExpand={() => setExpandedChart(expandedChart === 'tokens' ? null : 'tokens')} />
                {tokenChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <TokenVolumeChart
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
                />
                )}
              </article>

              <article className={`chart-card${expandedChart === 'requests' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Request Outcomes" tip="Displays successful API calls vs HTTP 429 (rate-limited) responses per interval. High 429 counts signal capacity pressure — PTU eliminates these by reserving dedicated throughput." onExpand={() => setExpandedChart(expandedChart === 'requests' ? null : 'requests')} />
                {requestsChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <RequestOutcomesChart
                  timestamps={analysis!.charts.requests.timestamps}
                  successful={analysis!.charts.requests.successful}
                  throttled={analysis!.charts.requests.throttled}
                  height={getChartHeight('requests', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                  perDeployment={perDepCharts?.requests.per_deployment}
                />
                )}
              </article>

              <article className={`chart-card${expandedChart === 'dailyCost' ? ' is-chart-expanded' : ''}`}>
                <h4 className="widget-header">
                  <span>Daily Deployment Cost{dailyCostChartData.length > 0 && <span className="cost-total-tag">Total: ${analysis!.charts.daily_cost.total_cost.reduce((a, b) => a + b, 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}</span>
                  <span className="widget-header-actions">
                    <button className="chart-expand-btn" onClick={() => setExpandedChart(expandedChart === 'dailyCost' ? null : 'dailyCost')} aria-label="Expand Daily Deployment Cost" title="Expand chart">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" /></svg>
                    </button>
                    <InfoTip text="Stacked bars show daily input and output token costs at PAYG rates. The dashed lines mark average daily spend and what a PTU baseline would cost per day — compare bars to lines to see if PTU saves money." />
                  </span>
                </h4>
                {dailyCostChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <DailyCostChart
                  timestamps={analysis!.charts.daily_cost.dates}
                  inputCost={analysis!.charts.daily_cost.input_cost}
                  outputCost={analysis!.charts.daily_cost.output_cost}
                  avgDailyCost={analysis!.charts.daily_cost.avg_daily_cost}
                  ptuDailyCost={analysis!.charts.daily_cost.ptu_daily_cost}
                  height={getChartHeight('dailyCost', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                />
                )}
              </article>

              <article className={`chart-card${expandedChart === 'throttle' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Rate-Limit Events (429)" tip="Shows the count of HTTP 429 rate-limit responses per interval. Frequent spikes mean your traffic regularly exceeds PAYG quota, causing retries and latency. PTU provisioning removes this bottleneck." onExpand={() => setExpandedChart(expandedChart === 'throttle' ? null : 'throttle')} />
                {throttleChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <ThrottleChart
                  timestamps={analysis!.charts.throttling.timestamps}
                  throttled={analysis!.charts.throttling.values}
                  height={getChartHeight('throttle', 240)}
                  zoomState={zoomState}
                  onDataZoom={onDataZoom}
                  selectedTimestamp={selectedTimestamp}
                  perDeployment={perDepCharts?.throttling.per_deployment}
                />
                )}
              </article>
            </div>

            <article className={`chart-card wide-card${expandedChart === 'tpm' ? ' is-chart-expanded' : ''}`}>
              <WidgetHeader title={`Throughput Band (TPM vs Avg/${tpmRefLabel})`} tip={`Shows actual tokens-per-minute over time against the average (dashed green) and ${tpmRefLabel} reference (dashed orange). When the blue area stays consistently above the ${tpmRefLabel} line, your workload is large enough to benefit from PTU.`} onExpand={() => setExpandedChart(expandedChart === 'tpm' ? null : 'tpm')} />
              {tpmChartData.length === 0 ? <ChartEmpty height={280} /> : (
              <TpmBandChart
                timestamps={analysis!.charts.tpm.timestamps}
                tpm={analysis!.charts.tpm.values}
                avg={analysis!.charts.tpm.avg}
                refLine={analysis!.charts.cost_curves.break_even_tpm ?? analysis!.charts.tpm.p25}
                refLabel={tpmRefLabel}
                height={getChartHeight('tpm', 280)}
                zoomState={zoomState}
                onDataZoom={onDataZoom}
                selectedTimestamp={selectedTimestamp}
                perDeployment={perDepCharts?.tpm.per_deployment}
              />
              )}
            </article>

            {perDepCharts?.latency && (
            <article className="chart-card wide-card">
              <WidgetHeader title="Latency Overlay (P50 / P95)" tip="Shows per-deployment P95 latency as solid lines and combined P50/P95 as dashed white lines. Use this to identify which deployments contribute most to overall latency." />
              <LatencyOverlayChart
                timestamps={perDepCharts.latency.timestamps}
                combined={perDepCharts.latency.combined}
                perDeployment={perDepCharts.latency.per_deployment}
                height={280}
                zoomState={zoomState}
                onDataZoom={onDataZoom}
                selectedTimestamp={selectedTimestamp}
              />
            </article>
            )}

            <h3 className="section-title section-title-with-icon stagger-5"><img src={RESULTS_ICON_URLS.traffic} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-5">Traffic Shape Signals</span></h3>
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

            <h3 className="section-title section-title-with-icon stagger-6"><img src={RESULTS_ICON_URLS.financial} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-6">Financial Decision</span> <PricingSourceBadge source={analysis.cost_analysis.pricing.pricing_source} asOf={analysis.cost_analysis.pricing.pricing_as_of} /></h3>

            {analysis.cost_analysis.pricing.pricing_source === 'fallback' && (
              <div className="pricing-fallback-banner" role="alert">
                <strong>Using default pricing</strong> — live pricing unavailable. Cost figures are based on static fallback rates and may not reflect current Azure pricing.
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
                  <select value={reservationType} onChange={(e) => setReservationType(e.target.value)}>
                    {RESERVATION_OPTIONS.map((term) => (
                      <option key={term} value={term}>
                        {term}
                      </option>
                    ))}
                  </select>
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
                    {(paygInputOverride != null || paygOutputOverride != null || ptuHourlyOverride != null) && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => { setPaygInputOverride(null); setPaygOutputOverride(null); setPtuHourlyOverride(null) }}
                      >
                        Reset to auto-resolved rates
                      </button>
                    )}
                  </div>
                </details>
              </div>
            </article>

            <details className="calculation-details" open>
              <summary>
                <h3 className="section-title calc-section-title">Calculation Details</h3>
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

            <article className={`chart-card wide-card${expandedChart === 'cost' ? ' is-chart-expanded' : ''}`}>
              <WidgetHeader title={`Cost Explorer — Does my traffic justify ${analysis!.charts.cost_curves.selected_ptu} PTU?`} tip="X-axis shows sustained traffic (TPM). The PTU+Spillover line is flat while traffic fits within PTU, then rises as overflow spills to PAYG." onExpand={() => setExpandedChart(expandedChart === 'cost' ? null : 'cost')} helpContent="The hybrid PTU + Spillover model commits a fixed number of Provisioned Throughput Units (PTU) to cover your baseline traffic at a predictable monthly cost. When traffic stays within PTU capacity, the cost is flat regardless of how much of that capacity you use. When traffic spikes above PTU capacity, the excess tokens automatically spill over to standard pay-as-you-go (PAYG) pricing. This means you get cost predictability for steady-state traffic while still handling bursts without throttling. The break-even point is where the fixed PTU commitment starts saving money compared to running everything on PAYG. Note: the 'Your avg TPM' marker is a visual reference for orientation on the chart. The final recommendation is based on the full monthly workload shape, realized hybrid cost, and commitment-safety metrics — not solely on the average." />
              {costCurveData.length === 0 ? <ChartEmpty height={300} /> : (<>
              <CostCurveChart
                sustainedTpm={analysis!.charts.cost_curves.sustained_tpm}
                payg={analysis!.charts.cost_curves.payg_monthly}
                hybrid={analysis!.charts.cost_curves.ptu_spill_monthly}
                breakEvenTpm={analysis!.charts.cost_curves.break_even_tpm ?? null}
                breakEvenCost={analysis!.charts.cost_curves.break_even_tpm != null ? analysis!.cost_analysis.hybrid.ptu_baseline_cost : null}
                ptuCapacityTpm={analysis!.charts.cost_curves.ptu_capacity_tpm}
                avgTpm={analysis!.charts.cost_curves.avg_tpm}
                selectedPtu={analysis!.charts.cost_curves.selected_ptu}
                paygAtAvg={analysis!.charts.cost_curves.payg_at_avg}
                hybridAtAvg={analysis!.charts.cost_curves.hybrid_at_avg}
                height={getChartHeight('cost', 300)}
              />
              {breakEvenStatus && (
                <div className={`break-even-callout tone-${breakEvenStatus.tone}`}>
                  {breakEvenStatus.text}
                </div>
              )}
              </>)}
            </article>

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

            <div className="metrics-grid">
              <article className={`metric-card${analysis.cost_analysis.payg.payg_total <= analysis.cost_analysis.hybrid.hybrid_total ? ' is-winner' : ''}`}>
                <h3>PAYG Monthly <InfoTip text="Estimated monthly spend when all traffic remains on PAYG." /></h3>
                <p>{formatCurrency(analysis.cost_analysis.payg.payg_total)}</p>
              </article>
              <article className={`metric-card${analysis.cost_analysis.hybrid.hybrid_total <= analysis.cost_analysis.payg.payg_total ? ' is-winner' : ''}`}>
                <h3>PTU + Spillover <InfoTip text="PTU baseline commitment plus PAYG overflow above baseline capacity." /></h3>
                <p>{formatCurrency(analysis.cost_analysis.hybrid.hybrid_total)}</p>
              </article>
              <article className="metric-card">
                <h3>Difference <InfoTip text="Absolute monthly delta between PAYG and PTU+spillover strategies." /></h3>
                <p>{differenceSummary}</p>
              </article>
              <article className="metric-card">
                <h3>Break-even TPM <InfoTip text="Sustained TPM level where PTU+spillover and PAYG costs are equal." /></h3>
                <p>{analysis.cost_analysis.comparison.break_even_tpm ? formatNumber(analysis.cost_analysis.comparison.break_even_tpm) : 'N/A'}</p>
              </article>
            </div>

            <article className="chart-card interpretation-card">
              <WidgetHeader title="Interpretation" tip="What this break-even point means for your current workload." />
              <p>{analysis.insights.break_even_message}</p>
              <ul>
                {analysis.insights.analysis_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </article>

            <h3 className="section-title section-title-with-icon stagger-7"><img src={RESULTS_ICON_URLS.scoring} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-7">Scoring Breakdown</span></h3>
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

            <article className="chart-card recommendation-context" data-testid="recommendation-context">
              <h3 className="section-title-with-icon"><img src={RESULTS_ICON_URLS.rationale} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span>Recommendation Rationale</span></h3>
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
                  <strong>{analysis.cost_analysis.comparison.break_even_tpm ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(analysis.cost_analysis.comparison.break_even_tpm) : 'N/A'}</strong>
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
      </div>
    </div>
  )
}

export default App
