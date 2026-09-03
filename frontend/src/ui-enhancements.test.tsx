import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const chartHarness = vi.hoisted(() => ({
  onDataZoom: null as null | ((params: { start?: number; end?: number }) => void),
  costCurveProps: null as null | {
    selectedPtu: number
    ptuCapacityTpm: number
    hybridAtAvg: number
  },
}))

// Mock echarts to prevent jsdom rendering crashes (no real layout engine)
vi.mock('echarts-for-react/lib/core', () => ({
  default: (props: { onEvents?: { datazoom?: (params: { start?: number; end?: number }) => void } }) => {
    if (props.onEvents?.datazoom) chartHarness.onDataZoom = props.onEvents.datazoom
    return null
  },
  __esModule: true,
}))

vi.mock('./charts/CostCurveChart', () => ({
  CostCurveChart: (props: { selectedPtu: number; ptuCapacityTpm: number; hybridAtAvg: number }) => {
    chartHarness.costCurveProps = props
    return null
  },
}))

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
      cache_match_rate: {
        available: true,
        source: 'observed',
        quality: 'good',
        avg_pct: 58.4,
        p95_pct: 72.1,
        coverage_pct: 94.6,
        cached_prompt_tokens: 58000000,
        active_prompt_tokens: 41000000,
        active_tokens_observed: 0,
      },
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
      prompt_cache: {
        timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T01:00:00Z'],
        match_rate_pct: [55, 61.8],
        prompt_tokens: [4000, 4200],
        cached_prompt_tokens: [2200, 2595.6],
        active_prompt_tokens: [1800, 1604.4],
        source: 'observed',
      },
      cost_curves: {
        sustained_tpm: [5000, 10000],
        payg_monthly: [1800, 3600],
        ptu_spill_monthly: [1700, 2900],
        break_even_tpm: 8200,
        upper_break_even_tpm: null,
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
        payg_cached_input_rate_per_million: 1.25,
        cached_input_pricing_source: 'fallback',
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
        upper_break_even_tpm: null,
        cheaper_strategy: 'PTU + Spillover',
      },
      commitment_safety: {
        savings_margin_pct: 12.1,
        spillover_pct: 15.0,
        capacity_coverage_pct: 85.0,
        safety_verdict: 'safe' as const,
      },
      cache_impact: {
        applied: true,
        source: 'observed',
        quality: 'good',
        coverage_pct: 94.6,
        no_cache_normalized_avg_tpm: 18000,
        cache_adjusted_normalized_avg_tpm: 12000,
        normalized_tpm_reduction_pct: 33.3,
        no_cache_recommended_ptu: 25,
        cache_aware_recommended_ptu: 20,
        ptu_avoided: 5,
        no_cache_payg_monthly: 1200,
        cache_aware_payg_monthly: 900,
        payg_cache_savings: 300,
        fixed_ptu_cost_changed: false,
        calculation_note: 'Cached prompt tokens reduce modeled utilization; fixed PTU cost changes only when the selected PTU count changes.',
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

function setupMockFetch(
  analysisOverrides: Record<string, unknown> = {},
  responseForPayload?: (payload: Record<string, unknown>) => ReturnType<typeof buildMockResponse>,
) {
  const defaultResponse = buildMockResponse(analysisOverrides)
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
      const payload = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {}
      const response = responseForPayload?.(payload) ?? defaultResponse
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

beforeEach(() => {
  chartHarness.onDataZoom = null
  chartHarness.costCurveProps = null
})

describe('Analytical evidence widgets', () => {
  it('exposes truthful metric summaries for every primary evidence chart', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const tokenVolume = await screen.findByRole('region', { name: 'Token Volume Over Time analytical widget' })
    expect(tokenVolume).toHaveAccessibleDescription('99,000,000 total tokens across 14 days; 7,071,429 average tokens per day.')

    const requestOutcomes = screen.getByRole('region', { name: 'Request Outcomes analytical widget' })
    expect(requestOutcomes).toHaveAccessibleDescription('250,000 total requests; 8,540 rate-limited responses; 3.42% HTTP 429 rate.')

    const dailyCost = screen.getByRole('region', { name: 'Daily Deployment Cost analytical widget' })
    expect(dailyCost).toHaveAccessibleDescription('$44.50 period cost; $44.50 average cost per day.')

    const rateLimits = screen.getByRole('region', { name: 'Rate-Limit Events (429) analytical widget' })
    expect(rateLimits).toHaveAccessibleDescription('8,540 throttled requests; 3.42% of all requests received HTTP 429 responses.')

    const cacheEvidence = screen.getByRole('group', { name: 'Prompt cache evidence' })
    expect(cacheEvidence).toHaveClass('prompt-cache-composition')

    const cacheVolume = within(cacheEvidence).getByRole('region', { name: 'Prompt Cache Volume analytical widget' })
    expect(cacheVolume).toHaveAccessibleDescription('4,796 cached prompt tokens and 3,404 active prompt tokens across the selected period; cached tokens are 58.5% of 8,200 total prompt tokens.')

    const cacheEfficiency = within(cacheEvidence).getByRole('region', { name: 'Cache Efficiency analytical widget' })
    expect(cacheEfficiency).toHaveAccessibleDescription('58.4% average prompt cache match with 94.6% telemetry coverage; 5 PTU avoided after capacity rounding and 33.3% normalized load reduction. Source observed; quality good; applied to the model.')

    const throughput = screen.getByRole('region', { name: 'Throughput Band (TPM vs Avg/Break-even) analytical widget' })
    expect(throughput).toHaveAccessibleDescription('12,345 average tokens per minute; 21,456 P95 tokens per minute.')
  })

  it('places an accessible four-fact economics comparison before the Cost Explorer chart', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const explorer = await screen.findByRole('region', { name: 'Cost Explorer analytical widget' })
    const facts = within(explorer).getByRole('list', { name: 'Cost Explorer economics summary' })
    expect(within(facts).getByText('PAYG monthly')).toBeInTheDocument()
    expect(within(facts).getByText('$590')).toBeInTheDocument()
    expect(within(facts).getByText('PTU + spillover monthly')).toBeInTheDocument()
    expect(within(facts).getByText('$5,364')).toBeInTheDocument()
    expect(within(facts).getByText('Monthly difference')).toBeInTheDocument()
    expect(within(facts).getByText('$740 saved')).toBeInTheDocument()
    expect(within(facts).getByText('Break-even range')).toBeInTheDocument()
    expect(within(facts).getByText('8,200 TPM / No upper bound')).toBeInTheDocument()
    expect(within(explorer).getByText('15 PTU')).toBeInTheDocument()
    expect(within(explorer).getByText('Monthly · Est. 64% off')).toBeInTheDocument()

    const chart = within(explorer).getByRole('img', { name: 'PAYG and PTU plus spillover monthly cost by sustained throughput' })
    expect(chart).toHaveAccessibleDescription(/PAYG costs \$590 per month.*PTU plus spillover costs \$5,364 per month.*lower break-even is 8,200 TPM.*no upper break-even/i)
    expect(facts.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('Discovery orchestration', () => {
  it('commits one subscriptions callback under Strict Mode', async () => {
    setupMockFetch()
    const loadedEvents: CustomEvent[] = []
    const listener = (event: Event) => {
      const telemetryEvent = event as CustomEvent
      if (telemetryEvent.detail?.event === 'discovery_subscriptions_loaded') {
        loadedEvents.push(telemetryEvent)
      }
    }
    window.addEventListener('ptu:telemetry', listener)

    try {
      render(<StrictMode><App /></StrictMode>)

      await waitFor(() => {
        const subscriptionCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
          ([url]) => String(url).includes('/api/discovery/subscriptions'),
        )
        expect(subscriptionCalls).toHaveLength(1)
        expect(loadedEvents).toHaveLength(1)
      })
    } finally {
      window.removeEventListener('ptu:telemetry', listener)
    }
  })
})

/* ────────────────────────────────────────────────────
   RecBadge
   ──────────────────────────────────────────────────── */

describe('RecBadge rendering', () => {
  function expectDecorativeRecommendationIcon(badge: HTMLElement, kind: string) {
    const icon = badge.querySelector(`svg[data-recommendation-icon="${kind}"]`)
    expect(icon).not.toBeNull()
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveAttribute('focusable', 'false')
    expect(icon).toHaveAttribute('fill', 'none')
    expect(icon).toHaveAttribute('stroke', 'currentColor')
  }

  it('keeps synthetic demo provenance visible in the result banner', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const results = await screen.findByRole('region', { name: 'Analysis results' })
    const provenance = within(results).getByText('Synthetic demo data')
    expect(provenance).toHaveClass('demo-provenance')
    expect(provenance.closest('.result-banner')).not.toBeNull()
  })

  it('shows the recommended label and authored SVG for ptu_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_recommended' })
    await runDemoAnalysis()

    const badges = await screen.findAllByText(/PTU Recommended/i)
    const badge = badges.find(el => el.classList.contains('rec-badge'))!
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-positive')
    expect(badge).toHaveTextContent(/^PTU Recommended$/)
    expectDecorativeRecommendationIcon(badge, 'recommended')
  })

  it('shows the Stay on PAYG label and authored info SVG for ptu_not_recommended', async () => {
    setupMockFetch({ recommendation: 'ptu_not_recommended' })
    await runDemoAnalysis()

    const badges = await screen.findAllByText(/Stay on PAYG/i)
    const badge = badges.find(el => el.classList.contains('rec-badge'))!
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-negative')
    expect(badge).toHaveTextContent(/^Stay on PAYG$/)
    expectDecorativeRecommendationIcon(badge, 'info')
  })

  it('shows the borderline label and authored caution SVG for borderline', async () => {
    setupMockFetch({ recommendation: 'borderline' })
    await runDemoAnalysis()

    const badges = await screen.findAllByText(/Borderline/i)
    const badge = badges.find(el => el.classList.contains('rec-badge'))!
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('rec-badge', 'rec-badge-borderline')
    expect(badge).toHaveTextContent(/^Borderline$/)
    expectDecorativeRecommendationIcon(badge, 'borderline')
  })

  it('shows insufficient data without financial conclusions for zero traffic', async () => {
    const base = buildMockResponse()
    setupMockFetch({
      recommendation: 'insufficient_data',
      confidence: 0,
      summary: 'Insufficient traffic data for a PTU or PAYG recommendation.',
      cost_analysis: {
        ...base.cost_analysis,
        status: 'insufficient_data',
        comparison: {
          ...base.cost_analysis.comparison,
          break_even_tpm: null,
          upper_break_even_tpm: null,
          cheaper_strategy: null,
        },
        commitment_safety: {
          ...base.cost_analysis.commitment_safety,
          safety_verdict: 'insufficient_data',
        },
      },
      charts: {
        ...base.charts,
        cost_curves: {
          ...base.charts.cost_curves,
          break_even_tpm: null,
          upper_break_even_tpm: null,
          break_even_reason: 'insufficient_data',
        },
      },
      insights: {
        ...base.insights,
        break_even_message: 'Insufficient traffic data to calculate an economic break-even.',
      },
    })
    await runDemoAnalysis()

    const results = await screen.findByRole('region', { name: 'Analysis results' })
    const badge = within(results).getByRole('status', { name: 'Insufficient Data' })
    expect(badge).toHaveClass('rec-badge', 'rec-badge-insufficient')
    expect(badge).toHaveTextContent(/^Insufficient Data$/)
    expectDecorativeRecommendationIcon(badge, 'insufficient')
    expect(within(results).getByText('More traffic data required')).toBeInTheDocument()
    expect(within(results).queryByText('Savings Margin')).not.toBeInTheDocument()
    expect(within(results).queryByText(/Cost Explorer/)).not.toBeInTheDocument()
    expect(within(results).queryByText(/No economic break-even/)).not.toBeInTheDocument()
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
  it('marks the PAYG fact as winner when PAYG is cheaper', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        payg: { ...buildMockResponse().cost_analysis.payg, payg_total: 500 },
        hybrid: { ...buildMockResponse().cost_analysis.hybrid, hybrid_total: 5000 },
      },
    })
    await runDemoAnalysis()

    const facts = await screen.findByRole('list', { name: 'Cost Explorer economics summary' })
    expect(within(facts).getByText('PAYG monthly').closest('[role="listitem"]')).toHaveClass('is-winner')
    expect(within(facts).getByText('PTU + spillover monthly').closest('[role="listitem"]')).not.toHaveClass('is-winner')
  })

  it('marks the PTU plus spillover fact as winner when hybrid is cheaper', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        payg: { ...buildMockResponse().cost_analysis.payg, payg_total: 8000 },
        hybrid: { ...buildMockResponse().cost_analysis.hybrid, hybrid_total: 3000 },
      },
    })
    await runDemoAnalysis()

    const facts = await screen.findByRole('list', { name: 'Cost Explorer economics summary' })
    expect(within(facts).getByText('PTU + spillover monthly').closest('[role="listitem"]')).toHaveClass('is-winner')
    expect(within(facts).getByText('PAYG monthly').closest('[role="listitem"]')).not.toHaveClass('is-winner')
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

    const facts = await screen.findByRole('list', { name: 'Cost Explorer economics summary' })
    expect(within(facts).getByText('PAYG monthly').closest('[role="listitem"]')).toHaveClass('is-winner')
    expect(within(facts).getByText('PTU + spillover monthly').closest('[role="listitem"]')).toHaveClass('is-winner')
  })
})

