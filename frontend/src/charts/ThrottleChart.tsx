import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, PTU_CHART_THEME } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  throttled: number[]
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
}

export function ThrottleChart({ timestamps, throttled, height, zoomState, onDataZoom, selectedTimestamp }: Props) {
  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const, lineStyle: { color: CHART_COLORS.primary, width: 1 } },
    },
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 36,
      data: ['Rate Limited'],
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
      name: '429 Events',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [
      {
        name: 'Rate Limited',
        type: 'line' as const,
        data: throttled,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.warning, width: 1.5 },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
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
