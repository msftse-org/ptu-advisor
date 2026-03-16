import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, PTU_CHART_THEME } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  inputCost: number[]
  outputCost: number[]
  avgDailyCost: number
  ptuDailyCost: number
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
}

export function DailyCostChart({ timestamps, inputCost, outputCost, avgDailyCost, ptuDailyCost, height, zoomState, onDataZoom, selectedTimestamp }: Props) {
  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      formatter: (params: Array<{ seriesName: string; value: number; marker: string }>) => {
        if (!Array.isArray(params)) return ''
        const label = params[0]?.seriesName ? '' : ''
        let result = `<div style="font-weight:600;margin-bottom:4px">${(params as unknown as { axisValueLabel?: string }[])
          ?.[0]?.axisValueLabel ?? ''}</div>`
        for (const p of params) {
          if (p.seriesName === 'Avg Daily' || p.seriesName === 'PTU Daily') continue
          result += `<div>${p.marker} ${p.seriesName}: $${typeof p.value === 'number' ? p.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : p.value}</div>`
        }
        return result + label
      },
    },
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 36,
      data: ['Input Cost', 'Output Cost'],
    },
    grid: { ...PTU_CHART_THEME.grid, bottom: 80 },
    xAxis: {
      type: 'category' as const,
      data: timestamps,
      ...PTU_CHART_THEME.categoryAxis,
    },
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      name: 'USD',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
      axisLabel: { ...PTU_CHART_THEME.valueAxis.axisLabel, formatter: (v: number) => `$${v.toLocaleString()}` },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [
      {
        name: 'Input Cost',
        type: 'bar' as const,
        stack: 'cost',
        data: inputCost,
        itemStyle: { color: CHART_COLORS.primary },
        emphasis: { focus: 'series' as const },
      },
      {
        name: 'Output Cost',
        type: 'bar' as const,
        stack: 'cost',
        data: outputCost,
        itemStyle: {
          color: CHART_COLORS.secondary,
          borderRadius: [3, 3, 0, 0],
        },
        emphasis: { focus: 'series' as const },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [
            ...(avgDailyCost > 0 ? [{
              yAxis: avgDailyCost,
              lineStyle: { color: CHART_COLORS.neutral, type: 'dashed' as const, width: 1 },
              label: { show: true, formatter: 'Avg Daily', color: CHART_COLORS.neutral, fontSize: 10, position: 'insideEndTop' as const },
            }] : []),
            ...(ptuDailyCost > 0 ? [{
              yAxis: ptuDailyCost,
              lineStyle: { color: CHART_COLORS.danger, type: 'dashed' as const, width: 1 },
              label: { show: true, formatter: 'PTU Daily', color: CHART_COLORS.danger, fontSize: 10, position: 'insideEndBottom' as const },
            }] : []),
            ...(selectedTimestamp && timestamps.includes(selectedTimestamp) ? [{
              xAxis: selectedTimestamp,
              lineStyle: { color: 'rgba(215, 225, 255, 0.7)', type: 'dashed' as const, width: 1 },
              label: { show: false },
            }] : []),
          ],
        },
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
