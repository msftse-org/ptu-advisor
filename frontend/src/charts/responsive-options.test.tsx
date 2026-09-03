import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'

const { chartRenderMock } = vi.hoisted(() => ({
  chartRenderMock: vi.fn((props: { option: unknown }) => {
    void props
    return null
  }),
}))

vi.mock('echarts-for-react/lib/core', () => ({
  default: chartRenderMock,
  __esModule: true,
}))

import { CostCurveChart } from './CostCurveChart'
import { DailyCostChart } from './DailyCostChart'
import { CacheEfficiencyChart, PromptCacheVolumeChart } from './PromptCacheChart'
import { TpmBandChart } from './TpmBandChart'
import { PTU_CHART_THEME } from './theme'

const zoomState = {
  range: [0, 100] as [number, number],
  isDirty: false,
  windowStart: null,
  windowEnd: null,
}

type ResponsiveOption = {
  media?: Array<{
    query: { maxWidth: number }
    option: {
      grid: { left: number; right: number; containLabel: boolean }
      legend: { type: string; left: number; right: number }
      xAxis?: { axisLabel?: { showMaxLabel?: boolean; hideOverlap?: boolean } }
      series?: Array<{
        markLine?: { data?: Array<{ label?: { show?: boolean } }> }
        markArea?: { label?: { show?: boolean } }
      }>
    }
  }>
  tooltip?: { formatter?: (params: never) => string }
}

function latestOption(): ResponsiveOption {
  return chartRenderMock.mock.calls.at(-1)?.[0].option as ResponsiveOption
}

function compactOption(option: ResponsiveOption) {
  const media = option.media?.find(({ query }) => query.maxWidth === 560)
  expect(media).toBeDefined()
  expect(media?.option.grid).toMatchObject({ left: 8, right: 8, containLabel: true })
  expect(media?.option.legend).toMatchObject({ type: 'scroll', left: 8, right: 8 })
  expect(media?.option.xAxis?.axisLabel).toMatchObject({ showMaxLabel: true, hideOverlap: true })
  return media!.option
}

describe('compact ECharts options', () => {
  beforeEach(() => {
    chartRenderMock.mockClear()
  })

  it('contains axis labels in the shared theme', () => {
    expect(PTU_CHART_THEME.grid.containLabel).toBe(true)
    compactOption(PTU_CHART_THEME as ResponsiveOption)
  })

  it('uses scrolling legends and contained grids for both prompt cache charts', () => {
    const { rerender } = render(
      <PromptCacheVolumeChart
        timestamps={['2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z']}
        cachedPromptTokens={[5_400, 6_100]}
        activePromptTokens={[4_600, 3_900]}
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp="2026-08-02T00:00:00Z"
      />,
    )

    compactOption(latestOption())

    rerender(
      <CacheEfficiencyChart
        timestamps={['2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z']}
        matchRatePct={[54, 61]}
        source="observed"
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp="2026-08-02T00:00:00Z"
      />,
    )

    compactOption(latestOption())
  })

  it('hides daily-cost reference labels on compact charts and keeps full values in the tooltip', () => {
    render(
      <DailyCostChart
        timestamps={['2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z']}
        inputCost={[120, 140]}
        outputCost={[80, 90]}
        avgDailyCost={215}
        ptuDailyCost={480}
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp={null}
      />,
    )

    const option = latestOption()
    const compact = compactOption(option)
    const compactMarkLines = compact.series?.[1]?.markLine?.data ?? []
    expect(compactMarkLines.every(({ label }) => label?.show === false)).toBe(true)

    const tooltip = option.tooltip?.formatter?.([
      { seriesName: 'Input Cost', value: 120, marker: '' },
    ] as never)
    expect(tooltip).toContain('Average daily reference: $215')
    expect(tooltip).toContain('PTU daily reference: $480')
  })

  it('hides cost-curve reference labels on compact charts and keeps full values in the tooltip', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 10_000, 20_000]}
        payg={[0, 2_000, 4_000]}
        hybrid={[1_000, 1_000, 1_500]}
        breakEvenTpm={8_000}
        upperBreakEvenTpm={40_000}
        breakEvenCost={1_000}
        ptuFixedMonthly={1_000}
        ptuCapacityTpm={15_000}
        avgTpm={12_000}
        selectedPtu={15}
        paygAtAvg={2_400}
        hybridAtAvg={1_000}
        height={300}
      />,
    )

    const option = latestOption()
    const compact = compactOption(option)
    const compactMarkLines = compact.series?.[0]?.markLine?.data ?? []
    expect(compactMarkLines.every(({ label }) => label?.show === false)).toBe(true)
    expect(compact.series?.[0]?.markArea).toBeUndefined()

    const tooltip = option.tooltip?.formatter?.([
      { seriesName: 'PAYG', value: [10_000, 2_000], marker: '' },
    ] as never)
    expect(tooltip).toContain('Lower break-even: 8.0K TPM')
    expect(tooltip).toContain('Upper break-even: 40.0K TPM')
    expect(tooltip).toContain('15 PTU capacity: 15.0K TPM')
  })

  it('hides TPM-band reference labels on compact charts and keeps full values in the tooltip', () => {
    render(
      <TpmBandChart
        timestamps={['2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z']}
        tpm={[10_000, 14_000]}
        avg={12_000}
        refLine={18_000}
        refLabel="P95"
        upperRefLine={24_000}
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp={null}
      />,
    )

    const option = latestOption()
    const compact = compactOption(option)
    const compactReferenceSeries = compact.series?.slice(1) ?? []
    expect(compactReferenceSeries).toHaveLength(2)
    for (const series of compactReferenceSeries) {
      const markers = series.markLine?.data ?? []
      expect(markers.every(({ label }) => label?.show === false)).toBe(true)
    }

    const tooltip = option.tooltip?.formatter?.([
      { seriesName: 'TPM', value: 14_000, marker: '', axisValue: '2026-08-02T00:00:00Z' },
    ] as never)
    expect(tooltip).toContain('Avg: 12,000')
    expect(tooltip).toContain('P95: 18,000')
    expect(tooltip).toContain('Upper: 24,000')
  })
})