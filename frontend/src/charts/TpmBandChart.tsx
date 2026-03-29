import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { CHART_COLORS, PTU_CHART_THEME, fmtTooltipDate, fmtNum, makeAxisDateFormatter } from './theme'
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
      appendTo: () => document.body,
      formatter: (params: Array<{ seriesName: string; value: number; marker: string; axisValue?: string }>) => {
        if (!Array.isArray(params)) return ''
        const ts = params[0]?.axisValue ?? ''
        let result = `<div style="font-weight:600;margin-bottom:4px">${fmtTooltipDate(ts)}</div>`
        for (const p of params) {
          if (p.seriesName === 'Avg' || p.seriesName === refLabel) continue
          const val = typeof p.value === 'number' && !isNaN(p.value) ? fmtNum(p.value) : '\u2014'
          result += `<div>${p.marker} ${p.seriesName}: ${val}</div>`
        }
        result += `<div style="margin-top:4px;border-top:1px solid rgba(255,255,255,0.1);padding-top:4px">`
        result += `<span style="color:${CHART_COLORS.success}">Avg: ${fmtNum(avg)}</span>`
        result += ` &nbsp;·&nbsp; <span style="color:${CHART_COLORS.warning}">${refLabel}: ${fmtNum(refLine)}</span>`
        result += `</div>`
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
      axisLabel: { ...PTU_CHART_THEME.categoryAxis.axisLabel, formatter: makeAxisDateFormatter(timestamps) },
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
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{
            yAxis: avg,
            lineStyle: { color: 'transparent', width: 0 },
            label: { show: true, formatter: `Avg: ${fmtNum(avg)} TPM`, color: CHART_COLORS.success, fontSize: 10, position: 'insideEndTop' as const },
          }],
        },
      },
      {
        name: refLabel,
        type: 'line' as const,
        data: timestamps.map(() => refLine),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: CHART_COLORS.warning, width: 1, type: 'dashed' as const },
        silent: true,
        markLine: {
          silent: true,
          symbol: 'none',
          data: [
            {
              yAxis: refLine,
              lineStyle: { color: 'transparent', width: 0 },
              label: { show: true, formatter: `${refLabel}: ${fmtNum(refLine)} TPM`, color: CHART_COLORS.warning, fontSize: 10, position: 'insideEndBottom' as const },
            },
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
