import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

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
      baseline_tpm: [5000, 10000],
      payg_monthly: [1800, 3600],
      ptu_spill_monthly: [1700, 2900],
      ptu_units: [15, 20],
      break_even_tpm: 8200,
      slider_baseline_tpm: 10000,
      payg_at_slider: 3600,
      hybrid_at_slider: 2900,
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

  it('renders info tooltips for widgets', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    const allMatches = await screen.findAllByText(/PTU RECOMMENDED/i)
    expect(allMatches.length).toBeGreaterThan(0)

    const tooltipNotes = screen.getAllByLabelText(/^Info:/i)
    expect(tooltipNotes.length).toBeGreaterThan(8)
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

  it('renders interactive chart guidance text', async () => {
    render(<App />)

    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    await screen.findByText('Evidence')

    expect(screen.getAllByLabelText(/Hover to inspect exact/i).length).toBeGreaterThan(0)
  })
})
