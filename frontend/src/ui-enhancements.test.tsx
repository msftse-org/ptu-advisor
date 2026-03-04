import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

/* ────────────────────────────────────────────────────
   Shared mock data
   ──────────────────────────────────────────────────── */

function buildMockResponse(overrides: Record<string, unknown> = {}) {
  return {
    recommendation: 'ptu_recommended',
    confidence: 0.93,
    summary: 'PTU is recommended based on strong workload signals.',
    explanation: 'Your workload is stable.',
    what_would_change: 'Lower sustained load.',
    data_quality: 'Good data quality.',
    analysis_period: '14 days',
    dimensions: [
      {
        name: 'Workload Shape',
        score: 'positive',
        confidence: 0.91,
        summary: 'Workload stable.',
        explanation: 'Low variance.',
        key_metrics: { cv: 0.42, sustained: 68.4 },
        is_positive: true,
      },
      {
        name: 'Capacity Pressure',
        score: 'negative',
        confidence: 0.65,
        summary: 'Low throttling.',
        explanation: 'No significant pressure.',
        key_metrics: { throttling_rate: 0.1 },
        is_positive: false,
      },
      {
        name: 'Latency Sensitivity',
        score: 'neutral',
        confidence: 0.72,
        summary: 'Average latency.',
        explanation: 'No strong signal.',
        key_metrics: {},
        is_positive: false,
      },
      {
        name: 'Load Predictability',
        score: 'insufficient',
        confidence: 0.3,
        summary: 'Not enough data.',
        explanation: 'Too few data points.',
        key_metrics: {},
        is_positive: false,
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
      latency: {
        timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
        p50: [390, 430],
        p95: [880, 930],
        p99: [1400, 1480],
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
        region_display_name: 'East US',
        region_multiplier: 1.0,
        deployment_type_label: 'Global',
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
    ...overrides,
  }
}

function setupMockFetch(analysisOverrides: Record<string, unknown> = {}) {
  const response = buildMockResponse(analysisOverrides)
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
      return new Response(JSON.stringify(response), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as unknown as typeof fetch
}

async function runDemoAnalysis() {
  render(<App />)
  fireEvent.click(screen.getByText('Demo Mode'))
  fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))
}

/* ────────────────────────────────────────────────────
   RecBadge
   ──────────────────────────────────────────────────── */

describe('RecBadge rendering', () => {
  it('shows ✓ PTU Recommended badge for ptu_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_recommended' })
    await runDemoAnalysis()

    const badge = await screen.findByText(/PTU Recommended/i)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-positive')
    // Check for the checkmark character (U+2713)
    expect(badge.textContent).toContain('\u2713')
  })

  it('shows — Stay on PAYG badge for ptu_not_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_not_recommended' })
    await runDemoAnalysis()

    const badges = await screen.findAllByText(/Stay on PAYG/i)
    const badge = badges.find(el => el.classList.contains('rec-badge'))!
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-negative')
    // Check for the em-dash character (U+2014)
    expect(badge.textContent).toContain('\u2014')
  })

  it('shows ⚠ Borderline badge for borderline', async () => {
    setupMockFetch({ recommendation: 'borderline' })
    await runDemoAnalysis()

    const badges = await screen.findAllByText(/Borderline/i)
    const badge = badges.find(el => el.classList.contains('rec-badge'))!
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-borderline')
    // Check for the warning character (U+26A0)
    expect(badge.textContent).toContain('\u26A0')
  })
})

/* ────────────────────────────────────────────────────
   Dimension score badges
   ──────────────────────────────────────────────────── */

