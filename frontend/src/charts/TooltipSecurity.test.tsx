import { render } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const { chartRenderMock, echartsMock } = vi.hoisted(() => ({
  chartRenderMock: vi.fn((props: { option: unknown }) => {
    void props
    return null
  }),
  echartsMock: {
    graphic: {
      LinearGradient: vi.fn(),
    },
  },
}))

vi.mock('echarts-for-react/lib/core', () => ({
  default: chartRenderMock,
  __esModule: true,
}))

vi.mock('./echarts-setup', () => ({
  echarts: echartsMock,
}))

let LatencyOverlayChart!: typeof import('./LatencyOverlayChart').LatencyOverlayChart
let CacheEfficiencyChart!: typeof import('./PromptCacheChart').CacheEfficiencyChart
let RequestOutcomesChart!: typeof import('./RequestOutcomesChart').RequestOutcomesChart
let ThrottleChart!: typeof import('./ThrottleChart').ThrottleChart
let TokenVolumeChart!: typeof import('./TokenVolumeChart').TokenVolumeChart
let TpmBandChart!: typeof import('./TpmBandChart').TpmBandChart

beforeAll(async () => {
  const [latency, cache, outcomes, throttle, tokenVolume, tpmBand] = await Promise.all([
    import('./LatencyOverlayChart'),
    import('./PromptCacheChart'),
    import('./RequestOutcomesChart'),
    import('./ThrottleChart'),
    import('./TokenVolumeChart'),
    import('./TpmBandChart'),
  ])

  LatencyOverlayChart = latency.LatencyOverlayChart
  CacheEfficiencyChart = cache.CacheEfficiencyChart
  RequestOutcomesChart = outcomes.RequestOutcomesChart
  ThrottleChart = throttle.ThrottleChart
  TokenVolumeChart = tokenVolume.TokenVolumeChart
  TpmBandChart = tpmBand.TpmBandChart
})

const timestamps = ['2026-08-01T00:00:00Z']
const zoomState = {
  range: [0, 100] as [number, number],
  isDirty: false,
  windowStart: timestamps[0],
  windowEnd: timestamps[0],
}
const sharedProps = {
  timestamps,
  height: 300,
  zoomState,
  onDataZoom: vi.fn(),
  selectedTimestamp: null,
}
const hostileName = '<img src=x onerror=alert(1)> & "quotes" \'single\''
const escapedName = '&lt;img src=x onerror=alert(1)&gt; &amp; &quot;quotes&quot; &#39;single&#39;'
const marker = '<span class="echarts-marker"></span>'

type TooltipParam = {
  seriesName: string
  value: number
  marker: string
  axisValue?: string
  dataIndex?: number
}

type TooltipFormatter = (params: TooltipParam[]) => string

function latestTooltip(): TooltipFormatter {
  const props = chartRenderMock.mock.calls.at(-1)?.[0] as {
    option: { tooltip: { formatter: TooltipFormatter } }
  }
  return props.option.tooltip.formatter
}

function expectEscapedName(html: string, preservesMarker = true) {
  expect(html).toContain(escapedName)
  expect(html).not.toContain(hostileName)
  expect(html).not.toContain('<img')
  if (preservesMarker) expect(html).toContain(marker)
}

describe('ECharts tooltip HTML escaping', () => {
  beforeEach(() => {
    chartRenderMock.mockClear()
  })

  it('escapes token-volume deployment names without escaping ECharts markers', () => {
    render(
      <TokenVolumeChart
        {...sharedProps}
        prompt={[4]}
        completion={[6]}
        total={[10]}
        perDeployment={{ [hostileName]: { prompt: [4], completion: [6] } }}
      />,
    )

    const html = latestTooltip()([
      { seriesName: hostileName, value: 10, marker, axisValue: timestamps[0], dataIndex: 0 },
      { seriesName: 'Combined', value: 10, marker: '', axisValue: timestamps[0], dataIndex: 0 },
    ])
    expectEscapedName(html)
  })

  it('escapes request-outcome deployment names without escaping ECharts markers', () => {
    render(
      <RequestOutcomesChart
        {...sharedProps}
        successful={[9]}
        throttled={[1]}
        perDeployment={{ [hostileName]: { successful: [9], throttled: [1] } }}
      />,
    )

    const html = latestTooltip()([
      { seriesName: hostileName, value: 10, marker, axisValue: timestamps[0], dataIndex: 0 },
      { seriesName: 'Combined Successful', value: 9, marker: '', axisValue: timestamps[0], dataIndex: 0 },
      { seriesName: 'Combined HTTP 429', value: 1, marker: '', axisValue: timestamps[0], dataIndex: 0 },
    ])
    expectEscapedName(html)
  })

  it('escapes throttle deployment names without escaping ECharts markers', () => {
    render(
      <ThrottleChart
        {...sharedProps}
        throttled={[3]}
        perDeployment={{ [hostileName]: [3] }}
      />,
    )

    const html = latestTooltip()([
      { seriesName: hostileName, value: 3, marker, axisValue: timestamps[0] },
      { seriesName: 'Combined', value: 3, marker: '', axisValue: timestamps[0] },
    ])
    expectEscapedName(html)
  })

  it('escapes TPM deployment names and reference labels without escaping ECharts markers', () => {
    const hostileLabel = `<svg onload=alert(2)>${hostileName}`
    render(
      <TpmBandChart
        {...sharedProps}
        tpm={[10]}
        avg={10}
        refLine={20}
        refLabel={hostileLabel}
        perDeployment={{ [hostileName]: [10] }}
      />,
    )

    const html = latestTooltip()([
      { seriesName: hostileName, value: 10, marker, axisValue: timestamps[0] },
      { seriesName: 'Combined', value: 10, marker: '', axisValue: timestamps[0] },
    ])
    expectEscapedName(html)
    expect(html).toContain(`&lt;svg onload=alert(2)&gt;${escapedName}`)
    expect(html).not.toContain('<svg')
  })

  it('escapes latency deployment names without escaping ECharts markers', () => {
    render(
      <LatencyOverlayChart
        {...sharedProps}
        combined={{ p50: [10], p95: [20], p99: [30] }}
        perDeployment={{ [hostileName]: { p50: [10], p95: [20], p99: [30] } }}
      />,
    )

    const html = latestTooltip()([
      { seriesName: `${hostileName} P95`, value: 20, marker, axisValue: timestamps[0], dataIndex: 0 },
      { seriesName: 'Combined P95', value: 20, marker: '', axisValue: timestamps[0], dataIndex: 0 },
      { seriesName: 'Combined P50', value: 10, marker: '', axisValue: timestamps[0], dataIndex: 0 },
    ])
    expectEscapedName(html)
  })

  it('escapes prompt-cache deployment names', () => {
    render(
      <CacheEfficiencyChart
        {...sharedProps}
        matchRatePct={[50]}
        source="observed"
        perDeployment={{
          [hostileName]: { match_rate_pct: [50], source: 'observed' },
        }}
      />,
    )

    const html = latestTooltip()([{ seriesName: '', value: 0, marker: '', dataIndex: 0 }])
    expectEscapedName(html, false)
  })
})