describe('PTU baseline Cost Explorer recalculation', () => {
  it('updates Cost Explorer inputs and economics from 15 to 30 PTU with an active zoom window', async () => {
    const analyzePayloads: Record<string, unknown>[] = []
    const responseForPtu = (selectedPtu: number) => {
      const base = buildMockResponse()
      const paygTotal = 7000
      const hybridTotal = selectedPtu === 30 ? 6200 : 3500
      const savings = paygTotal - hybridTotal

      return buildMockResponse({
        charts: {
          ...base.charts,
          cost_curves: {
            ...base.charts.cost_curves,
            selected_ptu: selectedPtu,
            ptu_capacity_tpm: selectedPtu * 2500,
            ptu_spill_monthly: selectedPtu === 30 ? [5600, 6200] : [2900, 3500],
            hybrid_at_avg: hybridTotal,
          },
        },
        cost_analysis: {
          ...base.cost_analysis,
          payg: { ...base.cost_analysis.payg, payg_total: paygTotal },
          hybrid: {
            ...base.cost_analysis.hybrid,
            baseline_label: `${selectedPtu} PTU`,
            baseline_tpm: selectedPtu * 2500,
            baseline_ptu: selectedPtu,
            default_baseline_ptu: 15,
            ptu_capacity_tpm: selectedPtu * 2500,
            ptu_baseline_cost: selectedPtu === 30 ? 6000 : 3000,
            hybrid_total: hybridTotal,
          },
          comparison: {
            ...base.cost_analysis.comparison,
            savings,
            savings_pct: (savings / paygTotal) * 100,
          },
        },
      })
    }

    setupMockFetch({}, (payload) => {
      analyzePayloads.push(payload)
      return responseForPtu(Number(payload.baseline_ptu ?? 15))
    })
    await runDemoAnalysis()

    const slider = await screen.findByRole('slider', { name: /PTU Baseline Coverage/i })
    await waitFor(() => expect(chartHarness.onDataZoom).not.toBeNull())
    expect(chartHarness.costCurveProps).toMatchObject({
      selectedPtu: 15,
      ptuCapacityTpm: 37500,
      hybridAtAvg: 3500,
    })

    act(() => chartHarness.onDataZoom!({ start: 0, end: 50 }))
    await waitFor(() => expect(analyzePayloads).toHaveLength(2), { timeout: 2000 })

    fireEvent.change(slider, { target: { value: '30' } })

    await waitFor(() => {
      expect(analyzePayloads.at(-1)).toMatchObject({
        baseline_ptu: 30,
        window_start: '2026-02-01T00:00:00Z',
        window_end: '2026-02-01T01:00:00Z',
      })
    }, { timeout: 2000 })

    const explorer = screen.getByRole('region', { name: 'Cost Explorer analytical widget' })
    await waitFor(() => {
      expect(within(explorer).getByRole('heading', { name: /Cost Explorer.*30 PTU/i })).toBeInTheDocument()
      expect(within(explorer).getByText('$6,200')).toBeInTheDocument()
      expect(within(explorer).getByText('$800 saved')).toBeInTheDocument()
      expect(chartHarness.costCurveProps).toMatchObject({
        selectedPtu: 30,
        ptuCapacityTpm: 75000,
        hybridAtAvg: 6200,
      })
    })
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

    const evidence = screen.getByRole('heading', { name: 'Evidence' })
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
  it('shows directional economic message when avg TPM is well above break-even', async () => {
    setupMockFetch()
    // Default mock: avg_tpm=12345, break_even_tpm=8200 → ~50% above → positive
    await runDemoAnalysis()

    const callouts = await screen.findAllByText(/economic signal favors PTU/i)
    const callout = callouts.find(el => el.classList.contains('break-even-callout'))!
    expect(callout).toBeInTheDocument()
    expect(callout).toHaveClass('tone-positive')
    expect(callout.textContent).toContain('Safety verdict: Safe')
  })

  it('shows directional economic message when avg TPM is below break-even', async () => {
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

    const callouts = await screen.findAllByText(/economic signal favors PAYG/i)
    const callout = callouts.find(el => el.classList.contains('break-even-callout'))!
    expect(callout).toBeInTheDocument()
    expect(callout).toHaveClass('tone-negative')
  })

  it('treats traffic above the upper break-even as favoring PAYG', async () => {
    const base = buildMockResponse()
    setupMockFetch({
      metrics: {
        ...base.metrics,
        avg_tpm: 30000,
      },
      charts: {
        ...base.charts,
        cost_curves: {
          ...base.charts.cost_curves,
          avg_tpm: 30000,
          break_even_tpm: 8200,
          upper_break_even_tpm: 20000,
        },
      },
      cost_analysis: {
        ...base.cost_analysis,
        comparison: {
          ...base.cost_analysis.comparison,
          break_even_tpm: 8200,
          upper_break_even_tpm: 20000,
        },
      },
    })
    await runDemoAnalysis()

    const callouts = await screen.findAllByText(/outside that range.*favors PAYG/i)
    const callout = callouts.find(el => el.classList.contains('break-even-callout'))!
    expect(callout).toHaveClass('tone-negative')
    expect(callout.textContent).toContain('8,200-20,000 TPM')
  })
})

describe('Difference summary', () => {
  it('renders directional savings copy instead of absolute delta only', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const snapshot = await screen.findByRole('region', { name: 'Decision snapshot' })
    expect(within(snapshot).getByText(/PTU saves \$740/i)).toBeInTheDocument()
  })
})

describe('Result DOM isolation and responsive scope', () => {
  it('keeps export markup out of layout and gives deployment scope a wide grid treatment', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const results = await screen.findByRole('region', { name: 'Analysis results' })
    const exportSource = within(results).getByTestId('export-report-source')
    const scopeCard = within(results).getByRole('article', { name: 'Deployment scope' })

    expect(exportSource).toHaveAttribute('hidden')
    expect(scopeCard).toHaveClass('glance-card-scope')
  })
})

