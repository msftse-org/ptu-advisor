import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { calculateBreakEvenRange } from './calculator'

const mockAnalysisResponse = {
  recommendation: 'ptu_recommended',
  confidence: 0.93,
  summary: 'PTU is recommended based on strong workload signals.',
  explanation: 'Your workload is stable and sees capacity pressure under PAYG.',
  what_would_change: 'Lower sustained load and lower throttling would reduce PTU benefits.',
  data_quality: 'Good data quality with sufficient lookback coverage.',
  analysis_period: '14 days',
  dimensions: [
    {
      name: 'Workload Shape',
      score: 'positive',
      confidence: 0.91,
      summary: 'Workload appears stable.',
      explanation: 'Low variance and sustained throughput indicate PTU fit.',
      key_metrics: { cv: 0.42, sustained: 68.4 },
      is_positive: true,
    },
    {
      name: 'Capacity Pressure',
      score: 'positive',
      confidence: 0.88,
      summary: '429 responses indicate pressure.',
      explanation: 'Observed throttling creates reliability risk under PAYG.',
      key_metrics: { throttling_rate: 3.4 },
      is_positive: true,
    },
  ],
  metrics: {
    deployment_name: 'demo-deployment',
    model_name: 'gpt-4o',
    avg_tpm: 12345,
    peak_tpm: 21456,
    throttling_rate_pct: 3.42,
    total_requests: 250000,
    throttled_requests: 8540,
    successful_requests: 241460,
    total_tokens: 99000000,
    total_tokens_millions: 99,
    lookback_days: 14,
    latency: { p50: 420, p95: 910, p99: 1450 },
    utilization: {
      peak_to_average_ratio: 1.74,
      sustained_utilization_rate: 66,
      active_hours_percentage: 82,
      business_hours_concentration: 64,
      weekend_vs_weekday_ratio: 0.58,
    },
  },
  charts: {
    tokens: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
      prompt: [4000, 4200],
      completion: [2600, 2800],
      total: [6600, 7000],
    },
    requests: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
      successful: [1000, 1100],
      throttled: [15, 22],
      total: [1015, 1122],
    },
    daily_cost: {
      dates: ['2026-02-01'],
      input_cost: [16.5],
      output_cost: [28.0],
      total_cost: [44.5],
      avg_daily_cost: 44.5,
      ptu_daily_cost: 173.33,
    },
    tpm: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
      values: [12000, 12800],
      avg: 12345,
      p95: 21456,
    },
    throttling: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
      values: [15, 22],
    },
    cost_curves: {
      sustained_tpm: [5000, 10000],
      payg_monthly: [1800, 3600],
      ptu_spill_monthly: [1700, 2900],
      break_even_tpm: 8200,
      break_even_reason: 'exists' as const,
      ptu_capacity_tpm: 37500,
      avg_tpm: 10000,
      selected_ptu: 15,
      payg_at_avg: 3600,
      hybrid_at_avg: 2900,
    },
  },
  cost_analysis: {
    pricing: {
      focus_topic: 'Cost Reduction',
      reservation_type: 'Monthly Commitment (Estimated 64% off)',
      reservation_discount_pct: 64,
      payg_blended_rate_per_million: 4.75,
      ptu_hourly_rate: 1,
      ptu_capacity_per_unit: 2500,
      ptu_minimum: 15,
      ptu_increment: 5,
    },
    payg: {
      monthly_tokens: 99000000,
      payg_base: 470,
      throttle_impact: 120,
      payg_total: 590,
    },
    hybrid: {
      baseline_percentile: 75,
      baseline_label: '20 PTU',
      baseline_tpm: 10000,
      baseline_ptu: 20,
      default_baseline_ptu: 20,
      max_viable_baseline_ptu: 45,
      max_baseline_ptu: 100,
      ptu_capacity_tpm: 50000,
      avg_spillover_tpm: 800,
      spillover_tokens_monthly: 34560000,
      spillover_cost: 164,
      ptu_baseline_cost: 5200,
      hybrid_total: 5364,
      spillover_pct: 22,
    },
    full_ptu: {
      ptu_needed_full: 25,
      ptu_monthly_full: 18000,
      ptu_committed_cost: 6500,
    },
    comparison: {
      savings: 740,
      savings_pct: 12.1,
      break_even_tpm: 8200,
      cheaper_strategy: 'PTU + Spillover',
    },
    commitment_safety: {
      savings_margin_pct: 12.1,
      spillover_pct: 15.0,
      capacity_coverage_pct: 85.0,
      safety_verdict: 'safe' as const,
    },
    formula_blocks: {
      payg: 'payg formula block',
      hybrid: 'hybrid formula block',
    },
  },
  insights: {
    break_even_message: 'Your average usage is above break-even.',
    focus_topic: 'Cost Reduction',
    analysis_notes: ['Note 1', 'Note 2'],
  },
}

