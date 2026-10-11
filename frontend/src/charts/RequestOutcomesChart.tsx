import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, COMBINED_TRACE_COLOR, PTU_CHART_THEME, escapeHtml, fmtTooltipDate, fmtNum, fmtPct, makeAxisDateFormatter, getDeploymentColor, hexToRgba } from './theme'
import type { ZoomState } from './use-chart-zoom'

type Props = {
  timestamps: string[]
  successful: number[]
  throttled: number[]
  height: number
  zoomState: ZoomState
  onDataZoom: (params: { start?: number; end?: number; batch?: Array<{ start?: number; end?: number }> }) => void
  selectedTimestamp: string | null
  perDeployment?: Record<string, { successful: number[]; throttled: number[] }>
}

export function RequestOutcomesChart({ timestamps, successful, throttled, height, zoomState, onDataZoom, selectedTimestamp, perDeployment }: Props) {
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
      data: ['Successful', 'HTTP 429'],
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
      name: 'Requests',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    dataZoom: [
      { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
      { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
    ],
    series: [
      {
        name: 'Successful',
        type: 'line' as const,
        data: successful,
        smooth: false,
        symbol: 'none' as const,
        lineStyle: { color: CHART_COLORS.success, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(47, 158, 119, 0.2)' },
            { offset: 1, color: 'rgba(47, 158, 119, 0.02)' },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      },
      {
        name: 'HTTP 429',
        type: 'line' as const,
        data: throttled,
        smooth: false,
        symbol: 'none' as const,
        lineStyle: { color: CHART_COLORS.danger, width: 1.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(179, 82, 82, 0.2)' },
            { offset: 1, color: 'rgba(179, 82, 82, 0.02)' },
          ]),
        },
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

    // Per-deployment TOTAL requests (successful + throttled) as stacked areas
    const depTotalSeries = entries.map(([name, data], i) => {
      const color = getDeploymentColor(i)
      const depTotal = data.successful.map((s, j) => s + (data.throttled[j] ?? 0))
      return {
        name,
        type: 'line' as const,
        data: depTotal,
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

    // Per-deployment throttled as stacked areas (lower opacity)
    const depThrottledSeries = entries.map(([name, data], i) => {
      const color = getDeploymentColor(i)
      return {
        name: `${name} (429)`,
        type: 'line' as const,
        data: data.throttled,
        stack: 'throttled',
        smooth: false,
        symbol: 'none' as const,
        lineStyle: { color: hexToRgba(color, 0.6), width: 1 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: hexToRgba(color, 0.10) },
            { offset: 1, color: hexToRgba(color, 0.01) },
          ]),
        },
        emphasis: { focus: 'series' as const },
        sampling: 'lttb' as const,
      }
    })

    // Combined Successful dashed white line
    const combinedSuccessfulSeries = {
      name: 'Combined Successful',
      type: 'line' as const,
      data: successful,
      smooth: false,
      symbol: 'none' as const,
      lineStyle: { color: COMBINED_TRACE_COLOR, width: 1.5, type: 'dashed' as const },
      emphasis: { focus: 'series' as const },
      sampling: 'lttb' as const,
    }

    // Combined HTTP 429 dashed red line
    const combinedThrottledSeries = {
      name: 'Combined HTTP 429',
      type: 'line' as const,
      data: throttled,
      smooth: false,
      symbol: 'none' as const,
      lineStyle: { color: CHART_COLORS.danger, width: 1.5, type: 'dashed' as const },
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
      ...depNames,
      ...depNames.map((n) => `${n} (429)`),
      'Combined Successful',
      'Combined HTTP 429',
    ]

    return {
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
          // Find combined totals
          const combinedSucc = params.find((p) => p.seriesName === 'Combined Successful')?.value ?? 0
          const combined429 = params.find((p) => p.seriesName === 'Combined HTTP 429')?.value ?? 0
          const combinedTotal = combinedSucc + combined429
          let result = `<div style="font-weight:600;margin-bottom:4px">${fmtTooltipDate(ts)}</div>`
          // Combined totals first
          result += `<div style="margin-bottom:4px"><span style="color:${COMBINED_TRACE_COLOR}">──</span> Combined Successful: <b>${fmtNum(combinedSucc)}</b>`
          result += ` &nbsp;·&nbsp; <span style="color:${CHART_COLORS.danger}">──</span> 429: <b>${fmtNum(combined429)}</b></div>`
          // Per-deployment grouped breakdown
          for (const [name, data] of entries) {
            const succVal = data.successful[idx] ?? 0
            const thrVal = data.throttled[idx] ?? 0
            const depTotal = succVal + thrVal
            const depParam = params.find((p) => p.seriesName === name)
            const marker = depParam?.marker ?? ''
            result += `<div>${marker} <b>${escapeHtml(name)}</b>: ${fmtNum(depTotal)} <span style="opacity:0.6">(${fmtPct(depTotal, combinedTotal)})</span></div>`
            result += `<div style="padding-left:18px;opacity:0.7">OK: ${fmtNum(succVal)} · 429: ${fmtNum(thrVal)}</div>`
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
        name: 'Requests',
        nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
      },
      dataZoom: [
        { ...PTU_CHART_THEME.dataZoom[0], start: zoomState.range[0], end: zoomState.range[1], xAxisIndex: [0] },
        { type: 'inside' as const, xAxisIndex: [0], start: zoomState.range[0], end: zoomState.range[1], zoomOnMouseWheel: true, moveOnMouseMove: false },
      ],
      series: [...depTotalSeries, ...depThrottledSeries, combinedSuccessfulSeries, combinedThrottledSeries],
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
