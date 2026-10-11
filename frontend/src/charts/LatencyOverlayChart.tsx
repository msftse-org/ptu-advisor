import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, COMBINED_TRACE_COLOR, PTU_CHART_THEME, escapeHtml, fmtTooltipDate, fmtNum, makeAxisDateFormatter, getDeploymentColor, hexToRgba } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  combined: { p50: number[]; p95: number[]; p99: number[] }
  perDeployment: Record<string, { p50: number[]; p95: number[]; p99: number[] }>
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
}

export function LatencyOverlayChart({ timestamps, combined, perDeployment, height, zoomState, onDataZoom, selectedTimestamp }: Props) {
  const entries = Object.entries(perDeployment)

  // Per-deployment P95 lines (solid, deployment color)
  const depP95Series = entries.map(([name, data], i) => {
    const color = getDeploymentColor(i)
    return {
      name: `${name} P95`,
      type: 'line' as const,
      data: data.p95,
      smooth: false,
      symbol: 'none' as const,
      lineStyle: { color, width: 1.5 },
      emphasis: { focus: 'series' as const },
      sampling: 'lttb' as const,
    }
  })

  // Combined P95 dashed white line
  const combinedP95Series = {
    name: 'Combined P95',
    type: 'line' as const,
    data: combined.p95,
    smooth: false,
    symbol: 'none' as const,
    lineStyle: { color: COMBINED_TRACE_COLOR, width: 1.5, type: 'dashed' as const },
    emphasis: { focus: 'series' as const },
    sampling: 'lttb' as const,
  }

  // Combined P50 thin dashed neutral line
  const combinedP50Series = {
    name: 'Combined P50',
    type: 'line' as const,
    data: combined.p50,
    smooth: false,
    symbol: 'none' as const,
    lineStyle: { color: CHART_COLORS.neutral, width: 1, type: 'dashed' as const },
    emphasis: { focus: 'series' as const },
    sampling: 'lttb' as const,
    markLine: selectedTimestamp && timestamps.includes(selectedTimestamp) ? {
      silent: true,
      symbol: 'none',
      lineStyle: { color: 'rgba(215, 225, 255, 0.7)', type: 'dashed', width: 1 },
      data: [{ xAxis: selectedTimestamp }],
      label: { show: false },
    } : undefined,
  }

  const legendData = [
    ...entries.map(([name]) => `${name} P95`),
    'Combined P95',
    'Combined P50',
  ]

  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const, lineStyle: { color: CHART_COLORS.primary, width: 1 } },
      appendTo: () => document.body,
      formatter: (params: Array<{ seriesName: string; value: number; marker: string; axisValue?: string; dataIndex?: number }>) => {
        if (!Array.isArray(params)) return ''
        const ts = params[0]?.axisValue ?? ''
        const idx = params[0]?.dataIndex ?? 0
        // Combined P95 and P50 first
        const combinedP95 = params.find((p) => p.seriesName === 'Combined P95')
        const combinedP50 = params.find((p) => p.seriesName === 'Combined P50')
        let result = `<div style="font-weight:600;margin-bottom:4px">${fmtTooltipDate(ts)}</div>`
        result += `<div style="margin-bottom:4px">`
        if (combinedP95) result += `<span style="color:${COMBINED_TRACE_COLOR}">──</span> Combined P95: <b>${fmtNum(combinedP95.value)} ms</b>`
        if (combinedP50) result += ` &nbsp;·&nbsp; <span style="color:${CHART_COLORS.neutral}">──</span> P50: <b>${fmtNum(combinedP50.value)} ms</b>`
        result += `</div>`
        // Per-deployment: P95 (from series) + P50 (from raw data)
        for (const [name, data] of entries) {
          const p95Param = params.find((p) => p.seriesName === `${name} P95`)
          const p95Val = p95Param?.value ?? 0
          const p50Val = data.p50[idx] ?? 0
          const marker = p95Param?.marker ?? ''
          const color = getDeploymentColor(entries.findIndex(([n]) => n === name))
          result += `<div>${marker} <b>${escapeHtml(name)}</b>: P95 ${fmtNum(p95Val)} ms <span style="opacity:0.7;color:${hexToRgba(color, 0.7)}">· P50 ${fmtNum(p50Val)} ms</span></div>`
        }
        return result
      },
    } as Record<string, unknown>,
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 36,
      data: legendData,
    },
    grid: { ...PTU_CHART_THEME.grid, bottom: 80 },
    xAxis: {
      type: 'category' as const,
      data: timestamps,
      ...PTU_CHART_THEME.categoryAxis,
      boundaryGap: false,
      axisLabel: { ...PTU_CHART_THEME.categoryAxis.axisLabel, formatter: makeAxisDateFormatter(timestamps) },
    },
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      name: 'Latency (ms)',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [...depP95Series, combinedP95Series, combinedP50Series],
  }

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      onEvents={{ datazoom: onDataZoom }}
      opts={{ renderer: 'canvas' }}
      theme="dark"
    />
  )
}
