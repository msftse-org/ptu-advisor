import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ExportReport } from './ExportReport'
import type { AnalysisResponse, ConsolidationSummary } from './types'

const { exportTokenSnapshotMock } = vi.hoisted(() => ({
  exportTokenSnapshotMock: vi.fn(),
}))

vi.mock('./api', () => ({
  api: { exportTokenSnapshot: exportTokenSnapshotMock },
}))

/* ── Shared mock data ── */

function buildAnalysis(overrides: Partial<AnalysisResponse> = {}): AnalysisResponse {
  return {
    recommendation: 'ptu_recommended',
    confidence: 0.82,
    summary: 'Steady high throughput with measurable rate-limiting.',
    explanation: 'Your workload is stable and high-volume.',
    what_would_change: 'If traffic drops below 38K sustained TPM.',
    data_quality: 'Good',
    analysis_period: 'Feb 24 – Mar 10 (14 days)',
    dimensions: [
      { name: 'Workload Shape', score: 'POSITIVE', confidence: 0.91, summary: 'Stable workload.', explanation: '', key_metrics: {}, is_positive: true },
      { name: 'Capacity Pressure', score: 'POSITIVE', confidence: 0.85, summary: 'High throttling.', explanation: '', key_metrics: {}, is_positive: true },
      { name: 'Latency Sensitivity', score: 'NEUTRAL', confidence: 0.72, summary: 'Average latency.', explanation: '', key_metrics: {}, is_positive: false },
      { name: 'Load Predictability', score: 'INSUFFICIENT', confidence: 0.3, summary: 'Not enough data.', explanation: '', key_metrics: {}, is_positive: false },
    ],
    metrics: {
      deployment_name: 'gpt-4o-2024-11-20',
      model_name: 'gpt-4o',
      avg_tpm: 42300,
      peak_tpm: 78500,
      throttling_rate_pct: 8.2,
      total_requests: 250000,
      throttled_requests: 8540,
      successful_requests: 241460,
      total_tokens: 99000000,
      total_tokens_millions: 99,
      lookback_days: 14,
      latency: { p50: 210, p95: 320, p99: 580 },
      utilization: {
        peak_to_average_ratio: 1.86,
        sustained_utilization_rate: 72,
        active_hours_percentage: 94,
        business_hours_concentration: 64,
        weekend_vs_weekday_ratio: 0.58,
      },
    },
    charts: {
      tokens: { timestamps: [], prompt: [], completion: [], total: [] },
      requests: { timestamps: [], successful: [], throttled: [], total: [] },
      daily_cost: { dates: [], input_cost: [], output_cost: [], total_cost: [], avg_daily_cost: 0, ptu_daily_cost: 0 },
      tpm: { timestamps: [], values: [], avg: 42300, p25: 30000, p95: 78500 },
      throttling: { timestamps: [], values: [] },
      prompt_cache: {
        timestamps: [], match_rate_pct: [], prompt_tokens: [], cached_prompt_tokens: [], active_prompt_tokens: [], source: 'observed' as const,
      },
      cost_curves: {
        sustained_tpm: [], payg_monthly: [], ptu_spill_monthly: [],
        break_even_tpm: 38000, break_even_reason: 'exists' as const, ptu_capacity_tpm: 37500, avg_tpm: 42300, selected_ptu: 15, payg_at_avg: 12450, hybrid_at_avg: 8200,
      },
    },
    cost_analysis: {
      pricing: {
        focus_topic: 'Cost Reduction',
        reservation_type: 'Monthly',
        reservation_discount_pct: 64,
        payg_blended_rate_per_million: 4.75,
        payg_input_rate_per_million: 2.50,
        payg_cached_input_rate_per_million: 1.25,
        cached_input_pricing_source: 'fallback' as const,
        payg_output_rate_per_million: 10.00,
        output_ratio: 0.3,
        ptu_hourly_rate: 1,
        ptu_capacity_per_unit: 2500,
        ptu_minimum: 15,
        ptu_increment: 5,
        region: 'eastus',
        region_display_name: 'East US',
        region_multiplier: 1.0,
        deployment_type: 'regional' as const,
        deployment_type_label: 'Regional',
        pricing_source: 'fallback' as const,
        pricing_as_of: '2026-03-28T00:00:00Z',
        pricing_currency: 'USD',
      },
      payg: { monthly_tokens: 99000000, payg_base: 10000, throttle_impact: 2450, payg_total: 12450 },
      hybrid: {
        baseline_percentile: 65,
        baseline_label: '50 PTU',
        baseline_tpm: 42300,
        baseline_ptu: 50,
        default_baseline_ptu: 50,
        max_viable_baseline_ptu: 75,
        max_baseline_ptu: 200,
        ptu_capacity_tpm: 125000,
        avg_spillover_tpm: 800,
        spillover_tokens_monthly: 34560000,
        spillover_cost: 200,
        ptu_baseline_cost: 8000,
        hybrid_total: 8200,
        spillover_pct: 2,
      },
      full_ptu: { ptu_needed_full: 60, ptu_monthly_full: 22000, ptu_committed_cost: 8000 },
      comparison: { savings: 4250, savings_pct: 34, break_even_tpm: 38000, cheaper_strategy: 'PTU + Spillover' },
      commitment_safety: { savings_margin_pct: 34, spillover_pct: 2, capacity_coverage_pct: 98, safety_verdict: 'safe' as const },
      cache_impact: {
        applied: true,
        source: 'observed' as const,
        quality: 'good' as const,
        coverage_pct: 100,
        no_cache_normalized_avg_tpm: 45000,
        cache_adjusted_normalized_avg_tpm: 42300,
        normalized_tpm_reduction_pct: 6,
        no_cache_recommended_ptu: 50,
        cache_aware_recommended_ptu: 50,
        ptu_avoided: 0,
        no_cache_payg_monthly: 13200,
        cache_aware_payg_monthly: 12450,
        payg_cache_savings: 750,
        fixed_ptu_cost_changed: false,
        calculation_note: 'Observed prompt-cache usage is included in capacity and cost estimates.',
      },
      formula_blocks: { payg: '', hybrid: '' },
    },
    insights: { break_even_message: '', focus_topic: 'Cost Reduction', analysis_notes: [] },
    ...overrides,
  }
}

