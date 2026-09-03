import type { ComponentType } from 'react'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import * as promptCacheCharts from './PromptCacheChart'

const timestamps = ['2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z']
const zoomState = {
  range: [18, 76] as [number, number],
  isDirty: true,
  windowStart: timestamps[0],
  windowEnd: timestamps[1],
}

type SharedProps = {
  timestamps: string[]
  height: number
  zoomState: typeof zoomState
  onDataZoom: (params: { start?: number; end?: number }) => void
  selectedTimestamp: string | null
}

type VolumeProps = SharedProps & {
  cachedPromptTokens: number[]
  activePromptTokens: number[]
}

type EfficiencyProps = SharedProps & {
  matchRatePct: Array<number | null>
  source: string
  perDeployment?: Record<string, {
    match_rate_pct: Array<number | null>
    source: 'observed' | 'inferred' | 'mixed' | 'unavailable'
  }>
}

const chartModule = promptCacheCharts as unknown as {
  PromptCacheVolumeChart?: ComponentType<VolumeProps>
  CacheEfficiencyChart?: ComponentType<EfficiencyProps>
}

type ChartOption = {
  xAxis: { data: string[] }
  yAxis: { name: string; min?: number; max?: number } | Array<{ name: string; min?: number; max?: number }>
  dataZoom: Array<{ start: number; end: number }>
  series: Array<{ name: string; markLine?: { data: Array<{ xAxis: string }> } }>
  media?: Array<{ query: { maxWidth: number } }>
  tooltip: { formatter: (params: Array<{ dataIndex: number }>) => string }
}

type ChartRenderProps = {
  option: ChartOption
  onEvents: { datazoom: SharedProps['onDataZoom'] }
}

function latestChartProps(): ChartRenderProps {
  return chartRenderMock.mock.calls.at(-1)?.[0] as ChartRenderProps
}

describe('coordinated prompt cache charts', () => {
  beforeEach(() => {
    chartRenderMock.mockClear()
  })

  it('renders token volume on one prompt-token axis without cache-rate series', () => {
    const PromptCacheVolumeChart = chartModule.PromptCacheVolumeChart
    expect(PromptCacheVolumeChart, 'PromptCacheVolumeChart export is required').toBeTypeOf('function')
    if (!PromptCacheVolumeChart) return

    render(
      <PromptCacheVolumeChart
        timestamps={timestamps}
        cachedPromptTokens={[5_400, 6_100]}
        activePromptTokens={[4_600, 3_900]}
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp={timestamps[1]}
      />,
    )

    const option = latestChartProps().option
    expect(screen.getByRole('img', { name: 'Active and cached prompt token volume over time' })).toHaveAccessibleDescription(/11,500 cached prompt tokens.*8,500 active prompt tokens/i)
    expect(Array.isArray(option.yAxis)).toBe(false)
    expect(option.yAxis).toMatchObject({ name: 'Prompt tokens' })
    expect(option.series.map(({ name }) => name)).toEqual(['Active prompt tokens', 'Cached prompt tokens'])
    expect(option.series.some(({ name }) => /cache match|cache \(/i.test(name))).toBe(false)
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('Cached prompt tokens: 6,100')
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('Active prompt tokens: 3,900')
  })

  it('renders cache efficiency on one 0–100% axis without token-volume series', () => {
    const CacheEfficiencyChart = chartModule.CacheEfficiencyChart
    expect(CacheEfficiencyChart, 'CacheEfficiencyChart export is required').toBeTypeOf('function')
    if (!CacheEfficiencyChart) return

    render(
      <CacheEfficiencyChart
        timestamps={timestamps}
        matchRatePct={[54, 61.8]}
        source="observed"
        height={300}
        zoomState={zoomState}
        onDataZoom={vi.fn()}
        selectedTimestamp={timestamps[1]}
        perDeployment={{
          alpha: { match_rate_pct: [50, 60], source: 'observed' },
        }}
      />,
    )

    const option = latestChartProps().option
    expect(screen.getByRole('img', { name: 'Prompt cache match percentage over time' })).toHaveAccessibleDescription(/54\.0% to 61\.8%/i)
    expect(Array.isArray(option.yAxis)).toBe(false)
    expect(option.yAxis).toMatchObject({ name: 'Cache match', min: 0, max: 100 })
    expect(option.series.map(({ name }) => name)).toEqual(['Cache match', 'alpha cache (observed)'])
    expect(option.series.some(({ name }) => /active prompt|cached prompt/i.test(name))).toBe(false)
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('Cache match rate: 61.8%')
  })

  it('shares timestamps, zoom range, selected timestamp, compact media, and zoom handler', () => {
    const PromptCacheVolumeChart = chartModule.PromptCacheVolumeChart
    const CacheEfficiencyChart = chartModule.CacheEfficiencyChart
    expect(PromptCacheVolumeChart, 'PromptCacheVolumeChart export is required').toBeTypeOf('function')
    expect(CacheEfficiencyChart, 'CacheEfficiencyChart export is required').toBeTypeOf('function')
    if (!PromptCacheVolumeChart || !CacheEfficiencyChart) return

    const onDataZoom = vi.fn()
    const { rerender } = render(
      <PromptCacheVolumeChart
        timestamps={timestamps}
        cachedPromptTokens={[5_400, 6_100]}
        activePromptTokens={[4_600, 3_900]}
        height={300}
        zoomState={zoomState}
        onDataZoom={onDataZoom}
        selectedTimestamp={timestamps[1]}
      />,
    )
    const volumeProps = latestChartProps()

    rerender(
      <CacheEfficiencyChart
        timestamps={timestamps}
        matchRatePct={[54, 61.8]}
        source="observed"
        height={300}
        zoomState={zoomState}
        onDataZoom={onDataZoom}
        selectedTimestamp={timestamps[1]}
      />,
    )
    const efficiencyProps = latestChartProps()

    for (const props of [volumeProps, efficiencyProps]) {
      expect(props.option.xAxis.data).toEqual(timestamps)
      expect(props.option.dataZoom).toEqual(expect.arrayContaining([
        expect.objectContaining({ start: 18, end: 76 }),
      ]))
      expect(props.option.series.some((series) => series.markLine?.data.some(({ xAxis }) => xAxis === timestamps[1]))).toBe(true)
      expect(props.option.media?.some(({ query }) => query.maxWidth === 560)).toBe(true)
      expect(props.onEvents.datazoom).toBe(onDataZoom)
    }
  })
})