describe('Dimension score badge classes', () => {
  beforeEach(() => {
    setupMockFetch()
  })

  it('applies dim-score-positive class for positive score', async () => {
    await runDemoAnalysis()
    await screen.findByText('Workload Shape')

    const card = screen.getByTestId('dimension-card-workload-shape')
    const scoreBadge = within(card).getByText(/POSITIVE/i)
    expect(scoreBadge).toHaveClass('dim-score', 'dim-score-positive')
  })

  it('applies dim-score-negative class for negative score', async () => {
    await runDemoAnalysis()
    await screen.findByText('Capacity Pressure')

    const card = screen.getByTestId('dimension-card-capacity-pressure')
    const scoreBadge = within(card).getByText(/NEGATIVE/i)
    expect(scoreBadge).toHaveClass('dim-score', 'dim-score-negative')
  })

  it('applies dim-score-neutral class for neutral score', async () => {
    await runDemoAnalysis()
    await screen.findByText('Latency Sensitivity')

    const card = screen.getByTestId('dimension-card-latency-sensitivity')
    const scoreBadge = within(card).getByText(/NEUTRAL/i)
    expect(scoreBadge).toHaveClass('dim-score', 'dim-score-neutral')
  })

  it('applies dim-score-insufficient class for insufficient score', async () => {
    await runDemoAnalysis()
    await screen.findByText('Load Predictability')

    const card = screen.getByTestId('dimension-card-load-predictability')
    const scoreBadge = within(card).getByText(/INSUFFICIENT/i)
    expect(scoreBadge).toHaveClass('dim-score', 'dim-score-insufficient')
  })
})

/* ────────────────────────────────────────────────────
   Loading spinner
   ──────────────────────────────────────────────────── */

describe('Loading spinner', () => {
  it('shows loading spinner while analysis is in progress', async () => {
    // Make the analyze endpoint hang so we can assert loading state
    let resolveAnalysis!: (value: Response) => void
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
          JSON.stringify({ regions: [], deployment_types: [] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }

      if (url.includes('/api/analyze')) {
        return new Promise<Response>((resolve) => {
          resolveAnalysis = resolve
        })
      }

      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as unknown as typeof fetch

    render(<App />)
    fireEvent.click(screen.getByText('Demo Mode'))
    fireEvent.click(screen.getByRole('button', { name: /run analysis/i }))

    // Spinner should be visible while loading
    await waitFor(() => {
      expect(screen.getByText('Analyzing deployment metrics')).toBeInTheDocument()
    })

    // Button should also say Analyzing
    expect(screen.getByRole('button', { name: /analyzing/i })).toBeDisabled()

    // Now resolve the fetch – the spinner should go away
    resolveAnalysis(
      new Response(JSON.stringify(buildMockResponse()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await waitFor(() => {
      expect(screen.queryByText('Analyzing deployment metrics')).not.toBeInTheDocument()
    })
  })
})

/* ────────────────────────────────────────────────────
   Cost winner highlight
   ──────────────────────────────────────────────────── */

describe('Cost winner highlight', () => {
  it('marks PAYG card as winner when PAYG is cheaper', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        payg: { ...buildMockResponse().cost_analysis.payg, payg_total: 500 },
        hybrid: { ...buildMockResponse().cost_analysis.hybrid, hybrid_total: 5000 },
      },
    })
    await runDemoAnalysis()

    const paygCard = await screen.findByText('PAYG Monthly')
    const paygArticle = paygCard.closest('article')
    expect(paygArticle).toHaveClass('is-winner')

    const hybridCard = screen.getByText('PTU + Spillover')
    const hybridArticle = hybridCard.closest('article')
    expect(hybridArticle).not.toHaveClass('is-winner')
  })

  it('marks PTU + Spillover card as winner when hybrid is cheaper', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        payg: { ...buildMockResponse().cost_analysis.payg, payg_total: 8000 },
        hybrid: { ...buildMockResponse().cost_analysis.hybrid, hybrid_total: 3000 },
      },
    })
    await runDemoAnalysis()

    const hybridCard = await screen.findByText('PTU + Spillover')
    const hybridArticle = hybridCard.closest('article')
    expect(hybridArticle).toHaveClass('is-winner')

    const paygCard = screen.getByText('PAYG Monthly')
    const paygArticle = paygCard.closest('article')
    expect(paygArticle).not.toHaveClass('is-winner')
  })

  it('marks both as winner when costs are equal', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        payg: { ...buildMockResponse().cost_analysis.payg, payg_total: 3000 },
        hybrid: { ...buildMockResponse().cost_analysis.hybrid, hybrid_total: 3000 },
      },
    })
    await runDemoAnalysis()

    const paygCard = await screen.findByText('PAYG Monthly')
    expect(paygCard.closest('article')).toHaveClass('is-winner')

    const hybridCard = screen.getByText('PTU + Spillover')
    expect(hybridCard.closest('article')).toHaveClass('is-winner')
  })
})