function expectDecorativeRecommendationIcon(container: Element, kind: string) {
  const icon = container.querySelector(`svg[data-recommendation-icon="${kind}"]`)
  expect(icon).not.toBeNull()
  expect(icon).toHaveAttribute('aria-hidden', 'true')
  expect(icon).toHaveAttribute('focusable', 'false')
  expect(icon).toHaveAttribute('fill', 'none')
  expect(icon).toHaveAttribute('stroke', 'currentColor')
}

/* ────────────────────────────────────────────────────
   Dropdown button
   ──────────────────────────────────────────────────── */

describe('Export dropdown', () => {
  it('renders the Export Report button with the shared SVG icon language', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    const button = screen.getByRole('button', { name: 'Export Report' })
    expect(button).toBeInTheDocument()
    expect(button.querySelector('svg')).not.toBeNull()
    expect(button).not.toHaveTextContent('▾')
  })

  it('shows menu items on click', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))

    expect(screen.getByText('Download PDF')).toBeInTheDocument()
    expect(screen.getByText('Download HTML')).toBeInTheDocument()
  })

  it('toggles dropdown open/closed', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    const btn = screen.getByRole('button', { name: 'Export Report' })

    fireEvent.click(btn)
    expect(screen.getByText('Download PDF')).toBeInTheDocument()

    fireEvent.click(btn)
    expect(screen.queryByText('Download PDF')).not.toBeInTheDocument()
  })

  it('has proper aria attributes', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    const btn = screen.getByRole('button', { name: 'Export Report' })

    expect(btn).toHaveAttribute('aria-haspopup', 'true')
    expect(btn).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'true')
  })
})

/* ────────────────────────────────────────────────────
   Report content — all 6 sections
   ──────────────────────────────────────────────────── */

