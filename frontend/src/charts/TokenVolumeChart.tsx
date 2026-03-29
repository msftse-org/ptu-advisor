import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, PTU_CHART_THEME, fmtTooltipDate, fmtNum, makeAxisDateFormatter } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  prompt: number[]
  completion: number[]
  total: number[]
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
  groupId?: string
}

export function TokenVolumeChart({ timestamps, prompt, completion, total, height, zoomState, onDataZoom, selectedTimestamp, groupId }: Props) {
  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const, lineStyle: { color: CHART_COLORS.primary, width: 1 } },
      appendTo: () => document.body,
      formatter: (params: Array<{ seriesName: string; value: number; marker: string; axisValue?: string }>) => {
        if (!Array.isArray(params)) return ''
        const ts = params[0]?.axisValue ?? ''
        let result = `<div style="font-weight:600;margin-bottom:4px">${fmtTooltipDate(ts)}</div>`
        for (const p of params) {
          result += `<div>${p.marker} ${p.seriesName}: ${fmtNum(p.value)}</div>`
        }
        return result
      },
    } as Record<string, unknown>,
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 36,
      data: ['Prompt Tokens', 'Completion Tokens', 'Total'],
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
      name: 'Tokens',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [
      {
        name: 'Prompt Tokens',
        type: 'line' as const,
        data: prompt,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.primary, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(91, 127, 255, 0.24)' },
            { offset: 1, color: 'rgba(91, 127, 255, 0.02)' },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      },
      {
        name: 'Completion Tokens',
        type: 'line' as const,
        data: completion,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.secondary, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(123, 142, 175, 0.22)' },
            { offset: 1, color: 'rgba(123, 142, 175, 0.02)' },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      },
      {
        name: 'Total',
        type: 'line' as const,
        data: total,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.accent, width: 1.5, type: 'dashed' as const },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      },
    ],
    ...(selectedTimestamp && timestamps.includes(selectedTimestamp) ? {
      // No extra markLine needed — we handle this at series level if needed
    } : {}),
  }

  // Add markLine to last series for selected timestamp
  if (selectedTimestamp && timestamps.includes(selectedTimestamp)) {
    const lastSeries = option.series[option.series.length - 1]
    ;(lastSeries as Record<string, unknown>).markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { color: 'rgba(215, 225, 255, 0.7)', type: 'dashed', width: 1 },
      data: [{ xAxis: selectedTimestamp }],
      label: { show: false },
    }
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
      key={groupId}
    />
  )
}