describe('Results UX parity checks', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/api/focus-topics')) {
        return new Response(JSON.stringify([{ name: 'Cost Reduction', tagline: 'Tagline' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/api/discovery/subscriptions')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/api/pricing/options')) {
        return new Response(
          JSON.stringify({
            regions: [{ name: 'eastus', display_name: 'East US', multiplier: 1.0, zone: 'US' }],
            deployment_types: [
              { name: 'global', label: 'Global', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.0 },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }

      if (url.includes('/api/analyze')) {
        return new Response(JSON.stringify(mockAnalysisResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as unknown as typeof fetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('opens as an operational analysis workspace', () => {
    render(<App />)

    expect(screen.getByRole('banner', { name: 'PTU Advisor analysis workspace' })).toBeInTheDocument()
    expect(screen.getByRole('main', { name: 'PTU Advisor workspace' })).toBeInTheDocument()
    expect(screen.queryByText('Usage Assessment')).not.toBeInTheDocument()
    expect(screen.queryByText('Azure OpenAI economics')).not.toBeInTheDocument()
    expect(screen.queryByText('Decision workspace')).not.toBeInTheDocument()
    expect(screen.getByText('Configure Analysis')).toBeInTheDocument()
  })

  it('gives the calculator comparison an accessible table name', () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'PTU Calculator' }))

    expect(screen.getByRole('table', { name: 'PTU strategy comparison' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'PTU strategy comparison table' })).toBeInTheDocument()
  })

  it('renders info tooltips for widgets', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const allMatches = await screen.findAllByText(/PTU RECOMMENDED/i)
    expect(allMatches.length).toBeGreaterThan(0)

    const tooltipControls = screen.getAllByRole('button', { name: /^Info:/i })
    expect(tooltipControls.length).toBeGreaterThan(8)
  })

  it('discloses the cache-aware Cost Explorer slope assumptions in its ordinary info tooltip', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const explorer = await screen.findByRole('region', { name: 'Cost Explorer analytical widget' })
    expect(within(explorer).getByRole('button', {
      name: /PAYG includes observed cached-input pricing.*conservatively prices spillover as uncached.*green line can therefore rise slightly faster.*upper break-even/i,
    })).toBeInTheDocument()
  })

  it('puts decision context and report navigation before detailed evidence', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const sectionNavigation = await screen.findByRole('navigation', { name: 'Analysis sections' })
    expect(within(sectionNavigation).getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '#overview')
    expect(within(sectionNavigation).getByRole('link', { name: 'Evidence' })).toHaveAttribute('href', '#evidence')
    expect(within(sectionNavigation).getByRole('link', { name: 'Economics' })).toHaveAttribute('href', '#economics')
    expect(within(sectionNavigation).getByRole('link', { name: 'Rationale' })).toHaveAttribute('href', '#rationale')

    const snapshot = screen.getByRole('region', { name: 'Decision snapshot' })
    expect(within(snapshot).getByText('PAYG monthly')).toBeInTheDocument()
    expect(within(snapshot).getByText('PTU + spillover')).toBeInTheDocument()
    expect(within(snapshot).getByText('Monthly difference')).toBeInTheDocument()
    expect(within(snapshot).getByText('Commitment safety')).toBeInTheDocument()
  })

  it('moves the viewport and focus to newly rendered analysis results', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const results = await screen.findByRole('region', { name: 'Analysis results' })

    await waitFor(() => {
      expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'auto' })
      expect(results).toHaveFocus()
    })
  })

  it('renders expandable Dimension Breakdown entries', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    await screen.findByText('Scoring Breakdown')

    const dimensionCard = screen.getByTestId('dimension-card-workload-shape')
    expect(dimensionCard).toBeInTheDocument()

    const summary = screen.getByText('Workload Shape')
    fireEvent.click(summary)

    await waitFor(() => {
      expect(screen.getByText(/Low variance and sustained throughput/i)).toBeInTheDocument()
    })
  })

  it('renders redesigned Recommendation Context panel', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    await screen.findByTestId('recommendation-context')

    expect(screen.getByText('Why this recommendation fits')).toBeInTheDocument()
    expect(screen.getByText('What would change this call')).toBeInTheDocument()
    expect(screen.getByText('Data quality notes')).toBeInTheDocument()
  })

  it('shows PTU pricing term and baseline controls on results screen only', async () => {
    render(<App />)

    expect(screen.queryByText('PTU Pricing Term')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    await screen.findByText('Assumptions')

    expect(screen.getByText('PTU Pricing Term')).toBeInTheDocument()
    expect(screen.getByText(/PTU Baseline Coverage \(\d+ PTU\)/i)).toBeInTheDocument()
    expect(screen.getByText(/changes apply automatically/i)).toBeInTheDocument()
  })

  it('keeps detailed cost formulas collapsed until requested', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const detailsHeading = await screen.findByRole('heading', { name: 'Calculation Details' })
    expect(detailsHeading.closest('details')).not.toHaveAttribute('open')
  })

  it('advertises auditable calculation inputs and updates its disclosure action', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const detailsHeading = await screen.findByRole('heading', { name: 'Calculation Details' })
    const details = detailsHeading.closest('details')
    const summary = detailsHeading.closest('summary')

    expect(details).not.toHaveAttribute('open')
    expect(summary).not.toBeNull()
    expect(within(summary!).getByText('Actual rates, token volumes, and step-by-step cost math')).toBeInTheDocument()
    expect(within(summary!).getByText('Expand')).toBeInTheDocument()

    fireEvent.click(summary!)

    await waitFor(() => {
      expect(details).toHaveAttribute('open')
      expect(within(summary!).getByText('Collapse')).toBeInTheDocument()
    })
  })

  it('renders interactive chart guidance text', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    await screen.findByRole('heading', { name: 'Evidence' })

    expect(screen.getAllByLabelText(/Hover to inspect exact/i).length).toBeGreaterThan(0)
  })
})

describe('PTU calculator break-even math', () => {
  it('ignores floating-point noise between parallel cost slopes', () => {
    const result = calculateBreakEvenRange({
      ptuFixed: 100,
      ptuCapacityRaw: 100,
      paygRatePerMillion: 10.000000000001,
      spilloverRatePerMillion: 10,
    })

    expect(result).toEqual({ lower: null, upper: null })
  })
})