describe('Report content sections', () => {
  it('renders report header with deployment info', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('PTU Advisor — Deployment Assessment')).toBeInTheDocument()
    expect(root.getByText(/gpt-4o-2024-11-20/)).toBeInTheDocument()
    expect(root.getByText('Model:')).toBeInTheDocument()
    expect(root.getByText(/Feb 24 – Mar 10/)).toBeInTheDocument()
  })

  it('renders recommendation banner with correct label and confidence', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('PTU Recommended')).toBeInTheDocument()
    expect(root.getByText(/82\.0%/)).toBeInTheDocument()
    expect(root.getByText('Steady high throughput with measurable rate-limiting.')).toBeInTheDocument()
    const banner = report.querySelector('.report-rec-banner')!
    expectDecorativeRecommendationIcon(banner, 'recommended')
    expect(banner).not.toHaveTextContent('✅')
  })

  it('renders all 6 key evidence metrics', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('Average TPM')).toBeInTheDocument()
    expect(root.getByText('42,300')).toBeInTheDocument()
    expect(root.getByText('Peak TPM')).toBeInTheDocument()
    expect(root.getByText('78,500')).toBeInTheDocument()
    expect(root.getByText('Throttle Rate')).toBeInTheDocument()
    expect(root.getByText('8.2%')).toBeInTheDocument()
    expect(root.getByText('P95 Latency')).toBeInTheDocument()
    expect(root.getByText('320 ms')).toBeInTheDocument()
    expect(root.getByText('Active Hours')).toBeInTheDocument()
    expect(root.getByText('94.0%')).toBeInTheDocument()
    expect(root.getByText(/1\.86x/)).toBeInTheDocument()
  })

  it('renders cost comparison with PAYG, hybrid, savings', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/\$12,450.*month/)).toBeInTheDocument()
    expect(root.getByText(/\$8,200.*month/)).toBeInTheDocument()
    expect(root.getByText(/\$4,250/)).toBeInTheDocument()
    expect(root.getByText(/34\.0%/)).toBeInTheDocument()
    expect(root.getByText('38,000')).toBeInTheDocument()
  })

  it('renders pricing assumptions line', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Monthly.*East US.*1x.*Regional.*50 PTU/)).toBeInTheDocument()
  })

  it('renders explanation and non-insufficient dimensions', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('Your workload is stable and high-volume.')).toBeInTheDocument()
    expect(root.getByText(/Workload Shape/)).toBeInTheDocument()
    expect(root.getByText(/Capacity Pressure/)).toBeInTheDocument()
    expect(root.getByText(/Latency Sensitivity/)).toBeInTheDocument()
    // INSUFFICIENT dimension should NOT appear
    expect(root.queryByText(/Load Predictability/)).not.toBeInTheDocument()
  })

  it('renders what would change section', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('If traffic drops below 38K sustained TPM.')).toBeInTheDocument()
  })

  it('renders PTU_RECOMMENDED next steps', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Reserve 50 PTU \(Regional, Monthly\)/)).toBeInTheDocument()
    expect(root.getByText(/Monitor spillover/)).toBeInTheDocument()
    expect(root.getByText(/Re-evaluate in 30 days/)).toBeInTheDocument()
  })

  it('renders footer disclaimer', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/not a contractual commitment/i)).toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   Recommendation variants
   ──────────────────────────────────────────────────── */

describe('Recommendation variant banners', () => {
  it('shows green banner for ptu_recommended', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'ptu_recommended' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--green')
    expectDecorativeRecommendationIcon(banner, 'recommended')
  })

  it('shows amber banner for borderline', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'borderline' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--amber')
    expect(banner.textContent).toContain('Borderline')
    expectDecorativeRecommendationIcon(banner, 'borderline')
  })

  it('shows blue banner for ptu_not_recommended', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'ptu_not_recommended' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--blue')
    expect(banner.textContent).toContain('Stay on PAYG')
    expectDecorativeRecommendationIcon(banner, 'info')
  })

  it('shows a readable insufficient-data banner with the fallback SVG language', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'insufficient_data' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--blue')
    expect(banner).toHaveTextContent('Insufficient Data')
    expectDecorativeRecommendationIcon(banner, 'insufficient')
  })

  it('renders borderline next steps', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'borderline' })} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/1-week load test/)).toBeInTheDocument()
  })

  it('renders ptu_not_recommended next steps', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'ptu_not_recommended' })} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Stay on PAYG — current usage/)).toBeInTheDocument()
    expect(root.getByText(/cost alerts/)).toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   Zoom-aware header
   ──────────────────────────────────────────────────── */

describe('Zoom-aware export', () => {
  it('does NOT show "(zoomed)" or full lookback line when not zoomed', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Feb 24 – Mar 10/)).toBeInTheDocument()
    expect(root.queryByText(/\(zoomed\)/)).not.toBeInTheDocument()
    expect(root.queryByText(/Full Lookback/)).not.toBeInTheDocument()
  })

  it('shows "(zoomed)" and full lookback when zoomed', () => {
    const zoomed = buildAnalysis({ analysis_period: 'Mar 3 – Mar 7 (4 days)' })
    const base = buildAnalysis({ analysis_period: 'Feb 24 – Mar 10 (14 days)' })

    render(<ExportReport analysis={zoomed} baseAnalysis={base} isZoomed={true} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Mar 3 – Mar 7.*\(zoomed\)/)).toBeInTheDocument()
    expect(root.getByText(/Feb 24 – Mar 10 \(14 days\)/)).toBeInTheDocument()
  })

  it('shows "(zoomed)" without full lookback if baseAnalysis is null', () => {
    const zoomed = buildAnalysis({ analysis_period: 'Mar 3 – Mar 7 (4 days)' })

    render(<ExportReport analysis={zoomed} baseAnalysis={null} isZoomed={true} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/Mar 3 – Mar 7.*\(zoomed\)/)).toBeInTheDocument()
    expect(root.queryByText(/Full Lookback/)).not.toBeInTheDocument()
  })
})

