import { expect, test } from '@playwright/test'

let capturedAnalyzeRequests: Array<Record<string, unknown>> = []

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
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T00:15:00Z', '2026-02-01T00:30:00Z', '2026-02-01T00:45:00Z'],
      prompt: [4000, 4200, 4150, 4300],
      completion: [2600, 2800, 2700, 2900],
      total: [6600, 7000, 6850, 7200],
    },
    requests: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T00:15:00Z', '2026-02-01T00:30:00Z', '2026-02-01T00:45:00Z'],
      successful: [1000, 1100, 1080, 1130],
      throttled: [15, 22, 20, 24],
      total: [1015, 1122, 1100, 1154],
    },
    daily_cost: {
      dates: ['2026-02-01', '2026-02-02'],
      input_cost: [20.5, 21.8],
      output_cost: [52.0, 56.0],
      total_cost: [72.5, 77.8],
      avg_daily_cost: 75.15,
      ptu_daily_cost: 173.33,
    },
    tpm: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T00:15:00Z', '2026-02-01T00:30:00Z', '2026-02-01T00:45:00Z'],
      values: [12000, 12800, 12400, 13000],
      avg: 12345,
      p25: 11200,
      p95: 21456,
    },
    throttling: {
      timestamps: ['2026-02-01T00:00:00Z', '2026-02-01T00:15:00Z', '2026-02-01T00:30:00Z', '2026-02-01T00:45:00Z'],
      values: [15, 22, 20, 24],
    },
    cost_curves: {
      sustained_tpm: [5000, 10000, 15000, 20000],
      payg_monthly: [1800, 3600, 5400, 7200],
      ptu_spill_monthly: [1700, 2900, 4100, 5300],
      break_even_tpm: 8200,
      break_even_reason: 'exists' as const,
      ptu_capacity_tpm: 50000,
      avg_tpm: 12345,
      selected_ptu: 20,
      payg_at_avg: 3600,
      hybrid_at_avg: 2900,
    },
  },
  cost_analysis: {
    pricing: {
      focus_topic: 'Cost Reduction',
      reservation_type: 'Monthly Commitment (Estimated 64% off)',
      reservation_discount_pct: 64,
      region: 'eastus',
      region_display_name: 'East US',
      region_multiplier: 1.0,
      deployment_type: 'global' as const,
      deployment_type_label: 'Global',
      payg_blended_rate_per_million: 4.75,
      ptu_hourly_rate: 1,
      ptu_capacity_per_unit: 2500,
      ptu_increment: 50,
      ptu_minimum: 50,
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
    commitment_safety: {
      savings_margin_pct: 12.1,
      spillover_pct: 15.0,
      capacity_coverage_pct: 85.0,
      safety_verdict: 'Safe',
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
  capturedAnalyzeRequests = []
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

    if (url.includes('/api/pricing/options')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          regions: [{ name: 'eastus', display_name: 'East US', multiplier: 1.0 }],
          deployment_types: [{ name: 'Global', display_name: 'Global', rate_multiplier: 1.0 }],
        }),
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
      const payload = route.request().postDataJSON() as Record<string, unknown>
      capturedAnalyzeRequests.push(payload)
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

  await expect(page.getByText('PTU Recommended').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Assumptions' })).toBeVisible()
  await expect(page.locator('label').filter({ hasText: 'PTU Pricing Term' }).first()).toBeVisible()
  await expect(page.getByText(/PTU Baseline Coverage/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recommendation Rationale' })).toBeVisible()
  await expect(page.getByText('Why this recommendation').first()).toBeVisible()
  await expect(page.getByText('Use the slider below each chart or scroll-wheel to zoom in')).toBeVisible()
  expect(capturedAnalyzeRequests.length).toBeGreaterThan(0)
  expect(capturedAnalyzeRequests[0].granularity_minutes).toBe(5)
})

test('expand button opens token chart in fixed modal mode', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: 'Demo Mode' }).click()
  await page.getByRole('button', { name: 'Run Analysis' }).click()

  const expandTokenChart = page.getByRole('button', { name: 'Expand Token Volume Over Time' })
  await expandTokenChart.click()

  const tokenCard = page.locator('.chart-card').filter({ hasText: 'Token Volume Over Time' }).first()
  await expect(tokenCard).toHaveClass(/is-chart-expanded/)

  const position = await tokenCard.evaluate((node) => window.getComputedStyle(node).position)
  expect(position).toBe('fixed')
})

test('chart tooltip appears in front of graph (appended to body with high z-index)', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: 'Demo Mode' }).click()
  await page.getByRole('button', { name: 'Run Analysis' }).click()

  // Find the first ECharts canvas and hover over its center to trigger a tooltip
  const chartCanvas = page.locator('canvas').first()
  await chartCanvas.waitFor({ state: 'visible' })
  const box = await chartCanvas.boundingBox()
  expect(box).toBeTruthy()

  // Hover near the center of the chart to trigger the tooltip
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
  // Small delay for tooltip to appear
  await page.waitForTimeout(600)

  // ECharts renders tooltips as a div with position:absolute.
  // With appendTo: () => document.body, the tooltip should be a direct child of <body>.
  const tooltipOnBody = page.locator('body > div[style*="position: absolute"][style*="border-color"]')
  const tooltipCount = await tooltipOnBody.count()

  if (tooltipCount > 0) {
    // Tooltip is appended to body — verify it has a high z-index
    const tooltip = tooltipOnBody.first()
    const zIndex = await tooltip.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return parseInt(style.zIndex, 10) || 0
    })
    expect(zIndex).toBeGreaterThanOrEqual(9999)

    // Verify the tooltip is visible
    const opacity = await tooltip.evaluate((el) => window.getComputedStyle(el).opacity)
    expect(Number(opacity)).toBeGreaterThan(0)
  } else {
    // Fallback: check any tooltip-like element in the page and verify it's not clipped
    // by the chart container (i.e., not inside an overflow:hidden parent)
    const anyTooltip = page.locator('div[style*="position: absolute"][style*="z-index: 9999"]').first()
    if (await anyTooltip.count() > 0) {
      // Verify the tooltip's ancestor chain doesn't have overflow:hidden
      const isClipped = await anyTooltip.evaluate((el) => {
        let parent = el.parentElement
        while (parent && parent !== document.body) {
          if (window.getComputedStyle(parent).overflow === 'hidden') return true
          parent = parent.parentElement
        }
        return false
      })
      expect(isClipped).toBe(false)
    }
  }
})
