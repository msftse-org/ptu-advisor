import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, PTU_CHART_THEME } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  tpm: number[]
  avg: number
  refLine: number
  refLabel: string
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
}

export function TpmBandChart({ timestamps, tpm, avg, refLine, refLabel, height, zoomState, onDataZoom, selectedTimestamp }: Props) {
  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const, lineStyle: { color: CHART_COLORS.primary, width: 1 } },
      formatter: (params: Array<{ seriesName: string; value: number; marker: string }>) => {
        if (!Array.isArray(params)) return ''
        let result = `<div style="font-weight:600;margin-bottom:4px">${(params as unknown as { axisValueLabel?: string }[])
          ?.[0]?.axisValueLabel ?? ''}</div>`
        for (const p of params) {
          if (p.seriesName === 'Avg' || p.seriesName === refLabel) continue
          result += `<div>${p.marker} ${p.seriesName}: ${typeof p.value === 'number' ? p.value.toLocaleString() : p.value}</div>`
        }
        return result
      },
    },
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 36,
      data: ['TPM', 'Avg', refLabel],
    },
    grid: { ...PTU_CHART_THEME.grid, bottom: 80 },
    xAxis: {
      type: 'category' as const,
      data: timestamps,
      ...PTU_CHART_THEME.categoryAxis,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      name: 'TPM',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [
      {
        name: 'TPM',
        type: 'line' as const,
        data: tpm,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.primary, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(91, 127, 255, 0.18)' },
            { offset: 1, color: 'rgba(91, 127, 255, 0.02)' },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      },
      {
        name: 'Avg',
        type: 'line' as const,
        data: timestamps.map(() => avg),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.success, width: 1, type: 'dashed' as const },
        silent: true,
      },
      {
        name: refLabel,
        type: 'line' as const,
        data: timestamps.map(() => refLine),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.warning, width: 1, type: 'dashed' as const },
        silent: true,
        markLine: selectedTimestamp && timestamps.includes(selectedTimestamp) ? {
          silent: true,
          symbol: 'none',
          lineStyle: { color: 'rgba(215, 225, 255, 0.7)', type: 'dashed', width: 1 },
          data: [{ xAxis: selectedTimestamp }],
          label: { show: false },
        } : undefined,
      },
    ],
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
