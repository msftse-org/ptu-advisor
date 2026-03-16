import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { PTU_CHART_THEME } from './theme'

type Props = {
  baselineTpm: number[]
  payg: number[]
  hybrid: number[]
  ptuUnits: number[]
  breakEvenTpm: number | null
  breakEvenPtuUnits: number | null
  sliderBaselineTpm: number
  sliderPtu: number
  paygAtSlider: number
  hybridAtSlider: number
  height: number
}

function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return `${Math.round(value)}`
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function CostCurveChart({ baselineTpm, payg, hybrid, ptuUnits, breakEvenTpm, breakEvenPtuUnits, sliderBaselineTpm, sliderPtu, paygAtSlider, hybridAtSlider, height }: Props) {
  const markLines: Array<Record<string, unknown>> = []

  if (breakEvenTpm) {
    markLines.push({
      xAxis: breakEvenTpm,
      lineStyle: { color: '#FFB900', type: 'dashed', width: 2 },
      label: {
        show: true,
        formatter: `Break-even ${formatNumber(breakEvenTpm)}${breakEvenPtuUnits ? ` · ${breakEvenPtuUnits} PTU` : ''}`,
        color: '#FFB900',
        fontSize: 12,
        position: 'insideEndTop',
      },
    })
  }

  markLines.push({
    xAxis: sliderBaselineTpm,
    lineStyle: { color: '#00d4aa', type: 'dashed', width: 2 },
    label: {
      show: true,
      formatter: `Baseline ${formatNumber(sliderBaselineTpm)} · ${sliderPtu} PTU`,
      color: '#00d4aa',
      fontSize: 12,
      position: 'insideEndBottom',
    },
  })

  const markPoints: Array<Record<string, unknown>> = [
    {
      coord: [sliderBaselineTpm, paygAtSlider],
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: { color: '#0078D4', borderColor: '#dce7ff', borderWidth: 1 },
    },
    {
      coord: [sliderBaselineTpm, hybridAtSlider],
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: { color: '#00d4aa', borderColor: '#dce7ff', borderWidth: 1 },
    },
  ]

  const dataMax = Math.max(...baselineTpm)
  const xMax = Math.max(dataMax, sliderBaselineTpm * 1.15, (breakEvenTpm ?? 0) * 1.15)

  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      formatter: (params: Array<{ seriesName: string; value: number[]; marker: string }>) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const baseline = params[0]?.value?.[0]
        const ptuIdx = baselineTpm.findIndex((v) => v === baseline)
        const ptu = ptuIdx >= 0 ? ptuUnits[ptuIdx] : 0
        let result = `<div style="font-weight:600;margin-bottom:6px">Baseline: ${formatNumber(baseline ?? 0)} TPM</div>`
        result += `<div style="margin-bottom:4px;color:#cbd7f2">PTU at point: ${ptu ?? 0}</div>`
        for (const p of params) {
          result += `<div>${p.marker} ${p.seriesName}: ${formatCurrency(p.value[1])}</div>`
        }
        return result
      },
    },
    legend: {
      ...PTU_CHART_THEME.legend,
      bottom: 8,
      data: ['PAYG', 'PTU + Spillover'],
    },
    grid: { ...PTU_CHART_THEME.grid, bottom: 44, top: 10, left: 60 },
    xAxis: {
      type: 'value' as const,
      min: 0,
      max: xMax,
      ...PTU_CHART_THEME.valueAxis,
      axisLabel: { ...PTU_CHART_THEME.valueAxis.axisLabel, formatter: (v: number) => formatNumber(v) },
      name: 'Baseline TPM',
      nameLocation: 'middle' as const,
      nameGap: 28,
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    yAxis: {
      type: 'value' as const,
      ...PTU_CHART_THEME.valueAxis,
      axisLabel: { ...PTU_CHART_THEME.valueAxis.axisLabel, formatter: (v: number) => formatCurrency(v) },
      name: '$/month',
      nameTextStyle: { color: '#8f9ec4', fontSize: 10 },
    },
    series: [
      {
        name: 'PAYG',
        type: 'line' as const,
        data: baselineTpm.map((x, i) => [x, payg[i]]),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: '#0078D4', width: 2, type: 'dashed' as const },
        emphasis: { focus: 'series' as const },
        markLine: {
          silent: true,
          symbol: 'none',
          data: markLines,
        },
        markPoint: {
          silent: true,
          data: markPoints,
        },
      },
      {
        name: 'PTU + Spillover',
        type: 'line' as const,
        data: baselineTpm.map((x, i) => [x, hybrid[i]]),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: '#00d4aa', width: 2 },
        emphasis: { focus: 'series' as const },
      },
    ],
  }

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      opts={{ renderer: 'canvas' }}
      theme="dark"
    />
  )
}