describe('Token snapshot export', () => {
  afterEach(() => {
    exportTokenSnapshotMock.mockReset()
  })

  it('exports cache-aware snapshot evidence with the active analysis assumptions', async () => {
    const createObjectURL = vi.fn(() => 'blob:snapshot')
    const revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL
    exportTokenSnapshotMock.mockResolvedValue({ series: [] })

    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        tokenSnapshotContext={{
          mode: 'demo',
          focusTopic: 'Cost Reduction',
          days: 14,
          interval: 'PT1M',
          cache_mode: 'override',
          cache_match_rate_override_pct: 62,
        }}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
    fireEvent.click(screen.getByRole('button', { name: 'Download GBB Token Snapshot (JSON)' }))

    await waitFor(() => {
      expect(exportTokenSnapshotMock).toHaveBeenCalledWith({
        mode: 'demo',
        focus_topic: 'Cost Reduction',
        days: 14,
        interval: 'PT1M',
        cache_mode: 'override',
        cache_match_rate_override_pct: 62,
      })
    })
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(anchorClick).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:snapshot')

    anchorClick.mockRestore()
  })
})

/* ────────────────────────────────────────────────────
   Export actions
   ──────────────────────────────────────────────────── */

describe('Export actions', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('serializes the authored recommendation SVG into the self-contained HTML download', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    const NativeBlob = global.Blob
    let serializedHtml = ''
    class CapturingBlob extends NativeBlob {
      constructor(parts: BlobPart[] = [], options?: BlobPropertyBag) {
        super(parts, options)
        serializedHtml = parts.filter((part): part is string => typeof part === 'string').join('')
      }
    }
    global.Blob = CapturingBlob
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL

    try {
      render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

      fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
      fireEvent.click(screen.getByText('Download HTML'))

      expect(createObjectURL).toHaveBeenCalledTimes(1)
      expect(serializedHtml).toContain('<svg')
      expect(serializedHtml).toContain('data-recommendation-icon="recommended"')
      expect(serializedHtml).toContain('aria-hidden="true"')
      expect(serializedHtml).not.toContain('✅')
      expect(serializedHtml).not.toMatch(/<script\b/i)
      // revokeObjectURL is deferred via setTimeout
      expect(revokeObjectURL).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1000)
      expect(revokeObjectURL).toHaveBeenCalledTimes(1)
    } finally {
      global.Blob = NativeBlob
    }
  })

  it('triggers print window on "Download PDF" click', () => {
    const mockPrint = vi.fn()
    const mockWrite = vi.fn()
    const mockOpen = vi.fn()
    const mockClose = vi.fn()
    const mockFocus = vi.fn()

    vi.spyOn(window, 'open').mockReturnValue({
      document: { open: mockOpen, write: mockWrite, close: mockClose },
      focus: mockFocus,
      print: mockPrint,
    } as unknown as Window)

    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
    fireEvent.click(screen.getByText('Download PDF'))

    expect(window.open).toHaveBeenCalledWith('', '_blank', 'width=900,height=700')
    expect(mockOpen).toHaveBeenCalled()
    expect(mockWrite).toHaveBeenCalledTimes(1)
    expect(mockWrite.mock.calls[0][0]).toContain('PTU Advisor')
    expect(mockClose).toHaveBeenCalled()

    // focus + print are deferred via setTimeout
    expect(mockFocus).not.toHaveBeenCalled()
    expect(mockPrint).not.toHaveBeenCalled()
    vi.advanceTimersByTime(400)
    expect(mockFocus).toHaveBeenCalled()
    expect(mockPrint).toHaveBeenCalled()

    vi.restoreAllMocks()
  })

  it('closes dropdown after action', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL

    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
    expect(screen.getByText('Download HTML')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Download HTML'))
    expect(screen.queryByText('Download HTML')).not.toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   Edge case: break_even_tpm is null
   ──────────────────────────────────────────────────── */

describe('Edge cases', () => {
  it('omits break-even row when break_even_tpm is null', () => {
    const analysis = buildAnalysis()
    analysis.cost_analysis.comparison.break_even_tpm = null

    render(<ExportReport analysis={analysis} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.queryByText('Break-even TPM')).not.toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   Consolidation export
   ──────────────────────────────────────────────────── */

function buildConsolidationSummary(): ConsolidationSummary {
  return {
    deployment_count: 3,
    model_name: 'gpt-4o',
    deployment_type: 'Standard',
    individual_deployments: [
      { name: 'gpt-4o-customer-chat', avg_tpm: 18000, peak_tpm: 35000, throttling_rate_pct: 6.1, total_requests: 120000, latency_p50: 180, latency_p95: 290, payg_monthly_cost: 5200 },
      { name: 'gpt-4o-doc-processing', avg_tpm: 14000, peak_tpm: 28000, throttling_rate_pct: 3.5, total_requests: 80000, latency_p50: 200, latency_p95: 350, payg_monthly_cost: 3800 },
      { name: 'gpt-4o-batch-analytics', avg_tpm: 10300, peak_tpm: 15500, throttling_rate_pct: 1.2, total_requests: 50000, latency_p50: 250, latency_p95: 400, payg_monthly_cost: 3450 },
    ],
    combined_avg_tpm: 42300,
    combined_peak_tpm: 78500,
    combined_throttling_rate_pct: 3.9,
    individual_payg_total: 12450,
    consolidated_hybrid_cost: 8200,
    savings: 4250,
    savings_pct: 34.1,
    warnings: [],
    all_on_ptu: false,
  }
}

describe('Consolidation export — report content', () => {
  it('renders consolidation header and mode label', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('PTU Advisor — Consolidation Assessment')).toBeInTheDocument()
    expect(root.getByText(/Consolidation \(3 deployments\)/)).toBeInTheDocument()
    expect(root.getByText(/gpt-4o-customer-chat, gpt-4o-doc-processing, gpt-4o-batch-analytics/)).toBeInTheDocument()
  })

  it('renders consolidation summary table with all deployments', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('2. Consolidation Summary')).toBeInTheDocument()
    expect(root.getByText('gpt-4o-customer-chat')).toBeInTheDocument()
    expect(root.getByText('gpt-4o-doc-processing')).toBeInTheDocument()
    expect(root.getByText('gpt-4o-batch-analytics')).toBeInTheDocument()
  })

  it('renders combined totals row in consolidation table', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const totalRow = document.querySelector('.consolidation-total-row')!
    expect(totalRow).toBeInTheDocument()
    expect(totalRow.textContent).toContain('Combined')
    expect(totalRow.textContent).toContain('42,300')
    expect(totalRow.textContent).toContain('78,500')
  })

  it('renders consolidation savings summary text', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/saves an estimated \$4,250\/month \(34\.1%\)/)).toBeInTheDocument()
  })

  it('renders negative savings message when consolidation does not save', () => {
    const summary = buildConsolidationSummary()
    summary.savings = -500
    summary.savings_pct = -4.0

    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText(/does not save money/)).toBeInTheDocument()
    expect(root.getByText(/\$500\/month/)).toBeInTheDocument()
  })

  it('shifts section numbers when consolidation is present', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    // Section numbering: 1. Recommendation, 2. Consolidation Summary, 3. Key Evidence, 4. Cost Comparison, etc.
    expect(root.getByText('1. Recommendation')).toBeInTheDocument()
    expect(root.getByText('2. Consolidation Summary')).toBeInTheDocument()
    expect(root.getByText(/3\. Key Evidence/)).toBeInTheDocument()
    expect(root.getByText(/4\. Cost Comparison/)).toBeInTheDocument()
    expect(root.getByText(/5\. Why This Recommendation/)).toBeInTheDocument()
    expect(root.getByText(/6\. What Would Change This/)).toBeInTheDocument()
    expect(root.getByText(/7\. Recommended Next Steps/)).toBeInTheDocument()
  })

  it('uses standard section numbers without consolidation', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('1. Recommendation')).toBeInTheDocument()
    expect(root.queryByText('2. Consolidation Summary')).not.toBeInTheDocument()
    expect(root.getByText(/2\. Key Evidence/)).toBeInTheDocument()
    expect(root.getByText(/3\. Cost Comparison/)).toBeInTheDocument()
  })

  it('renders consolidation cost comparison (individual PAYG vs consolidated hybrid)', () => {
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    const report = document.getElementById('export-report-root')!
    const root = within(report)

    expect(root.getByText('Sum of Individual PAYG')).toBeInTheDocument()
    expect(root.getByText('Consolidated PTU + Spillover')).toBeInTheDocument()
  })
})

