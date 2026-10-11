import { useId } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import {
  CHART_COLORS,
  PTU_CHART_THEME,
  escapeHtml,
  fmtTooltipDate,
  getDeploymentColor,
  makeAxisDateFormatter,
  makeCompactChartMedia,
} from './theme'
import type { ZoomState } from './use-chart-zoom'

type DataZoomParams = {
  start?: number
  end?: number
  batch?: Array<{ start?: number; end?: number }>
}

type SharedChartProps = {
  timestamps: string[]
  height: number
  zoomState: ZoomState
  onDataZoom: (params: DataZoomParams) => void
  selectedTimestamp: string | null
}

type PromptCacheVolumeChartProps = SharedChartProps & {
  cachedPromptTokens: number[]
  activePromptTokens: number[]
}

type CacheEfficiencyChartProps = SharedChartProps & {
  matchRatePct: Array<number | null>
  source: string
  perDeployment?: Record<string, {
    match_rate_pct: Array<number | null>
    source: 'observed' | 'inferred' | 'mixed' | 'unavailable'
  }>
}

function formatExact(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 20 }).format(value)
}

function selectedTimestampMarker(selectedTimestamp: string | null, timestamps: string[]) {
  if (!selectedTimestamp || !timestamps.includes(selectedTimestamp)) return undefined
  return {
    silent: true,
    symbol: 'none',
    lineStyle: { color: 'rgba(215, 225, 255, 0.7)', type: 'dashed' as const, width: 1 },
    data: [{ xAxis: selectedTimestamp }],
    label: { show: false },
  }
}

function makeSharedOption(timestamps: string[], zoomState: ZoomState, legendData: string[]) {
  return {
    ...PTU_CHART_THEME,
    legend: {
      ...PTU_CHART_THEME.legend,
      top: 0,
      data: legendData,
    },
    grid: {
      ...PTU_CHART_THEME.grid,
      top: 40,
      bottom: 64,
      left: 56,
      right: 18,
    },
    xAxis: {
      type: 'category' as const,
      data: timestamps,
      ...PTU_CHART_THEME.categoryAxis,
      boundaryGap: false,
      axisLabel: {
        ...PTU_CHART_THEME.categoryAxis.axisLabel,
        formatter: makeAxisDateFormatter(timestamps),
      },
    },
    dataZoom: [
      {
        ...PTU_CHART_THEME.dataZoom[0],
        start: zoomState.range[0],
        end: zoomState.range[1],
        xAxisIndex: [0],
      },
      {
        type: 'inside' as const,
        xAxisIndex: [0],
        start: zoomState.range[0],
        end: zoomState.range[1],
        zoomOnMouseWheel: true,
        moveOnMouseMove: false,
      },
    ],
    media: makeCompactChartMedia({
      grid: { top: 46, bottom: 64 },
      xAxis: {
        axisLabel: {
          formatter: makeAxisDateFormatter(timestamps),
        },
      },
    }),
  }
}

export function PromptCacheVolumeChart({
  timestamps,
  cachedPromptTokens,
  activePromptTokens,
  height,
  zoomState,
  onDataZoom,
  selectedTimestamp,
}: PromptCacheVolumeChartProps) {
  const descriptionId = useId()
  const cachedTotal = cachedPromptTokens.reduce((total, value) => total + value, 0)
  const activeTotal = activePromptTokens.reduce((total, value) => total + value, 0)
  const option = {
    ...makeSharedOption(timestamps, zoomState, ['Active prompt tokens', 'Cached prompt tokens']),
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      appendTo: () => document.body,
      formatter: (params: Array<{ dataIndex?: number }> | { dataIndex?: number }) => {
        const rows = Array.isArray(params) ? params : [params]
        const index = Number(rows[0]?.dataIndex ?? 0)
        const cached = cachedPromptTokens[index] ?? 0
        const active = activePromptTokens[index] ?? 0
        return [
          `<strong>${fmtTooltipDate(timestamps[index] ?? '')}</strong>`,
          `Active prompt tokens: ${formatExact(active)}`,
          `Cached prompt tokens: ${formatExact(cached)}`,
          `Total prompt tokens: ${formatExact(active + cached)}`,
        ].join('<br/>')
      },
    } as Record<string, unknown>,
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      name: 'Prompt tokens',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    series: [
      {
        name: 'Active prompt tokens',
        type: 'line' as const,
        stack: 'prompt',
        data: activePromptTokens,
        smooth: false,
        symbol: 'none' as const,
        sampling: 'lttb' as const,
        lineStyle: { color: CHART_COLORS.primary, width: 1.5 },
        areaStyle: { color: 'rgba(91, 127, 255, 0.18)' },
        emphasis: { focus: 'series' as const },
      },
      {
        name: 'Cached prompt tokens',
        type: 'line' as const,
        stack: 'prompt',
        data: cachedPromptTokens,
        smooth: false,
        symbol: 'none' as const,
        sampling: 'lttb' as const,
        lineStyle: { color: CHART_COLORS.success, width: 1.5 },
        areaStyle: { color: 'rgba(47, 158, 119, 0.22)' },
        emphasis: { focus: 'series' as const },
        markLine: selectedTimestampMarker(selectedTimestamp, timestamps),
      },
    ],
  }

  return (
    <div
      className="prompt-cache-chart"
      role="img"
      aria-label="Active and cached prompt token volume over time"
      aria-describedby={descriptionId}
    >
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height, width: '100%' }}
        notMerge
        onEvents={{ datazoom: onDataZoom }}
        opts={{ renderer: 'canvas' }}
        theme="dark"
      />
      <span className="visually-hidden" id={descriptionId}>
        {formatExact(cachedTotal)} cached prompt tokens and {formatExact(activeTotal)} active prompt tokens across {timestamps.length} timestamps.
      </span>
    </div>
  )
}