describe('Baseline headroom helper', () => {
  it('shows an explore headroom action when a higher viable PTU exists', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    expect(await screen.findByText(/up to 45 PTU still saves more than 5%/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /explore headroom/i })).toBeInTheDocument()
  })
})

describe('Daily cost headline', () => {
  it('renders period total from daily_cost data', async () => {
    setupMockFetch({
      charts: {
        ...buildMockResponse().charts,
        daily_cost: {
          dates: ['2026-02-01', '2026-02-02', '2026-02-03'],
          input_cost: [10, 20, 30],
          output_cost: [5, 10, 15],
          total_cost: [15, 30, 45],
          avg_daily_cost: 30,
          ptu_daily_cost: 100,
        },
      },
    })
    await runDemoAnalysis()

    const widget = await screen.findByRole('region', { name: 'Daily Deployment Cost analytical widget' })
    expect(within(widget).getByText('$90')).toBeInTheDocument()
    expect(within(widget).getByText('period cost')).toBeInTheDocument()
  })
})

/* ────────────────────────────────────────────────────
   PricingSourceBadge (Phase 2.2)
   ──────────────────────────────────────────────────── */

describe('PricingSourceBadge', () => {
  it('renders fallback badge with warning icon when pricing_source is fallback', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'fallback',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    const badge = await screen.findByText(/Fallback pricing/i)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('pricing-badge', 'pricing-badge-fallback')
    // Check for warning icon U+26A0
    expect(badge.textContent).toContain('\u26A0')
  })

  it('renders live badge with checkmark when pricing_source is live', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'live',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    const badge = await screen.findByText(/Live pricing/i)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('pricing-badge', 'pricing-badge-live')
    expect(badge.textContent).toContain('\u2713')
  })

  it('renders cached badge when pricing_source is cached', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'cached',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    const badge = await screen.findByText(/Cached pricing/i)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('pricing-badge', 'pricing-badge-cached')
  })

  it('renders manual badge when pricing_source is manual', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'manual',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    const badge = await screen.findByText(/Custom rates/i)
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('pricing-badge', 'pricing-badge-manual')
    expect(badge.textContent).toContain('\u270E')
  })
})

