import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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

type CostTooltipParam = { seriesName: string; value: number[]; marker: string }

function renderTooltipChart(): (params: CostTooltipParam[]) => string {
  render(
    <CostCurveChart
      sustainedTpm={[0, 128_988, 300_000]}
      payg={[0, 29_188, 67_800]}
      hybrid={[53_284, 53_284, 60_500]}
      breakEvenTpm={235_474}
      upperBreakEvenTpm={709_835}
      breakEvenCost={53_284}
      ptuFixedMonthly={53_284}
      ptuCapacityTpm={256_507}
      avgTpm={128_988}
      selectedPtu={205}
      paygAtAvg={29_188}
      hybridAtAvg={53_284}
      height={300}
    />,
  )

  const option = chartRenderMock.mock.calls.at(-1)![0].option as {
    tooltip: { formatter: (params: CostTooltipParam[]) => string }
  }
  return option.tooltip.formatter
}

describe('CostCurveChart', () => {
  it('plots both cache-aware break-even boundaries and includes the upper boundary in its domain', () => {
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

    expect(chartRenderMock).toHaveBeenCalledTimes(1)
    const option = chartRenderMock.mock.calls[0]![0].option as {
      xAxis: { max: number }
      series: Array<{ markLine?: { data: Array<{ xAxis: number; label: { formatter: string } }> } }>
    }
    const breakEvenMarkers = option.series[0].markLine?.data ?? []

    expect(breakEvenMarkers).toEqual(expect.arrayContaining([
      expect.objectContaining({
        xAxis: 8_000,
        label: expect.objectContaining({ formatter: expect.stringContaining('Lower break-even') }),
      }),
      expect.objectContaining({
        xAxis: 40_000,
        label: expect.objectContaining({ formatter: expect.stringContaining('Upper break-even') }),
      }),
    ]))
    expect(option.xAxis.max).toBeGreaterThan(40_000)
  })

  it('focuses the initial x-axis near the largest decision marker instead of the backend data maximum', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 40_069, 43_631, 121_017, 128_986, 386_957]}
        payg={[0, 9_100, 9_900, 27_480, 29_290, 87_854]}
        hybrid={[8_900, 8_900, 8_900, 26_900, 29_100, 90_634]}
        breakEvenTpm={40_069}
        upperBreakEvenTpm={121_017}
        breakEvenCost={9_100}
        ptuFixedMonthly={8_900}
        ptuCapacityTpm={43_631}
        avgTpm={128_986}
        selectedPtu={35}
        paygAtAvg={29_290}
        hybridAtAvg={29_100}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      xAxis: { max: number }
    }

    expect(option.xAxis.max).toBeGreaterThan(128_986)
    expect(option.xAxis.max).toBeGreaterThan(121_017)
    expect(option.xAxis.max).toBeGreaterThan(43_631)
    expect(option.xAxis.max).toBeGreaterThan(40_069)
    expect(option.xAxis.max).toBeGreaterThanOrEqual(150_000)
    expect(option.xAxis.max).toBeLessThanOrEqual(165_000)
    expect(option.xAxis.max).toBeLessThan(200_000)
  })

  it('sets a nice y-axis ceiling from visible line costs including the interpolated x-axis endpoint', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 40_069, 43_631, 121_017, 128_986, 386_957]}
        payg={[0, 9_100, 9_900, 27_480, 29_290, 87_854]}
        hybrid={[8_900, 8_900, 8_900, 26_900, 29_100, 90_634]}
        breakEvenTpm={40_069}
        upperBreakEvenTpm={121_017}
        breakEvenCost={9_100}
        ptuFixedMonthly={8_900}
        ptuCapacityTpm={43_631}
        avgTpm={128_986}
        selectedPtu={35}
        paygAtAvg={29_290}
        hybridAtAvg={29_100}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      xAxis: { max: number }
      yAxis: { min: number; max: number }
    }
    const endpointRatio = (option.xAxis.max - 128_986) / (386_957 - 128_986)
    const visiblePaygEndpoint = 29_290 + (87_854 - 29_290) * endpointRatio
    const visibleHybridEndpoint = 29_100 + (90_634 - 29_100) * endpointRatio

    expect(option.yAxis.min).toBe(0)
    expect(option.yAxis.max).toBe(40_000)
    expect(option.yAxis.max).toBeGreaterThan(Math.max(visiblePaygEndpoint, visibleHybridEndpoint))
    expect(option.yAxis.max).toBeLessThan(60_000)
  })

  it('keeps a remote upper crossing out of the initial oversized-commitment domain', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 128_988, 235_474, 256_507, 709_835, 851_802]}
        payg={[0, 29_188, 53_284, 58_044, 160_700, 192_800]}
        hybrid={[53_284, 53_284, 53_284, 53_284, 160_700, 197_000]}
        breakEvenTpm={235_474}
        upperBreakEvenTpm={709_835}
        breakEvenCost={53_284}
        ptuFixedMonthly={53_284}
        ptuCapacityTpm={256_507}
        avgTpm={128_988}
        selectedPtu={205}
        paygAtAvg={29_188}
        hybridAtAvg={53_284}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      xAxis: { max: number }
      yAxis: { min: number; max: number }
      series: Array<{ markLine?: { data: Array<{ xAxis?: number }> } }>
    }
    const visibleReferenceLines = option.series[0].markLine?.data ?? []

    expect(option.xAxis.max).toBeGreaterThan(256_507)
    expect(option.xAxis.max).toBeLessThanOrEqual(330_000)
    expect(option.yAxis.min).toBe(0)
    expect(option.yAxis.max).toBeGreaterThan(53_284)
    expect(option.yAxis.max).toBeLessThan(100_000)
    expect(visibleReferenceLines).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ xAxis: 709_835 }),
    ]))
  })

  it.each([
    {
      paygAtAvg: 29_188,
      hybridAtAvg: 53_284,
      expectedLabel: 'PTU +$24.1K/mo',
    },
    {
      paygAtAvg: 53_284,
      hybridAtAvg: 29_188,
      expectedLabel: 'PTU saves $24.1K/mo',
    },
  ])('marks the exact current-workload cost gap as "$expectedLabel" without legend or tooltip leakage', ({ paygAtAvg, hybridAtAvg, expectedLabel }) => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 128_988, 235_474, 256_507, 709_835, 851_802]}
        payg={[0, 29_188, 53_284, 58_044, 160_700, 192_800]}
        hybrid={[53_284, 53_284, 53_284, 53_284, 160_700, 197_000]}
        breakEvenTpm={235_474}
        upperBreakEvenTpm={709_835}
        breakEvenCost={53_284}
        ptuFixedMonthly={53_284}
        ptuCapacityTpm={256_507}
        avgTpm={128_988}
        selectedPtu={205}
        paygAtAvg={paygAtAvg}
        hybridAtAvg={hybridAtAvg}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      legend: { data: string[] }
      series: Array<{
        name: string
        markLine?: {
          silent: boolean
          tooltip: { show: boolean }
          label: { show: boolean; formatter: string }
          data: Array<Array<{ coord: [number, number] }>>
        }
      }>
      media: Array<{
        query: { maxWidth: number }
        option: { series?: Array<{ markLine?: { label?: { show?: boolean } } }> }
      }>
    }
    const ptuSeries = option.series.find((series) => series.name === 'PTU + Spillover')
    const costGap = ptuSeries?.markLine

    expect(costGap).toMatchObject({
      silent: true,
      tooltip: { show: false },
      label: { show: true, formatter: expectedLabel },
      data: [[
        { coord: [128_988, paygAtAvg] },
        { coord: [128_988, hybridAtAvg] },
      ]],
    })
    expect(option.legend.data).toEqual(['PAYG', 'PTU + Spillover'])
    const compactPtuSeries = option.media.find(({ query }) => query.maxWidth === 560)?.option.series?.[1]
    expect(compactPtuSeries?.markLine?.label?.show).toBe(false)
  })

  it('uses the data maximum for both axes when there are no decision markers', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 10, 20]}
        payg={[0, 100, 200]}
        hybrid={[50, 50, 150]}
        breakEvenTpm={null}
        upperBreakEvenTpm={null}
        breakEvenCost={null}
        ptuFixedMonthly={50}
        ptuCapacityTpm={0}
        avgTpm={0}
        selectedPtu={30}
        paygAtAvg={0}
        hybridAtAvg={0}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      xAxis: { max: number }
      yAxis: { min: number; max: number }
    }

    expect(option.xAxis.max).toBe(20)
    expect(option.yAxis).toMatchObject({ min: 0, max: 250 })
  })

  it.each([
    { sustainedTpm: [], payg: [], hybrid: [] },
    { sustainedTpm: [0], payg: [0], hybrid: [] },
    { sustainedTpm: [0, 10, 20], payg: [0, 100], hybrid: [50] },
  ])('keeps the y-axis finite for empty, zero, short, or misaligned line arrays', ({ sustainedTpm, payg, hybrid }) => {
    render(
      <CostCurveChart
        sustainedTpm={sustainedTpm}
        payg={payg}
        hybrid={hybrid}
        breakEvenTpm={null}
        upperBreakEvenTpm={null}
        breakEvenCost={null}
        ptuFixedMonthly={50}
        ptuCapacityTpm={0}
        avgTpm={0}
        selectedPtu={30}
        paygAtAvg={0}
        hybridAtAvg={0}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      yAxis: { min: number; max: number }
    }

    expect(option.yAxis.min).toBe(0)
    expect(Number.isFinite(option.yAxis.max)).toBe(true)
    expect(option.yAxis.max).toBeGreaterThan(0)
  })

  it('marks the bounded PTU-favorable savings window without exposing internal series in tooltips', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 10_000, 20_000, 40_000]}
        payg={[0, 2_000, 4_000, 8_000]}
        hybrid={[1_000, 1_000, 1_500, 8_000]}
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

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      tooltip: { formatter: (params: Array<{ seriesName: string; value: number[]; marker: string }>) => string }
      series: Array<{
        name: string
        markArea?: {
          silent: boolean
          tooltip: { show: boolean }
          itemStyle: { color: string }
          label: { show: boolean; formatter: string }
          data: Array<[{ name: string; xAxis: number }, { xAxis: number }]>
        }
      }>
    }
    const paygSeries = option.series.find((series) => series.name === 'PAYG')

    expect(paygSeries?.markArea).toEqual(expect.objectContaining({
      silent: true,
      tooltip: { show: false },
      itemStyle: { color: 'rgba(0, 212, 170, 0.08)' },
      label: expect.objectContaining({ show: true, formatter: 'PTU savings window' }),
      data: [[
        expect.objectContaining({ name: 'PTU-favorable savings window', xAxis: 8_000 }),
        expect.objectContaining({ xAxis: 40_000 }),
      ]],
    }))

    const tooltip = option.tooltip.formatter([
      { seriesName: '_savings_fill', value: [10_000, 1_500], marker: 'internal-marker' },
      { seriesName: 'PAYG', value: [10_000, 2_000], marker: 'payg-marker' },
    ])
    expect(tooltip).not.toContain('_savings_fill')
    expect(tooltip).not.toContain('internal-marker')
    expect(tooltip).toContain('PAYG')
  })

  it('caps and wraps the body-appended tooltip on narrow viewports', () => {
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

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      tooltip: { extraCssText: string }
    }

    expect(option.tooltip.extraCssText).toContain('max-width: min(360px, 75vw)')
    expect(option.tooltip.extraCssText).toContain('box-sizing: border-box')
    expect(option.tooltip.extraCssText).toContain('white-space: normal')
    expect(option.tooltip.extraCssText).toContain('overflow-wrap: anywhere')
  })

  it('extends the PTU-favorable savings window to the focused domain when there is no upper boundary', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 10, 30, 100]}
        payg={[0, 200, 600, 2_000]}
        hybrid={[100, 100, 400, 1_000]}
        breakEvenTpm={5}
        upperBreakEvenTpm={null}
        breakEvenCost={100}
        ptuFixedMonthly={100}
        ptuCapacityTpm={30}
        avgTpm={20}
        selectedPtu={15}
        paygAtAvg={400}
        hybridAtAvg={250}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      xAxis: { max: number }
      series: Array<{
        name: string
        markArea?: { data: Array<[{ xAxis: number }, { xAxis: number }]> }
      }>
    }
    const paygSeries = option.series.find((series) => series.name === 'PAYG')

    expect(paygSeries?.markArea?.data[0]?.[0]).toEqual(expect.objectContaining({ xAxis: 5 }))
    expect(paygSeries?.markArea?.data[0]?.[1]).toEqual(expect.objectContaining({ xAxis: option.xAxis.max }))
  })

  it('clips savings polygons to interpolated PAYG-over-hybrid intervals', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 10, 30, 100]}
        payg={[0, 200, 600, 800]}
        hybrid={[100, 100, 400, 1_000]}
        breakEvenTpm={5}
        upperBreakEvenTpm={65}
        breakEvenCost={100}
        ptuFixedMonthly={100}
        ptuCapacityTpm={30}
        avgTpm={20}
        selectedPtu={15}
        paygAtAvg={400}
        hybridAtAvg={250}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      series: Array<{ name: string; data: number[][] }>
    }
    const savingsSeries = option.series.find((series) => series.name === '_savings_fill')

    expect(savingsSeries?.data.map((segment) => segment.slice(0, 2))).toEqual([
      [5, 10],
      [10, 30],
      [30, 65],
    ])
  })

  it('encodes savings polygon coordinates without exposing the internal series in the legend', () => {
    render(
      <CostCurveChart
        sustainedTpm={[0, 40_069, 43_631, 121_017, 128_986, 386_957]}
        payg={[0, 9_100, 9_900, 27_480, 29_290, 87_854]}
        hybrid={[8_900, 8_900, 8_900, 26_900, 29_100, 90_634]}
        breakEvenTpm={40_069}
        upperBreakEvenTpm={121_017}
        breakEvenCost={9_100}
        ptuFixedMonthly={8_900}
        ptuCapacityTpm={43_631}
        avgTpm={128_986}
        selectedPtu={35}
        paygAtAvg={29_290}
        hybridAtAvg={29_100}
        height={300}
      />,
    )

    const option = chartRenderMock.mock.calls.at(-1)![0].option as {
      legend: { data: string[] }
      media: Array<{
        query: { maxWidth: number }
        option: { legend?: { data?: string[] } }
      }>
      series: Array<{
        name: string
        encode?: { x: number[]; y: number[] }
      }>
    }
    const savingsSeries = option.series.find((series) => series.name === '_savings_fill')

    expect(savingsSeries?.encode).toEqual({
      x: [0, 1],
      y: [2, 3, 4, 5],
    })
    expect(option.legend.data).toEqual(['PAYG', 'PTU + Spillover'])
    expect(option.legend.data).not.toContain('_savings_fill')
    const compactLegend = option.media.find(({ query }) => query.maxWidth === 560)?.option.legend
    expect(compactLegend?.data).toEqual(['PAYG', 'PTU + Spillover'])
    expect(compactLegend?.data).not.toContain('_savings_fill')
  })

  it('separates decision context from public price rows while preserving PAYG and omitting internal series', () => {
    const formatter = renderTooltipChart()
    const tooltip = formatter([
      { seriesName: 'PAYG', value: [128_988, 29_188], marker: 'payg-marker' },
      { seriesName: 'PTU + Spillover', value: [128_988, 53_284], marker: 'hybrid-marker' },
      { seriesName: '_savings_fill', value: [128_988, 24_096], marker: 'internal-marker' },
    ])

    const contextIndex = tooltip.indexOf('Your average:')
    const dividerIndex = tooltip.indexOf('cost-tooltip-divider')
    const paygIndex = tooltip.indexOf('payg-marker PAYG: $29,188')

    expect(contextIndex).toBeGreaterThanOrEqual(0)
    expect(dividerIndex).toBeGreaterThan(contextIndex)
    expect(paygIndex).toBeGreaterThan(dividerIndex)
    expect(tooltip).not.toContain('_savings_fill')
    expect(tooltip).not.toContain('internal-marker')
  })

  it('shows the fixed PTU cost with zero spillover at an under-capacity hovered point', () => {
    const formatter = renderTooltipChart()
    const tooltip = formatter([
      { seriesName: 'PTU + Spillover', value: [128_988, 53_284 + 1e-10], marker: 'hybrid-marker' },
    ])

    expect(tooltip).toContain('PTU + Spillover: $53,284 (PTU $53,284 + spillover $0)')
  })

  it('uses the hovered hybrid total for the exact above-capacity spillover breakdown', () => {
    const formatter = renderTooltipChart()
    const tooltip = formatter([
      { seriesName: 'PTU + Spillover', value: [300_000, 60_500], marker: 'hybrid-marker' },
    ])

    expect(tooltip).toContain('PTU + Spillover: $60,500 (PTU $53,284 + spillover $7,216)')
  })
})