describe('Consolidation export — filename and HTML title', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('uses consolidation filename prefix on HTML download', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL

    // Capture the <a> element to verify filename
    const appendSpy = vi.spyOn(document.body, 'appendChild')

    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={buildConsolidationSummary()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
    fireEvent.click(screen.getByText('Download HTML'))

    const anchor = appendSpy.mock.calls.find(
      (call) => call[0] instanceof HTMLAnchorElement,
    )?.[0] as HTMLAnchorElement | undefined

    expect(anchor).toBeDefined()
    expect(anchor!.download).toContain('ptu-consolidation')
    expect(anchor!.download).toContain('gpt-4o')
    expect(anchor!.download).toContain('3deps')
    expect(anchor!.download).not.toContain('ptu-assessment')

    appendSpy.mockRestore()
    vi.advanceTimersByTime(1000)
  })

  it('uses standard filename for single-deployment HTML download', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL

    const appendSpy = vi.spyOn(document.body, 'appendChild')

    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    fireEvent.click(screen.getByRole('button', { name: 'Export Report' }))
    fireEvent.click(screen.getByText('Download HTML'))

    const anchor = appendSpy.mock.calls.find(
      (call) => call[0] instanceof HTMLAnchorElement,
    )?.[0] as HTMLAnchorElement | undefined

    expect(anchor).toBeDefined()
    expect(anchor!.download).toContain('ptu-assessment')
    expect(anchor!.download).toContain('gpt-4o-2024-11-20')
    expect(anchor!.download).not.toContain('ptu-consolidation')

    appendSpy.mockRestore()
    vi.advanceTimersByTime(1000)
  })
})