/* ────────────────────────────────────────────────────
   Fallback warning banner (Phase 2.3)
   ──────────────────────────────────────────────────── */

describe('Fallback warning banner', () => {
  it('shows fallback banner when pricing_source is fallback', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'fallback',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    const banner = await screen.findByRole('alert')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveClass('pricing-fallback-banner')
    expect(banner.textContent).toContain('Using default pricing')
  })

  it('does not show fallback banner when pricing_source is live', async () => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'live',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
        },
      },
    })
    await runDemoAnalysis()

    // Wait for Financial Decision to render
    await screen.findByText('Financial Decision')
    // The fallback banner should not exist
    const banners = screen.queryAllByRole('alert')
    const fallbackBanner = banners.find(el => el.classList.contains('pricing-fallback-banner'))
    expect(fallbackBanner).toBeUndefined()
  })
})

/* ────────────────────────────────────────────────────
   Advanced Pricing collapsible (Phase 2.4)
   ──────────────────────────────────────────────────── */

describe('Advanced Pricing section', () => {
  beforeEach(() => {
    setupMockFetch({
      cost_analysis: {
        ...buildMockResponse().cost_analysis,
        pricing: {
          ...buildMockResponse().cost_analysis.pricing,
          pricing_source: 'fallback',
          pricing_as_of: '2026-03-15T12:00:00Z',
          pricing_currency: 'USD',
          payg_input_rate_per_million: 2.50,
          payg_output_rate_per_million: 10.00,
          ptu_hourly_rate: 1.00,
        },
      },
    })
  })

  it('renders Advanced Pricing as a collapsible details element', async () => {
    await runDemoAnalysis()
    await screen.findByText('Financial Decision')

    const summary = screen.getByText(/Advanced Pricing/i)
    expect(summary).toBeInTheDocument()
    const details = summary.closest('details')
    expect(details).toBeInTheDocument()
    expect(details).toHaveClass('advanced-pricing-section')
  })

  it('contains three number inputs for rate overrides', async () => {
    await runDemoAnalysis()
    await screen.findByText('Financial Decision')

    // Open the details
    fireEvent.click(screen.getByText(/Advanced Pricing/i))

    expect(screen.getByText('PAYG Input Rate ($/1M tokens)')).toBeInTheDocument()
    expect(screen.getByText('PAYG Output Rate ($/1M tokens)')).toBeInTheDocument()
    expect(screen.getByText('PTU Hourly Rate ($/PTU/hr)')).toBeInTheDocument()
  })

  it('shows a concise pricing term while preserving the full commitment description', async () => {
    await runDemoAnalysis()
    await screen.findByText('Financial Decision')

    const select = screen.getByRole('combobox', { name: /PTU Pricing Term/i })
    expect(select).toHaveValue('Monthly Commitment (Estimated 64% off)')
    expect(within(select).getByRole('option', { name: 'Monthly · Est. 64% off' })).toBeInTheDocument()
    expect(select).toHaveAttribute('title', 'Monthly Commitment (Estimated 64% off)')
    expect(select).toHaveAccessibleDescription('Selected term: Monthly Commitment (Estimated 64% off)')
  })

  it('shows Reset button only when overrides are entered', async () => {
    await runDemoAnalysis()
    await screen.findByText('Financial Decision')

    fireEvent.click(screen.getByText(/Advanced Pricing/i))

    // Initially no reset button
    expect(screen.queryByText('Reset to auto-resolved rates')).not.toBeInTheDocument()

    // Enter a value in the first input
    const inputs = screen.getAllByRole('spinbutton')
    const advancedInputs = inputs.filter(el => {
      const label = el.closest('label')
      return label && label.textContent?.includes('$/1M tokens')
    })
    expect(advancedInputs.length).toBeGreaterThan(0)

    fireEvent.change(advancedInputs[0], { target: { value: '5.00' } })

    await waitFor(() => {
      expect(screen.getByText('Reset to auto-resolved rates')).toBeInTheDocument()
    })
  })
})