export function CacheEfficiencyChart({
  timestamps,
  matchRatePct,
  source,
  height,
  zoomState,
  onDataZoom,
  selectedTimestamp,
  perDeployment,
}: CacheEfficiencyChartProps) {
  const descriptionId = useId()
  const lineType = source === 'override' ? 'dashed' : source === 'inferred' ? 'dotted' : 'solid'
  const perDeploymentEntries = Object.entries(perDeployment ?? {})
  const perDeploymentSeries = perDeploymentEntries.map(([name, values], index) => ({
    name: `${name} cache (${values.source})`,
    type: 'line' as const,
    showSymbol: false,
    data: values.match_rate_pct,
    lineStyle: {
      width: 1,
      type: values.source === 'inferred' ? 'dotted' as const : values.source === 'mixed' ? 'dashed' as const : 'solid' as const,
    },
    color: getDeploymentColor(index),
  }))
  const availableRates = matchRatePct.filter((value): value is number => value != null)
  const minRate = availableRates.length > 0 ? Math.min(...availableRates) : null
  const maxRate = availableRates.length > 0 ? Math.max(...availableRates) : null
  const aggregateName = source === 'override' ? 'Cache match (assumed)' : 'Cache match'
  const option = {
    ...makeSharedOption(timestamps, zoomState, [aggregateName, ...perDeploymentSeries.map(({ name }) => name)]),
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      appendTo: () => document.body,
      formatter: (params: Array<{ dataIndex?: number }> | { dataIndex?: number }) => {
        const rows = Array.isArray(params) ? params : [params]
        const index = Number(rows[0]?.dataIndex ?? 0)
        const rate = matchRatePct[index]
        const deploymentRows = perDeploymentEntries.map(([name, values]) => {
          const deploymentRate = values.match_rate_pct[index]
          return `${escapeHtml(name)} cache (${values.source}): ${deploymentRate == null ? 'Unavailable' : `${formatExact(deploymentRate)}%`}`
        })
        return [
          `<strong>${fmtTooltipDate(timestamps[index] ?? '')}</strong>`,
          `Cache match rate: ${rate == null ? 'Unavailable' : `${formatExact(rate)}%`}`,
          ...deploymentRows,
          `Source: ${source}`,
        ].join('<br/>')
      },
    } as Record<string, unknown>,
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      name: 'Cache match',
      min: 0,
      max: 100,
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
      axisLabel: {
        ...PTU_CHART_THEME.valueAxis.axisLabel,
        formatter: '{value}%',
      },
    },
    series: [
      {
        name: aggregateName,
        type: 'line' as const,
        showSymbol: false,
        data: matchRatePct,
        lineStyle: { width: 2, type: lineType },
        color: CHART_COLORS.warning,
        markLine: selectedTimestampMarker(selectedTimestamp, timestamps),
      },
      ...perDeploymentSeries,
    ],
  }

  const rangeDescription = minRate == null || maxRate == null
    ? 'Cache match telemetry is unavailable for this period.'
    : `Cache match telemetry ranges from ${minRate.toFixed(1)}% to ${maxRate.toFixed(1)}% across ${timestamps.length} timestamps.`

  return (
    <div
      className="prompt-cache-chart"
      role="img"
      aria-label="Prompt cache match percentage over time"
      aria-describedby={descriptionId}
    >
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height, width: '100%' }}
        notMerge
        onEvents={{ datazoom: onDataZoom }}
        opts={{ renderer: 'canvas' }}
        theme="dark"
      />
      <span className="visually-hidden" id={descriptionId}>{rangeDescription}</span>
    </div>
  )
}
