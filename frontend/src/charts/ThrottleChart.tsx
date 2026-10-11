import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, COMBINED_TRACE_COLOR, PTU_CHART_THEME, escapeHtml, fmtTooltipDate, fmtNum, fmtPct, makeAxisDateFormatter, getDeploymentColor, hexToRgba } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  throttled: number[]
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
  perDeployment?: Record<string, number[]>
}

export function ThrottleChart({ timestamps, throttled, height, zoomState, onDataZoom, selectedTimestamp, perDeployment }: Props) {
  const isConsolidated = perDeployment != null && Object.keys(perDeployment).length > 0

  const buildSingleDeploymentOption = () => ({
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
      data: ['Rate Limited'],
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
        symbol: 'none' as const,
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
  })

  const buildConsolidatedOption = () => {
    const entries = Object.entries(perDeployment!)
    const depNames = entries.map(([name]) => name)

    // Per-deployment throttle values as stacked areas
    const depSeries = entries.map(([name, data], i) => {
      const color = getDeploymentColor(i)
      return {
        name,
        type: 'line' as const,
        data,
        stack: 'per-dep',
        smooth: false,
        symbol: 'none' as const,
        lineStyle: { color, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: hexToRgba(color, 0.18) },
            { offset: 1, color: hexToRgba(color, 0.02) },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      }
    })

    // Combined dashed white line on top
    const combinedSeries = {
      name: 'Combined',
      type: 'line' as const,
      data: throttled,
      smooth: false,
      symbol: 'none' as const,
      lineStyle: { color: COMBINED_TRACE_COLOR, width: 1.5, type: 'dashed' as const },
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

    return {
      ...PTU_CHART_THEME,
      tooltip: {
        ...PTU_CHART_THEME.tooltip,
        trigger: 'axis' as const,
        axisPointer: { type: 'cross' as const, lineStyle: { color: CHART_COLORS.primary, width: 1 } },
        appendTo: () => document.body,
        formatter: (params: Array<{ seriesName: string; value: number; marker: string; axisValue?: string }>) => {
          if (!Array.isArray(params)) return ''
          const ts = params[0]?.axisValue ?? ''
          const combinedParam = params.find((p) => p.seriesName === 'Combined')
          const combinedVal = combinedParam?.value ?? 0
          let result = `<div style="font-weight:600;margin-bottom:4px">${fmtTooltipDate(ts)}</div>`
          // Combined total first
          result += `<div style="margin-bottom:4px"><span style="color:${COMBINED_TRACE_COLOR}">──</span> Combined: <b>${fmtNum(combinedVal)}</b></div>`
          // Per-deployment with % contribution
          for (const p of params) {
            if (p.seriesName === 'Combined') continue
            result += `<div>${p.marker} <b>${escapeHtml(p.seriesName)}</b>: ${fmtNum(p.value)} <span style="opacity:0.6">(${fmtPct(p.value, combinedVal)})</span></div>`
          }
          return result
        },
      } as Record<string, unknown>,
      legend: {
        ...PTU_CHART_THEME.legend,
        bottom: 36,
        data: [...depNames, 'Combined'],
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
        name: '429 Events',
        nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
      },
      dataZoom: [
        { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
        { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
      ],
      series: [...depSeries, combinedSeries],
    }
  }

  const option = isConsolidated ? buildConsolidatedOption() : buildSingleDeploymentOption()

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
