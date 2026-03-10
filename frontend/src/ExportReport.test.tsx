import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ExportReport } from './ExportReport'
import type { AnalysisResponse } from './types'

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
      latency: { timestamps: [], p50: [], p95: [], p99: [] },
      tpm: { timestamps: [], values: [], avg: 42300, p25: 30000, p95: 78500 },
      throttling: { timestamps: [], values: [] },
      cost_curves: {
        baseline_tpm: [], payg_monthly: [], ptu_spill_monthly: [], ptu_units: [],
        break_even_tpm: 38000, slider_baseline_tpm: 42300, payg_at_slider: 12450, hybrid_at_slider: 8200,
      },
    },
    cost_analysis: {
      pricing: {
        focus_topic: 'Cost Reduction',
        reservation_type: 'Monthly',
        reservation_discount_pct: 64,
        payg_blended_rate_per_million: 4.75,
        ptu_hourly_rate: 1,
        ptu_capacity_per_unit: 2500,
        ptu_minimum: 15,
        ptu_increment: 5,
        region: 'eastus',
        region_display_name: 'East US',
        region_multiplier: 1.0,
        deployment_type: 'regional',
        deployment_type_label: 'Regional',
      },
      payg: { monthly_tokens: 99000000, payg_base: 10000, throttle_impact: 2450, payg_total: 12450 },
      hybrid: {
        baseline_percentile: 65,
        baseline_label: '50 PTU',
        baseline_tpm: 42300,
        baseline_ptu: 50,
        default_baseline_ptu: 50,
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
      formula_blocks: { payg: '', hybrid: '' },
    },
    insights: { break_even_message: '', focus_topic: 'Cost Reduction', analysis_notes: [] },
    ...overrides,
  }
}

/* ────────────────────────────────────────────────────
   Dropdown button
   ──────────────────────────────────────────────────── */

describe('Export dropdown', () => {
  it('renders the Export Report button', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    expect(screen.getByText('Export Report ▾')).toBeInTheDocument()
  })

  it('shows menu items on click', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    fireEvent.click(screen.getByText('Export Report ▾'))

    expect(screen.getByText('Download PDF')).toBeInTheDocument()
    expect(screen.getByText('Download HTML')).toBeInTheDocument()
  })

  it('toggles dropdown open/closed', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    const btn = screen.getByText('Export Report ▾')

    fireEvent.click(btn)
    expect(screen.getByText('Download PDF')).toBeInTheDocument()

    fireEvent.click(btn)
    expect(screen.queryByText('Download PDF')).not.toBeInTheDocument()
  })

  it('has proper aria attributes', () => {
    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)
    const btn = screen.getByText('Export Report ▾')

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
  })

  it('shows amber banner for borderline', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'borderline' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--amber')
    expect(banner.textContent).toContain('Borderline')
  })

  it('shows blue banner for ptu_not_recommended', () => {
    render(<ExportReport analysis={buildAnalysis({ recommendation: 'ptu_not_recommended' })} baseAnalysis={null} isZoomed={false} />)

    const banner = document.querySelector('.report-rec-banner')!
    expect(banner).toHaveClass('report-rec--blue')
    expect(banner.textContent).toContain('Stay on PAYG')
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

/* ────────────────────────────────────────────────────
   Export actions
   ──────────────────────────────────────────────────── */

describe('Export actions', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('triggers HTML download on "Download HTML" click', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    global.URL.createObjectURL = createObjectURL
    global.URL.revokeObjectURL = revokeObjectURL

    render(<ExportReport analysis={buildAnalysis()} baseAnalysis={null} isZoomed={false} />)

    fireEvent.click(screen.getByText('Export Report ▾'))
    fireEvent.click(screen.getByText('Download HTML'))

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    // revokeObjectURL is deferred via setTimeout
    expect(revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
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

    fireEvent.click(screen.getByText('Export Report ▾'))
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

    fireEvent.click(screen.getByText('Export Report ▾'))
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
