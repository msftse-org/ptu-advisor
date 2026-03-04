import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from './api'
import type {
  AccountInfo,
  AnalysisResponse,
  DeploymentInfo,
  DeploymentTypeOption,
  FocusTopic,
  PricingRegion,
  SubscriptionInfo,
} from './types'

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

const CHART_COLORS = {
  primary: '#5B7FFF',
  secondary: '#7B8EAF',
  success: '#2F9E77',
  danger: '#B35252',
  warning: '#C58A2A',
  neutral: '#9DAAC0',
} as const

const CHART_TOOLTIP_STYLE = {
  background: 'rgba(8, 14, 26, 0.96)',
  border: '1px solid rgba(91, 127, 255, 0.32)',
  borderRadius: '10px',
  color: '#e8ecf2',
  fontSize: '12px',
}

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

type CalcScenario = { name: string; term: string; cost: number; ptuUnits: number }
type LegendEntry = { label: string; color: string }
type CostCurvePoint = { baselineTpm: number; payg: number; hybrid: number; ptuUnits: number }

function StaticLegend({ items }: { items: LegendEntry[] }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', fontSize: 11, color: '#b5becc' }}>
      {items.map((item) => (
        <span key={item.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 2, background: item.color, borderRadius: 999 }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

function CostCurveTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color?: string; payload?: CostCurvePoint }>; label?: string | number }) {
  if (!active || !payload || payload.length === 0) return null

  const point = payload[0]?.payload
  const baseline = typeof label === 'number' ? formatWithCommas(label) : String(label ?? '')
  const paygValue = payload.find((entry) => entry.name === 'PAYG')?.value
  const hybridValue = payload.find((entry) => entry.name === 'PTU + Spillover')?.value

  return (
    <div style={{ ...CHART_TOOLTIP_STYLE, minWidth: 190 }}>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>Baseline: {baseline} TPM</div>
      <div style={{ marginBottom: 4, color: '#cbd7f2' }}>PTU at point: {point?.ptuUnits ?? 0}</div>
      <div style={{ color: CHART_COLORS.primary }}>PAYG: {typeof paygValue === 'number' ? formatCurrency(paygValue) : '—'}</div>
      <div style={{ color: CHART_COLORS.success }}>PTU + Spillover: {typeof hybridValue === 'number' ? formatCurrency(hybridValue) : '—'}</div>
    </div>
  )
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

/** Format a number with comma thousand-separators (e.g. 1,234,567). */
function formatWithCommas(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
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

function WidgetHeader({ title, tip, onExpand }: { title: string; tip: string; onExpand?: () => void }) {
  return (
    <h4 className="widget-header">
      <span>{title}</span>
      <span className="widget-header-actions">
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

  // Chart zoom state — drag-to-zoom across all time-series charts
  const [zoomLeft, setZoomLeft] = useState<string | null>(null)
  const [zoomRight, setZoomRight] = useState<string | null>(null)
  const [zoomDomain, setZoomDomain] = useState<[number, number] | null>(null)

  const [lookbackDays, setLookbackDays] = useState(14)
  const [reservationType, setReservationType] = useState<string>('Monthly Commitment (Estimated 64% off)')
  const [baselinePtu, setBaselinePtu] = useState<number | null>(null)
  const [focusTopics, setFocusTopics] = useState<FocusTopic[]>([])
  const [focusTopic, setFocusTopic] = useState('Cost Reduction')
  const [pricingRegions, setPricingRegions] = useState<PricingRegion[]>([])
  const [deploymentTypeOptions, setDeploymentTypeOptions] = useState<DeploymentTypeOption[]>([])
  const [selectedRegion, setSelectedRegion] = useState('eastus')
  const [selectedDeploymentType, setSelectedDeploymentType] = useState<'global' | 'data_zone' | 'regional'>('global')

  const [subscriptions, setSubscriptions] = useState<SubscriptionInfo[]>([])
  const [subscriptionId, setSubscriptionId] = useState('')

  const [accounts, setAccounts] = useState<AccountInfo[]>([])
  const [accountKey, setAccountKey] = useState('')

  const [deployments, setDeployments] = useState<DeploymentInfo[]>([])
  const [deploymentName, setDeploymentName] = useState('')

  // ── App-level view: Deployment Advisor vs PTU Calculator ──
  const [activeView, setActiveView] = useState<'advisor' | 'calculator'>('advisor')

  // ── PTU Calculator form state ──
  const [calcModel, setCalcModel] = useState('gpt-4o')
  const [calcAvgTpm, setCalcAvgTpm] = useState(50000)
  const [calcPeakTpm, setCalcPeakTpm] = useState(120000)
  const [calcOutputPct, setCalcOutputPct] = useState(40)
  const [calcPeakHours, setCalcPeakHours] = useState(4)
  const [calcRegion, setCalcRegion] = useState('eastus')
  const [calcDeployType, setCalcDeployType] = useState<'global' | 'data_zone' | 'regional'>('global')

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
      return
    }
    api.subscriptions()
      .then((items) => {
        setSubscriptions(items)
        if (items.length > 0) {
          setSubscriptionId((current) => current || items[0].subscription_id)
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [mode])

  useEffect(() => {
    if (mode !== 'live' || !subscriptionId) {
      return
    }
    setAccounts([])
    setAccountKey('')
    setDeployments([])
    setDeploymentName('')

    api.accounts(subscriptionId)
      .then((items) => {
        setAccounts(items)
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

    api.deployments(subscriptionId, selectedAccount.resource_group, selectedAccount.name)
      .then((items) => {
        setDeployments(items)
        if (items.length > 0) {
          setDeploymentName(items[0].name)
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [mode, subscriptionId, selectedAccount])

  const runAnalysis = useCallback(async (preserveCurrent = false) => {
    setLoading(true)
    setError('')
    if (!preserveCurrent) {
      setAnalysis(null)
      setBaselinePtu(null) // Reset so next analysis picks its own default
    }
    try {
      // Only send baseline_ptu when known (after first analysis sets the default)
      const ptuParam = baselinePtu != null ? { baseline_ptu: baselinePtu } : {}
      if (mode === 'demo') {
        const result = await api.analyze({
          mode: 'demo',
          focus_topic: focusTopic,
          lookback_days: lookbackDays,
          reservation_type: reservationType,
          region: selectedRegion,
          deployment_type: selectedDeploymentType,
          ...ptuParam,
        })
        // Initialise the PTU slider on first analysis load
        if (baselinePtu == null) {
          setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
        }
        setAnalysis(result)
        return
      }

      if (!subscriptionId || !selectedAccount || !deploymentName) {
        throw new Error('Please select subscription, account, and deployment.')
      }

      const result = await api.analyze({
        mode: 'live',
        lookback_days: lookbackDays,
        subscription_id: subscriptionId,
        resource_group: selectedAccount.resource_group,
        workspace: selectedAccount.name,
        deployment: deploymentName,
        focus_topic: focusTopic,
        reservation_type: reservationType,
        region: selectedRegion,
        deployment_type: selectedDeploymentType,
        ...ptuParam,
      })
      // Initialise the PTU slider on first analysis load
      if (baselinePtu == null) {
        setBaselinePtu(result.cost_analysis.hybrid.baseline_ptu)
      }
      setAnalysis(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }, [
    mode,
    focusTopic,
    lookbackDays,
    reservationType,
    baselinePtu,
    selectedRegion,
    selectedDeploymentType,
    subscriptionId,
    selectedAccount,
    deploymentName,
  ])

  const previousAssumptionKey = useRef('')

  useEffect(() => {
    if (!analysis) {
      previousAssumptionKey.current = ''
      return
    }

    const currentKey = `${reservationType}|${baselinePtu}|${selectedRegion}|${selectedDeploymentType}`
    if (!previousAssumptionKey.current) {
      previousAssumptionKey.current = currentKey
      return
    }

    if (previousAssumptionKey.current === currentKey || loading) {
      return
    }

    previousAssumptionKey.current = currentKey
    const timer = setTimeout(() => {
      runAnalysis(true)
    }, 250)

    return () => clearTimeout(timer)
  }, [analysis, reservationType, baselinePtu, selectedRegion, selectedDeploymentType, loading, runAnalysis])

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
      time: smartDateFmt(ts),
      prompt: series.prompt[idx] ?? 0,
      completion: series.completion[idx] ?? 0,
      total: series.total[idx] ?? 0,
    }))
  }, [analysis, smartDateFmt])

  const requestsChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.requests
    return series.timestamps.map((ts, idx) => ({
      time: smartDateFmt(ts),
      successful: series.successful[idx] ?? 0,
      throttled: series.throttled[idx] ?? 0,
      total: series.total[idx] ?? 0,
    }))
  }, [analysis, smartDateFmt])

  const latencyChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.latency
    return series.timestamps.map((ts, idx) => ({
      time: smartDateFmt(ts),
      p50: series.p50[idx] ?? 0,
      p95: series.p95[idx] ?? 0,
      p99: series.p99[idx] ?? 0,
    }))
  }, [analysis, smartDateFmt])

  const throttleChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.throttling
    return series.timestamps.map((ts, idx) => ({
      time: smartDateFmt(ts),
      throttled: series.values[idx] ?? 0,
    }))
  }, [analysis, smartDateFmt])

  const tpmChartData = useMemo(() => {
    if (!analysis) return []
    const series = analysis.charts.tpm
    const refTpm = analysis.charts.cost_curves.break_even_tpm ?? series.p25
    return series.timestamps.map((ts, idx) => ({
      time: smartDateFmt(ts),
      tpm: series.values[idx] ?? 0,
      avg: series.avg,
      refLine: refTpm,
    }))
  }, [analysis, smartDateFmt])

  /** Label for the TPM reference line (break-even or P25). */
  const tpmRefLabel = useMemo(() => {
    if (!analysis) return 'P25'
    return analysis.charts.cost_curves.break_even_tpm ? 'Break-even' : 'P25'
  }, [analysis])

  const costCurveData = useMemo(() => {
    if (!analysis) return []
    const c = analysis.charts.cost_curves
    return c.baseline_tpm.map((x, idx) => ({
      baselineTpm: x,
      payg: c.payg_monthly[idx] ?? 0,
      hybrid: c.ptu_spill_monthly[idx] ?? 0,
      ptuUnits: c.ptu_units[idx] ?? 0,
    }))
  }, [analysis])

  /** Explicit X domain for the cost curve so reference lines always fall inside the visible area. */
  const costCurveDomain = useMemo<[number, number]>(() => {
    if (!analysis || costCurveData.length === 0) return [0, 100_000]
    const dataMax = Math.max(...costCurveData.map((d) => d.baselineTpm))
    const sliderTpm = analysis.charts.cost_curves.slider_baseline_tpm ?? 0
    const breakEvenTpm = analysis.charts.cost_curves.break_even_tpm ?? 0
    return [0, Math.max(dataMax, sliderTpm * 1.15, breakEvenTpm * 1.15)]
  }, [analysis, costCurveData])

  const breakEvenPtuUnits = useMemo(() => {
    if (!analysis?.charts.cost_curves.break_even_tpm || costCurveData.length === 0) return null
    const be = analysis.charts.cost_curves.break_even_tpm
    const closest = costCurveData.reduce((prev, curr) => {
      const prevDist = Math.abs(prev.baselineTpm - be)
      const currDist = Math.abs(curr.baselineTpm - be)
      return currDist < prevDist ? curr : prev
    })
    return closest.ptuUnits
  }, [analysis, costCurveData])

  // ── Drag-to-zoom helpers (shared across all time charts) ──
  const applyZoom = useCallback(<T extends { time: string }>(data: T[]): T[] => {
    if (!zoomDomain) return data
    return data.slice(zoomDomain[0], zoomDomain[1] + 1)
  }, [zoomDomain])

  const fullTimeLabels = useMemo(() => tokenChartData.map((d) => d.time), [tokenChartData])

  const handleZoomMouseDown = useCallback((e: { activeLabel?: string | number } | null) => {
    if (e?.activeLabel != null) setZoomLeft(String(e.activeLabel))
  }, [])

  const handleZoomMouseMove = useCallback((e: { activeLabel?: string | number } | null) => {
    if (zoomLeft && e?.activeLabel != null) setZoomRight(String(e.activeLabel))
  }, [zoomLeft])

  const handleZoomMouseUp = useCallback(() => {
    if (!zoomLeft || !zoomRight) {
      setZoomLeft(null)
      setZoomRight(null)
      return
    }
    const leftIdx = fullTimeLabels.indexOf(zoomLeft)
    const rightIdx = fullTimeLabels.indexOf(zoomRight)
    if (leftIdx < 0 || rightIdx < 0) {
      setZoomLeft(null)
      setZoomRight(null)
      return
    }
    const lo = Math.min(leftIdx, rightIdx)
    const hi = Math.max(leftIdx, rightIdx)
    if (hi - lo >= 1) {
      setZoomDomain([lo, hi])
    }
    setZoomLeft(null)
    setZoomRight(null)
  }, [zoomLeft, zoomRight, fullTimeLabels])

  const resetZoom = useCallback(() => setZoomDomain(null), [])

  const zoomChartProps = useMemo(() => ({
    onMouseDown: handleZoomMouseDown,
    onMouseMove: handleZoomMouseMove,
    onMouseUp: handleZoomMouseUp,
  }), [handleZoomMouseDown, handleZoomMouseMove, handleZoomMouseUp])

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
    if (!analysis || !analysis.cost_analysis.comparison.break_even_tpm || analysis.metrics.avg_tpm <= 0) {
      return null
    }

    const breakEven = analysis.cost_analysis.comparison.break_even_tpm
    const distancePct = ((analysis.metrics.avg_tpm - breakEven) / breakEven) * 100
    if (distancePct > 10) {
      return { tone: 'positive', text: `Your average TPM is ${distancePct.toFixed(0)}% above break-even.` }
    }
    if (distancePct >= -10) {
      return { tone: 'neutral', text: 'Your average TPM is near break-even (within ±10%).' }
    }
    return { tone: 'negative', text: `Your average TPM is ${Math.abs(distancePct).toFixed(0)}% below break-even.` }
  }, [analysis])

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

    // Break-even: find sustained TPM where PAYG = PTU On-Demand
    let breakEvenTpm: number | null = null
    const step = Math.max(100, calcPeakTpm / 500)
    let prevDiff = -Infinity
    for (let tpm = step; tpm <= calcPeakTpm * 3; tpm += step) {
      const paygCost = (tpm * MINUTES_PER_MONTH / 1_000_000) * blendedRate
      const effTpm = tpm * effectiveMult
      const ptu = Math.max(minPtu, Math.ceil(effTpm / model.tpmPerPtu / increment) * increment)
      const ptuCost = ptu * baseRate * regionMult * HOURS_PER_MONTH
      const diff = paygCost - ptuCost
      if (prevDiff < 0 && diff >= 0) {
        breakEvenTpm = tpm - step * (diff / (diff - prevDiff))
        break
      }
      prevDiff = diff
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

            <div className="form-grid advisor-form-grid">
              {mode === 'demo' ? (
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
              ) : (
                <>
                  <fieldset>
                    <legend>Subscription</legend>
                    <div className="deployments-box subscription-box">
                      {subscriptions.length === 0 && (
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
                      {deployments.map((deployment) => {
                        const meta = getDeploymentMetaParts(deployment)
                        return (
                          <label
                            key={deployment.name}
                            className={`radio-option deployment-option ${deploymentName === deployment.name ? 'is-selected' : ''}`}
                          >
                            <input
                              type="radio"
                              name="deployment"
                              checked={deploymentName === deployment.name}
                              onChange={() => setDeploymentName(deployment.name)}
                            />
                            <span className="deployment-text">
                              <span className="deployment-title">{formatDeploymentTitle(deployment)}</span>
                              <span className="deployment-meta deployment-labels">
                                <span className="deployment-chip">SKU: {meta.sku}</span>
                                <span className="deployment-chip">Capacity: {meta.capacity}</span>
                              </span>
                            </span>
                          </label>
                        )
                      })}
                    </div>
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
              <button className="primary run-btn" onClick={() => runAnalysis()} disabled={loading}>
                {loading ? (
                  <><span className="run-btn-spinner" /> Analyzing...</>
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
          <section className="results results-v2">
            <div className={`result-banner ${recommendationClass}`}>
              <div className="result-banner-top">
                <RecBadge recommendation={analysis.recommendation} />
                <p className="confidence">Confidence score: {(analysis.confidence * 100).toFixed(1)}%</p>
              </div>
              <h2 className="result-banner-title">{recommendationTitle}</h2>
              <p className="result-banner-summary">{recommendationSummary}</p>
            </div>

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
              <article className={`glance-card${analysis.metrics.throttling_rate_pct > 5 ? ' glance-alert' : ''}`}>
                <span className="glance-label">Rate-Limit Events <InfoTip text="Percent of requests receiving HTTP 429 rate-limit responses." /></span>
                <span className="glance-value">{analysis.metrics.throttling_rate_pct.toFixed(2)}%</span>
                <span className="glance-sub">HTTP 429 rate</span>
              </article>
            </div>

            <h3 className="section-title section-title-with-icon stagger-3"><img src={RESULTS_ICON_URLS.evidence} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-3">Evidence</span></h3>
            {zoomDomain && (
              <div className="zoom-indicator stagger-3">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="4.5"/><path d="M13 13l-3.5-3.5"/><path d="M6 4v4M4 6h4"/></svg>
                <span>Zoomed to {zoomDomain[1] - zoomDomain[0] + 1} of {tokenChartData.length} points</span>
                <button className="zoom-reset-btn" onClick={resetZoom}>Reset Zoom</button>
              </div>
            )}
            {!zoomDomain && (
              <p className="zoom-hint stagger-3">Drag across any chart to zoom in</p>
            )}
            <div className="chart-grid chart-grid-v2 stagger-4">
              <article className={`chart-card${expandedChart === 'tokens' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Token Volume Over Time" tip="Hover to inspect exact values by interval." onExpand={() => setExpandedChart(expandedChart === 'tokens' ? null : 'tokens')} />
                {tokenChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <ResponsiveContainer width="100%" height={expandedChart === 'tokens' ? window.innerHeight - 140 : 240}>
                  <ComposedChart data={applyZoom(tokenChartData)} {...zoomChartProps}>
                    <defs>
                      <linearGradient id="gradPrompt" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={CHART_COLORS.primary} stopOpacity={0.24} />
                        <stop offset="100%" stopColor={CHART_COLORS.primary} stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="gradCompletion" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={CHART_COLORS.secondary} stopOpacity={0.22} />
                        <stop offset="100%" stopColor={CHART_COLORS.secondary} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(120,140,170,0.12)" />
                    <XAxis dataKey="time" tick={{ fill: '#8f9ec4', fontSize: 11 }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatWithCommas(Number(v))} label={{ value: 'Tokens', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={{ stroke: CHART_COLORS.primary, strokeWidth: 1 }} formatter={(value) => (typeof value === 'number' ? formatWithCommas(value) : String(value ?? ''))} />
                    <Legend content={<StaticLegend items={[{ label: 'Prompt Tokens', color: CHART_COLORS.primary }, { label: 'Completion Tokens', color: CHART_COLORS.secondary }]} />} />
                    <Area type="monotone" dataKey="prompt" fill="url(#gradPrompt)" stroke="none" legendType="none" />
                    <Area type="monotone" dataKey="completion" fill="url(#gradCompletion)" stroke="none" legendType="none" />
                    <Line type="monotone" dataKey="prompt" stroke={CHART_COLORS.primary} dot={false} activeDot={{ r: 4 }} name="Prompt Tokens" legendType="none" />
                    <Line type="monotone" dataKey="completion" stroke={CHART_COLORS.secondary} dot={false} activeDot={{ r: 4 }} name="Completion Tokens" legendType="none" />
                    {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
                  </ComposedChart>
                </ResponsiveContainer>
                )}
              </article>

              <article className={`chart-card${expandedChart === 'requests' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Request Outcomes" tip="Hover to inspect exact values by interval." onExpand={() => setExpandedChart(expandedChart === 'requests' ? null : 'requests')} />
                {requestsChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <ResponsiveContainer width="100%" height={expandedChart === 'requests' ? window.innerHeight - 140 : 240}>
                  <ComposedChart data={applyZoom(requestsChartData)} {...zoomChartProps}>
                    <defs>
                      <linearGradient id="gradSuccess" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={CHART_COLORS.success} stopOpacity={0.2} />
                        <stop offset="100%" stopColor={CHART_COLORS.success} stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="gradThrottled" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={CHART_COLORS.danger} stopOpacity={0.2} />
                        <stop offset="100%" stopColor={CHART_COLORS.danger} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(120,140,170,0.12)" />
                    <XAxis dataKey="time" tick={{ fill: '#8f9ec4', fontSize: 11 }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatWithCommas(Number(v))} label={{ value: 'Requests', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={{ stroke: CHART_COLORS.primary, strokeWidth: 1 }} formatter={(value) => (typeof value === 'number' ? formatWithCommas(value) : String(value ?? ''))} />
                    <Legend content={<StaticLegend items={[{ label: 'Successful', color: CHART_COLORS.success }, { label: 'HTTP 429', color: CHART_COLORS.danger }]} />} />
                    <Area type="monotone" dataKey="successful" fill="url(#gradSuccess)" stroke="none" legendType="none" />
                    <Area type="monotone" dataKey="throttled" fill="url(#gradThrottled)" stroke="none" legendType="none" />
                    <Line type="monotone" dataKey="successful" stroke={CHART_COLORS.success} dot={false} activeDot={{ r: 4 }} name="Successful" legendType="none" />
                    <Line type="monotone" dataKey="throttled" stroke={CHART_COLORS.danger} dot={false} activeDot={{ r: 4 }} name="HTTP 429" legendType="none" />
                    {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
                  </ComposedChart>
                </ResponsiveContainer>
                )}
              </article>

              <article className={`chart-card${expandedChart === 'latency' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Response Time Stability" tip="Hover to inspect exact latency levels by interval." onExpand={() => setExpandedChart(expandedChart === 'latency' ? null : 'latency')} />
                {latencyChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <ResponsiveContainer width="100%" height={expandedChart === 'latency' ? window.innerHeight - 140 : 240}>
                  <LineChart data={applyZoom(latencyChartData)} {...zoomChartProps}>
                    <CartesianGrid stroke="rgba(120,140,170,0.2)" />
                    <XAxis dataKey="time" tick={{ fill: '#8f9ec4', fontSize: 11 }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatWithCommas(Number(v))} label={{ value: 'ms', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={{ stroke: CHART_COLORS.primary, strokeWidth: 1 }} formatter={(value) => (typeof value === 'number' ? `${formatWithCommas(value)} ms` : String(value ?? ''))} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="p50" stroke={CHART_COLORS.primary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} name="P50" connectNulls />
                    <Line type="monotone" dataKey="p95" stroke={CHART_COLORS.secondary} strokeWidth={2} dot={false} activeDot={{ r: 4 }} name="P95" connectNulls />
                    <Line type="monotone" dataKey="p99" stroke={CHART_COLORS.warning} strokeWidth={2} dot={false} activeDot={{ r: 4 }} name="P99" connectNulls />
                    {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
                  </LineChart>
                </ResponsiveContainer>
                )}
              </article>

              <article className={`chart-card${expandedChart === 'throttle' ? ' is-chart-expanded' : ''}`}>
                <WidgetHeader title="Rate-Limit Events (429)" tip="Hover to inspect exact values by interval." onExpand={() => setExpandedChart(expandedChart === 'throttle' ? null : 'throttle')} />
                {throttleChartData.length === 0 ? <ChartEmpty height={240} /> : (
                <ResponsiveContainer width="100%" height={expandedChart === 'throttle' ? window.innerHeight - 140 : 240}>
                  <LineChart data={applyZoom(throttleChartData)} {...zoomChartProps}>
                    <CartesianGrid stroke="rgba(120,140,170,0.2)" />
                    <XAxis dataKey="time" tick={{ fill: '#8f9ec4', fontSize: 11 }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatWithCommas(Number(v))} label={{ value: '429 Events', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={{ stroke: CHART_COLORS.primary, strokeWidth: 1 }} formatter={(value) => (typeof value === 'number' ? formatWithCommas(value) : String(value ?? ''))} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="throttled" stroke={CHART_COLORS.warning} dot={false} activeDot={{ r: 4 }} name="Rate Limited" />
                    {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
                  </LineChart>
                </ResponsiveContainer>
                )}
              </article>
            </div>

            <article className={`chart-card wide-card${expandedChart === 'tpm' ? ' is-chart-expanded' : ''}`}>
              <WidgetHeader title={`Throughput Band (TPM vs Avg/${tpmRefLabel})`} tip={`Shows raw TPM against average and ${tpmRefLabel} throughput levels.`} onExpand={() => setExpandedChart(expandedChart === 'tpm' ? null : 'tpm')} />
              {tpmChartData.length === 0 ? <ChartEmpty height={280} /> : (
              <ResponsiveContainer width="100%" height={expandedChart === 'tpm' ? window.innerHeight - 140 : 280}>
                <ComposedChart data={applyZoom(tpmChartData)} {...zoomChartProps}>
                  <defs>
                    <linearGradient id="gradTpm" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART_COLORS.primary} stopOpacity={0.18} />
                      <stop offset="100%" stopColor={CHART_COLORS.primary} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(120,140,170,0.12)" />
                  <XAxis dataKey="time" tick={{ fill: '#8f9ec4', fontSize: 11 }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatWithCommas(Number(v))} label={{ value: 'TPM', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                  <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={{ stroke: CHART_COLORS.primary, strokeWidth: 1 }} formatter={(value) => (typeof value === 'number' ? formatWithCommas(value) : String(value ?? ''))} />
                  <Legend content={<StaticLegend items={[{ label: 'TPM', color: CHART_COLORS.primary }, { label: 'Avg', color: CHART_COLORS.success }, { label: tpmRefLabel, color: CHART_COLORS.warning }]} />} />
                  <Area type="monotone" dataKey="tpm" fill="url(#gradTpm)" stroke="none" legendType="none" />
                  <Line type="monotone" dataKey="tpm" stroke={CHART_COLORS.primary} dot={false} activeDot={{ r: 4 }} name="TPM" legendType="none" />
                  <Line type="monotone" dataKey="avg" stroke={CHART_COLORS.success} dot={false} activeDot={{ r: 4 }} name="Avg" legendType="none" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="refLine" stroke={CHART_COLORS.warning} dot={false} activeDot={{ r: 4 }} name={tpmRefLabel} legendType="none" strokeDasharray="5 5" />
                  {zoomLeft && zoomRight && <ReferenceArea x1={zoomLeft} x2={zoomRight} strokeOpacity={0.3} fill="rgba(124,140,255,0.15)" />}
                </ComposedChart>
              </ResponsiveContainer>
              )}
            </article>

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

            <h3 className="section-title section-title-with-icon stagger-6"><img src={RESULTS_ICON_URLS.financial} alt="" className="section-title-icon" loading="lazy" decoding="async" /><span className="stagger-6">Financial Decision</span></h3>
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

                <div className="assumption-status" aria-live="polite">
                  {loading ? 'Updating calculations…' : 'Changes apply automatically after each adjustment'}
                </div>
              </div>
            </article>

            <details className="calculation-details" open>
              <summary>
                <h3 className="section-title calc-section-title">Calculation Details</h3>
              </summary>
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
              <WidgetHeader title="Break-even Curve (PAYG vs PTU + Spillover)" tip="Hover to inspect monthly PAYG vs PTU + spillover cost points by baseline TPM." onExpand={() => setExpandedChart(expandedChart === 'cost' ? null : 'cost')} />
              <div className="chart-inline-legend">
                <StaticLegend items={[{ label: 'PAYG Cost', color: CHART_COLORS.primary }, { label: 'Hybrid Cost', color: CHART_COLORS.success }]} />
              </div>
              {costCurveData.length === 0 ? <ChartEmpty height={300} /> : (<>
              <ResponsiveContainer width="100%" height={expandedChart === 'cost' ? window.innerHeight - 140 : 300}>
                <LineChart data={costCurveData} margin={{ top: 10, right: 12, left: 8, bottom: 18 }}>
                  <CartesianGrid stroke="rgba(120,140,170,0.2)" />
                  <XAxis dataKey="baselineTpm" type="number" domain={costCurveDomain} tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatNumber(Number(v))} tickLine={false} axisLine={false} label={{ value: 'Baseline TPM', position: 'insideBottom', fill: '#8f9ec4', fontSize: 10, dy: 10 }} />
                  <YAxis tick={{ fill: '#8f9ec4', fontSize: 10 }} tickFormatter={(v) => formatCurrency(Number(v))} label={{ value: '$/month', angle: -90, position: 'insideLeft', fill: '#8f9ec4', fontSize: 10, dx: -4 }} />
                  <Tooltip content={<CostCurveTooltip />} cursor={{ stroke: '#7c8cff', strokeWidth: 1 }} />
                  {analysis.charts.cost_curves.break_even_tpm && (
                    <ReferenceLine
                      x={analysis.charts.cost_curves.break_even_tpm}
                      stroke="#FFB900"
                      strokeDasharray="6 4"
                      strokeWidth={2}
                      label={{
                        value: `Break-even ${formatNumber(analysis.charts.cost_curves.break_even_tpm)}${breakEvenPtuUnits ? ` · ${breakEvenPtuUnits} PTU` : ''}`,
                        position: 'insideTopRight',
                        fill: '#FFB900',
                        fontSize: 12,
                      }}
                    />
                  )}
                  <ReferenceLine
                    x={analysis.charts.cost_curves.slider_baseline_tpm}
                    stroke="#00d4aa"
                    strokeWidth={2}
                    strokeDasharray="4 2"
                    label={{
                      value: `Baseline ${formatNumber(analysis.charts.cost_curves.slider_baseline_tpm)} · ${analysis.cost_analysis.hybrid.baseline_ptu} PTU`,
                      position: 'insideTopLeft',
                      fill: '#00d4aa',
                      fontSize: 12,
                    }}
                  />
                  <Line type="monotone" dataKey="payg" stroke="#0078D4" dot={false} activeDot={{ r: 4 }} name="PAYG" strokeDasharray="5 4" />
                  <Line type="monotone" dataKey="hybrid" stroke="#00d4aa" dot={false} activeDot={{ r: 4 }} name="PTU + Spillover" />
                  <ReferenceDot
                    x={analysis.charts.cost_curves.slider_baseline_tpm}
                    y={analysis.charts.cost_curves.payg_at_slider}
                    r={4}
                    fill="#0078D4"
                    stroke="#dce7ff"
                    strokeWidth={1}
                  />
                  <ReferenceDot
                    x={analysis.charts.cost_curves.slider_baseline_tpm}
                    y={analysis.charts.cost_curves.hybrid_at_slider}
                    r={4}
                    fill="#00d4aa"
                    stroke="#dce7ff"
                    strokeWidth={1}
                  />
                </LineChart>
              </ResponsiveContainer>
              {breakEvenStatus && (
                <div className={`break-even-callout tone-${breakEvenStatus.tone}`}>
                  {breakEvenStatus.text}
                </div>
              )}
              </>)}
            </article>

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
                <p>{formatCurrency(Math.abs(analysis.cost_analysis.comparison.savings))}</p>
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

            <button className="secondary stagger-8" onClick={() => { setExpandedChart(null); setAnalysis(null) }}>
              {"\u2190"} Back to Setup
            </button>
          </section>
        )}
      </div>
    </div>
  )
}

export default App