describe('Prompt cache benefit', () => {
  it('renders cache evidence and chart from observed telemetry', async () => {
    setupMockFetch()
    await runDemoAnalysis()

    const cacheVolume = await screen.findByRole('region', { name: 'Prompt Cache Volume analytical widget' })
    const cacheEfficiency = screen.getByRole('region', { name: 'Cache Efficiency analytical widget' })

    expect(within(cacheVolume).getByText('Prompt Cache Volume')).toBeInTheDocument()
    expect(within(cacheEfficiency).getByText('Cache Efficiency')).toBeInTheDocument()
    expect(within(cacheEfficiency).getByRole('list', { name: 'Cache efficiency facts' })).toHaveTextContent('94.6%')
    expect(within(cacheEfficiency).getByRole('list', { name: 'Cache efficiency facts' })).toHaveTextContent('5 PTU')
    expect(within(cacheEfficiency).getByRole('list', { name: 'Cache efficiency facts' })).toHaveTextContent('Observed')
    expect(screen.queryByTestId('cache-impact-strip')).not.toBeInTheDocument()
  })

  it('sends an explicit cache override in the next analysis request', async () => {
    setupMockFetch()
    await runDemoAnalysis()
    await screen.findByRole('region', { name: 'Cache Efficiency analytical widget' })

    fireEvent.click(screen.getByText(/Advanced Pricing/i))
    fireEvent.change(screen.getByLabelText(/Cache calculation mode/i), {
      target: { value: 'override' },
    })
    fireEvent.change(screen.getByLabelText(/Assumed cache match rate/i), {
      target: { value: '40' },
    })

    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls
      const request = [...calls].reverse().find(([url]) => String(url).includes('/api/analyze'))
      expect(request).toBeDefined()
      const body = JSON.parse(String((request?.[1] as RequestInit).body))
      expect(body.cache_mode).toBe('override')
      expect(body.cache_match_rate_override_pct).toBe(40)
    })
  })

  it('waits for a cache rate before submitting override mode', async () => {
    setupMockFetch()
    await runDemoAnalysis()
    await screen.findByRole('region', { name: 'Cache Efficiency analytical widget' })
    const callsBeforeOverride = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([url]) => String(url).includes('/api/analyze'),
    ).length

    fireEvent.click(screen.getByText(/Advanced Pricing/i))
    fireEvent.change(screen.getByLabelText(/Cache calculation mode/i), {
      target: { value: 'override' },
    })
    await new Promise(resolve => setTimeout(resolve, 350))

    const callsAfterOverride = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([url]) => String(url).includes('/api/analyze'),
    ).length
    expect(callsAfterOverride).toBe(callsBeforeOverride)
  })

  it('labels limited cache evidence as contextual and unapplied', async () => {
    const base = buildMockResponse()
    setupMockFetch({
      cost_analysis: {
        ...base.cost_analysis,
        cache_impact: {
          ...base.cost_analysis.cache_impact,
          applied: false,
          quality: 'limited',
          coverage_pct: 35,
          ptu_avoided: 0,
          normalized_tpm_reduction_pct: 0,
        },
      },
    })
    await runDemoAnalysis()

    const warning = await screen.findByRole('alert', { name: 'Cache telemetry warning' })
    expect(warning).toHaveTextContent(/limited cache evidence is contextual only/i)
  })

  it('keeps unavailable cache telemetry prominent and excludes it from sizing', async () => {
    const base = buildMockResponse()
    setupMockFetch({
      cost_analysis: {
        ...base.cost_analysis,
        cache_impact: {
          ...base.cost_analysis.cache_impact,
          applied: false,
          source: 'unavailable',
          quality: 'limited',
          coverage_pct: 0,
          ptu_avoided: 0,
          normalized_tpm_reduction_pct: 0,
        },
      },
    })
    await runDemoAnalysis()

    const warning = await screen.findByRole('alert', { name: 'Cache telemetry warning' })
    expect(warning).toHaveTextContent(/cache telemetry unavailable/i)
    expect(warning).toHaveTextContent(/assumes no cache benefit/i)
  })
})

