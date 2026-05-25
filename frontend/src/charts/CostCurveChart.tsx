import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { PTU_CHART_THEME } from './theme'

type Props = {
  sustainedTpm: number[]
  payg: number[]
  hybrid: number[]
  breakEvenTpm: number | null
  breakEvenCost: number | null
  ptuCapacityTpm: number
  avgTpm: number
  selectedPtu: number
  paygAtAvg: number
  hybridAtAvg: number
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

export function CostCurveChart({ sustainedTpm, payg, hybrid, breakEvenTpm, breakEvenCost, ptuCapacityTpm, avgTpm, selectedPtu, paygAtAvg, hybridAtAvg, height }: Props) {
  const markLines: Array<Record<string, unknown>> = []

  // Break-even marker
  if (breakEvenTpm) {
    const costLabel = breakEvenCost != null ? ` (${formatCurrency(breakEvenCost)}/mo)` : ''
    markLines.push({
      xAxis: breakEvenTpm,
      lineStyle: { color: '#FFB900', type: 'dashed', width: 2 },
      label: {
        show: true,
        formatter: `Break-even ${formatNumber(breakEvenTpm)} TPM${costLabel}`,
        color: '#FFB900',
        fontSize: 12,
        position: 'insideEndTop',
      },
    })
  }

  // PTU capacity marker (inflection point where spillover begins)
  markLines.push({
    xAxis: ptuCapacityTpm,
    lineStyle: { color: '#00d4aa', type: 'dotted', width: 1.5 },
    label: {
      show: true,
      formatter: `${selectedPtu} PTU capacity (${formatNumber(ptuCapacityTpm)})`,
      color: '#00d4aa',
      fontSize: 10,
      position: 'insideEndBottom',
    },
  })

  // Your avg TPM marker (white per PRD §3.3)
  if (avgTpm > 0) {
    markLines.push({
      xAxis: avgTpm,
      lineStyle: { color: '#ffffff', type: 'dashed', width: 2 },
      label: {
        show: true,
        formatter: `Your avg ${formatNumber(avgTpm)} TPM`,
        color: '#ffffff',
        fontSize: 12,
        position: 'insideEndTop',
      },
    })
  }

  // Cost dots at user's avg TPM
  const markPoints: Array<Record<string, unknown>> = []
  if (avgTpm > 0) {
    markPoints.push(
      {
        coord: [avgTpm, paygAtAvg],
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#0078D4', borderColor: '#dce7ff', borderWidth: 1 },
      },
      {
        coord: [avgTpm, hybridAtAvg],
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#00d4aa', borderColor: '#dce7ff', borderWidth: 1 },
      },
    )
  }

  const dataMax = Math.max(...sustainedTpm)
  const xMax = Math.max(dataMax, avgTpm * 1.15, (breakEvenTpm ?? 0) * 1.15, ptuCapacityTpm * 1.3)

  // Savings fill zone: collect data points where PAYG > PTU (PTU is cheaper).
  // Each point stores [x, yPayg, yHybrid] for the custom polygon renderer.
  const savingsData: Array<[number, number, number]> = []
  for (let i = 0; i < sustainedTpm.length; i++) {
    if (payg[i] > hybrid[i]) {
      savingsData.push([sustainedTpm[i], payg[i], hybrid[i]])
    }
  }

  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      appendTo: () => document.body,
      formatter: (params: Array<{ seriesName: string; value: number[]; marker: string }>) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const tpm = params[0]?.value?.[0] ?? 0
        const inPtu = tpm <= ptuCapacityTpm
        let result = `<div style="font-weight:600;margin-bottom:6px">Sustained: ${formatNumber(tpm)} TPM</div>`
        result += `<div style="margin-bottom:4px;color:#cbd7f2">${selectedPtu} PTU — ${inPtu ? `All traffic fits within your ${selectedPtu} PTU — no spillover` : `Traffic exceeds PTU capacity — overflow goes to PAYG`}</div>`
        for (const p of params) {
          if (p.seriesName.startsWith('_')) continue
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
      name: 'Sustained TPM',
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
        data: sustainedTpm.map((x, i) => [x, payg[i]]),
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
        data: sustainedTpm.map((x, i) => [x, hybrid[i]]),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: '#00d4aa', width: 2 },
        emphasis: { focus: 'series' as const },
      },
      // Savings fill zone: custom polygon series filling between PAYG and PTU
      // lines where PTU is cheaper (the shaded "savings" area).
      {
        name: '_savings_fill',
        type: 'custom' as const,
        data: savingsData,
        silent: true,
        tooltip: { show: false },
        z: -1,
        renderItem: (
          _params: unknown,
          api: {
            value: (idx: number, dimIdx?: number) => number
            coord: (point: number[]) => number[]
          },
        ) => {
          // Each data point contributes a vertical strip from hybrid (bottom) to payg (top).
          // We draw a thin rect per point to approximate the filled area.
          const x = api.value(0)
          const yPayg = api.value(1)
          const yHybrid = api.value(2)
          const topLeft = api.coord([x, yPayg])
          const bottomLeft = api.coord([x, yHybrid])
          // Width: pixel distance to the next sustained-TPM sample on x-axis.
          // api.size() without args is undefined in some echarts versions, so derive
          // the step from two coord lookups on the value axis.
          const stepX = sustainedTpm.length > 1 ? sustainedTpm[1] - sustainedTpm[0] : 0
          const nextPx = stepX > 0 ? api.coord([x + stepX, yPayg])[0] : topLeft[0] + 2
          const stepPx = Math.max(nextPx - topLeft[0], 1.5)
          return {
            type: 'rect' as const,
            shape: {
              x: topLeft[0],
              y: topLeft[1],
              width: stepPx,
              height: Math.max(bottomLeft[1] - topLeft[1], 0),
            },
            style: {
              fill: 'rgba(0, 212, 170, 0.15)',
            },
          }
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
      opts={{ renderer: 'canvas' }}
      theme="dark"
    />
  )
}