/* ────────────────────────────────────────────────────
   Stagger animation classes
   ──────────────────────────────────────────────────── */

describe('Stagger animation classes on section titles', () => {
  beforeEach(() => {
    setupMockFetch()
  })

  it('applies stagger classes to result section headings', async () => {
    await runDemoAnalysis()
    await screen.findByText('At a Glance')

    const glance = screen.getByText('At a Glance')
    expect(glance).toHaveClass('stagger-1')

    const evidence = screen.getByText('Evidence')
    expect(evidence).toHaveClass('stagger-3')

    const traffic = screen.getByText('Traffic Shape Signals')
    expect(traffic).toHaveClass('stagger-5')

    const financial = screen.getByText('Financial Decision')
    expect(financial).toHaveClass('stagger-6')

    const scoring = screen.getByText('Scoring Breakdown')
    expect(scoring).toHaveClass('stagger-7')
  })
})

/* ────────────────────────────────────────────────────
   Back button
   ──────────────────────────────────────────────────── */

describe('Back to Setup button', () => {
  beforeEach(() => {
    setupMockFetch()
  })

  it('renders left-arrow character in the back button', async () => {
    await runDemoAnalysis()
    await screen.findByText('At a Glance')

    const backButton = screen.getByRole('button', { name: /back to setup/i })
    expect(backButton).toBeInTheDocument()
    // Left arrow U+2190
    expect(backButton.textContent).toContain('\u2190')
    expect(backButton).toHaveClass('secondary', 'stagger-8')
  })

  it('returns to setup panel when clicked', async () => {
    await runDemoAnalysis()
    await screen.findByText('At a Glance')

    fireEvent.click(screen.getByRole('button', { name: /back to setup/i }))

    await waitFor(() => {
      expect(screen.getByText('Configure Analysis')).toBeInTheDocument()
    })
    expect(screen.queryByText('At a Glance')).not.toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   Result banner styling
   ──────────────────────────────────────────────────── */

describe('Result banner recommendation class', () => {
  it('applies rec-positive class for ptu_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_recommended' })
    await runDemoAnalysis()

    const banner = (await screen.findByText(/Recommendation:/i)).closest('.result-banner')
    expect(banner).toHaveClass('rec-positive')
  })

  it('applies rec-negative class for ptu_not_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_not_recommended' })
    await runDemoAnalysis()

    const banner = (await screen.findByText(/Recommendation:/i)).closest('.result-banner')
    expect(banner).toHaveClass('rec-negative')
  })

  it('applies rec-borderline class for borderline', async () => {
    setupMockFetch({ recommendation: 'borderline' })
    await runDemoAnalysis()

    const banner = (await screen.findByText(/Recommendation:/i)).closest('.result-banner')
    expect(banner).toHaveClass('rec-borderline')
  })
})

/* ────────────────────────────────────────────────────
   Break-even callout tones
   ──────────────────────────────────────────────────── */

describe('Break-even callout', () => {
  it('shows tone-positive when avg TPM is well above break-even', async () => {
    setupMockFetch()
    // Default mock: avg_tpm=12345, break_even_tpm=8200 → ~50% above → positive
    await runDemoAnalysis()

    const callouts = await screen.findAllByText(/above break-even/i)
    const callout = callouts.find(el => el.classList.contains('break-even-callout'))!
    expect(callout).toBeInTheDocument()
    expect(callout).toHaveClass('tone-positive')
  })

  it('shows tone-negative when avg TPM is below break-even', async () => {
    setupMockFetch({
      metrics: {
        ...buildMockResponse().metrics,
        avg_tpm: 5000,
      },
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        comparison: {
          ...buildMockResponse().cost_analysis.comparison,
          break_even_tpm: 8200,
        },
      },
    })
    await runDemoAnalysis()

    const callouts = await screen.findAllByText(/below break-even/i)
    const callout = callouts.find(el => el.classList.contains('break-even-callout'))!
    expect(callout).toBeInTheDocument()
    expect(callout).toHaveClass('tone-negative')
  })
})