describe('Consolidation export — warnings and all_on_ptu', () => {
  it('renders consolidation warnings in the report', () => {
    const summary = buildConsolidationSummary()
    summary.warnings = [
      "Deployment 'dep-late' has no data for 03/24–03/27. Consolidation will treat missing periods as 0 TPM.",
    ]
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )
    const report = document.getElementById('export-report-root')!
    const root = within(report)
    expect(root.getByText(/dep-late/)).toBeInTheDocument()
    expect(root.getByText(/0 TPM/)).toBeInTheDocument()
  })

  it('does not render warnings section when warnings array is empty', () => {
    const summary = buildConsolidationSummary()
    summary.warnings = []
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )
    expect(document.querySelector('[data-testid="report-consolidation-warnings"]')).toBeNull()
  })

  it('renders all_on_ptu savings messaging variant', () => {
    const summary = buildConsolidationSummary()
    summary.all_on_ptu = true
    summary.warnings = [
      "All selected deployments already use PTU (ProvisionedManaged). This analysis shows what their combined PAYG cost would be vs the current PTU spend.",
    ]
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )
    const report = document.getElementById('export-report-root')!
    const root = within(report)
    // all_on_ptu variant with positive savings — summary text uses "already use PTU"
    // and the warning also mentions PTU, so use getAllByText
    const ptuTexts = root.getAllByText(/already use PTU/)
    expect(ptuTexts.length).toBeGreaterThanOrEqual(1)
    expect(root.getByText(/single PTU allocation/)).toBeInTheDocument()
  })

  it('renders all_on_ptu negative savings messaging variant', () => {
    const summary = buildConsolidationSummary()
    summary.all_on_ptu = true
    summary.savings = -500
    summary.savings_pct = -4.0
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )
    const report = document.getElementById('export-report-root')!
    const root = within(report)
    expect(root.getByText(/already use PTU/)).toBeInTheDocument()
    expect(root.getByText(/already cost-effective/)).toBeInTheDocument()
  })

  it('renders multiple warnings', () => {
    const summary = buildConsolidationSummary()
    summary.warnings = [
      "Deployment 'dep-a' has no data for 03/24–03/27. Consolidation will treat missing periods as 0 TPM.",
      "Deployment 'dep-b' has no data for 03/29–03/31. Consolidation will treat missing periods as 0 TPM.",
    ]
    render(
      <ExportReport
        analysis={buildAnalysis()}
        baseAnalysis={null}
        isZoomed={false}
        consolidationSummary={summary}
      />,
    )
    const warnings = document.querySelectorAll('.report-warning-item')
    expect(warnings.length).toBe(2)
  })
})
