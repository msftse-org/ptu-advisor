import { expect, test } from '@playwright/test'

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
    },
    payg: {
      monthly_tokens: 99000000,
      payg_base: 470,
      throttle_impact: 120,
      payg_total: 590,
    },
    hybrid: {
      baseline_percentile: 75,
      baseline_label: 'P75',
      baseline_tpm: 10000,
      baseline_ptu: 20,
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

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()

    if (url.includes('/api/focus-topics')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ name: 'Cost Reduction', tagline: 'Tagline' }]),
      })
      return
    }

    if (url.includes('/api/discovery/subscriptions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
      return
    }

    if (url.includes('/api/analyze')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAnalysisResponse),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })
})

test('demo flow renders second page with expected controls and context', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: 'Demo Mode' }).click()
  await page.getByRole('button', { name: 'Run Analysis' }).click()

  await expect(page.getByText('PTU RECOMMENDED')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Cost Assumptions' })).toBeVisible()
  await expect(page.getByText('PTU Pricing Term')).toBeVisible()
  await expect(page.getByText('PTU Baseline Coverage (P75)')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recommendation Context' })).toBeVisible()
  await expect(page.getByText('Why this recommendation')).toBeVisible()
  await expect(page.getByText('interactive chart: hover for exact values and drag the bottom range bar to zoom.', { exact: false })).toBeVisible()
})