describe('PTU Calculator prompt cache input', () => {
  it('uses the 720-hour month convention for fixed PTU cost', () => {
    setupMockFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'PTU Calculator' }))

    const onDemandFullPtuRow = screen.getAllByRole('row').find(row =>
      row.textContent?.includes('Full PTU') && row.textContent?.includes('On-Demand'),
    )

    expect(onDemandFullPtuRow).toBeDefined()
    expect(within(onDemandFullPtuRow!).getByText('$79,200')).toBeInTheDocument()
  })

  it('shows break-even TPM for every commitment term', () => {
    setupMockFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'PTU Calculator' }))

    const breakEvenCard = screen
      .getByText('Break-Even TPM by Commitment')
      .closest('.calc-detail-card')

    expect(breakEvenCard).toBeInstanceOf(HTMLElement)
    const breakEvenDetails = within(breakEvenCard as HTMLElement)
    expect(breakEvenDetails.getByText('On-Demand')).toBeInTheDocument()
    expect(breakEvenDetails.getByText('1-Year')).toBeInTheDocument()
    expect(breakEvenDetails.getByText('3-Year')).toBeInTheDocument()
  })

  it('exposes a cache-match slider and fixed-cost clarification', () => {
    setupMockFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'PTU Calculator' }))

    expect(screen.getByText(/Prompt Cache Match:/i)).toBeInTheDocument()
    expect(screen.getByText(/fixed PTU cost changes only when fewer units are selected/i)).toBeInTheDocument()
    expect(screen.getByText('Break-Even TPM by Commitment')).toBeInTheDocument()
  })

  it('uses Data Zone cached-input pricing in the blended rate', () => {
    setupMockFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'PTU Calculator' }))

    const cacheLabel = screen.getByText(/Prompt Cache Match:/i).closest('label')!
    fireEvent.change(cacheLabel.querySelector('input[type="range"]')!, {
      target: { value: '100' },
    })
    fireEvent.change(screen.getByLabelText('Deployment Type'), {
      target: { value: 'data_zone' },
    })

    const blendedRate = screen.getByText('PAYG Blended Rate').closest('.calc-detail-card')!
    expect(blendedRate).toHaveTextContent('$5.23/1M')
  })
})
