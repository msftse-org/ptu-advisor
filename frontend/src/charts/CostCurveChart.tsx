import ReactEChartsCore from 'echarts-for-react/lib/core'
import { echarts } from './echarts-setup'
import { PTU_CHART_THEME, makeCompactChartMedia } from './theme'

type Props = {
  sustainedTpm: number[]
  payg: number[]
  hybrid: number[]
  breakEvenTpm: number | null
  upperBreakEvenTpm: number | null
  breakEvenCost: number | null
  ptuFixedMonthly: number
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

function formatCompactCurrency(value: number): string {
  const absoluteValue = Math.abs(value)
  if (absoluteValue >= 1_000_000) return `$${(absoluteValue / 1_000_000).toFixed(1)}M`
  if (absoluteValue >= 1_000) return `$${(absoluteValue / 1_000).toFixed(1)}K`
  return formatCurrency(absoluteValue)
}

function getInitialXMax(sustainedTpm: number[], coreDecisionMarkers: number[], upperBreakEvenTpm: number | null): number {
  const largestCoreMarker = Math.max(0, ...coreDecisionMarkers)
  if (largestCoreMarker > 0) {
    const nearbyUpperLimit = largestCoreMarker + Math.max(largestCoreMarker * 0.5, 25_000)
    const largestVisibleMarker = upperBreakEvenTpm && upperBreakEvenTpm <= nearbyUpperLimit
      ? Math.max(largestCoreMarker, upperBreakEvenTpm)
      : largestCoreMarker
    return largestVisibleMarker * 1.2
  }
  return Math.max(0, ...sustainedTpm)
}

function getVisibleLineMax(sustainedTpm: number[], costs: number[], xMax: number): number {
  const pointCount = Math.min(sustainedTpm.length, costs.length)
  let visibleMax = 0

  for (let index = 0; index < pointCount; index++) {
    const x = sustainedTpm[index]
    const cost = costs[index]
    if (!Number.isFinite(x) || !Number.isFinite(cost)) continue
    if (x >= 0 && x <= xMax) visibleMax = Math.max(visibleMax, cost)

    if (index === 0) continue
    const previousX = sustainedTpm[index - 1]
    const previousCost = costs[index - 1]
    if (!Number.isFinite(previousX) || !Number.isFinite(previousCost) || previousX === x) continue
    if ((previousX < xMax && x > xMax) || (previousX > xMax && x < xMax)) {
      const ratio = (xMax - previousX) / (x - previousX)
      visibleMax = Math.max(visibleMax, previousCost + (cost - previousCost) * ratio)
    }
  }

  return visibleMax
}

function getNiceYAxisMax(sustainedTpm: number[], payg: number[], hybrid: number[], xMax: number, referenceCosts: number[] = []): number {
  const visibleMax = Math.max(
    getVisibleLineMax(sustainedTpm, payg, xMax),
    getVisibleLineMax(sustainedTpm, hybrid, xMax),
    ...referenceCosts.filter((cost) => Number.isFinite(cost) && cost >= 0),
  )
  if (!Number.isFinite(visibleMax) || visibleMax <= 0) return 1

  const roughIncrement = visibleMax / 5
  const magnitude = 10 ** Math.floor(Math.log10(roughIncrement))
  const normalizedIncrement = roughIncrement / magnitude
  const niceFactor = normalizedIncrement <= 1 ? 1 : normalizedIncrement <= 2 ? 2 : normalizedIncrement <= 2.5 ? 2.5 : normalizedIncrement <= 5 ? 5 : 10
  const niceIncrement = niceFactor * magnitude
  return Math.ceil((visibleMax * 1.1) / niceIncrement - 1e-12) * niceIncrement
}

export function CostCurveChart({ sustainedTpm, payg, hybrid, breakEvenTpm, upperBreakEvenTpm, breakEvenCost, ptuFixedMonthly, ptuCapacityTpm, avgTpm, selectedPtu, paygAtAvg, hybridAtAvg, height }: Props) {
  const xMax = getInitialXMax(sustainedTpm, [
    avgTpm,
    breakEvenTpm ?? 0,
    ptuCapacityTpm,
  ], upperBreakEvenTpm)
  const visibleUpperBreakEvenTpm = upperBreakEvenTpm && upperBreakEvenTpm <= xMax
    ? upperBreakEvenTpm
    : null
  const currentCosts = avgTpm > 0 && avgTpm <= xMax ? [paygAtAvg, hybridAtAvg] : []
  const yMax = getNiceYAxisMax(sustainedTpm, payg, hybrid, xMax, currentCosts)
  const markLines: Array<Record<string, unknown>> = []

  // Break-even marker
  if (breakEvenTpm) {
    const costLabel = breakEvenCost != null ? ` (${formatCurrency(breakEvenCost)}/mo)` : ''
    markLines.push({
      xAxis: breakEvenTpm,
      lineStyle: { color: '#FFB900', type: 'dashed', width: 2 },
      label: {
        show: true,
        formatter: `${upperBreakEvenTpm ? 'Lower break-even' : 'Break-even'} ${formatNumber(breakEvenTpm)} TPM${costLabel}`,
        color: '#FFB900',
        fontSize: 12,
        position: 'insideEndTop',
      },
    })
  }

  if (visibleUpperBreakEvenTpm) {
    markLines.push({
      xAxis: visibleUpperBreakEvenTpm,
      lineStyle: { color: '#ff8a65', type: 'dashed', width: 2 },
      label: {
        show: true,
        formatter: `Upper break-even ${formatNumber(visibleUpperBreakEvenTpm)} TPM`,
        color: '#ff8a65',
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

  const currentCostDifference = hybridAtAvg - paygAtAvg
  const currentCostGap = avgTpm > 0
    && Number.isFinite(paygAtAvg)
    && Number.isFinite(hybridAtAvg)
    && currentCostDifference !== 0
    ? {
        silent: true,
        symbol: 'none',
        animation: false,
        tooltip: { show: false },
        lineStyle: {
          color: currentCostDifference > 0 ? '#FFB900' : '#00d4aa',
          type: 'solid' as const,
          width: 2,
        },
        label: {
          show: true,
          formatter: currentCostDifference > 0
            ? `PTU +${formatCompactCurrency(currentCostDifference)}/mo`
            : `PTU saves ${formatCompactCurrency(currentCostDifference)}/mo`,
          color: currentCostDifference > 0 ? '#ffd66b' : '#8fe6d3',
          backgroundColor: 'rgba(8, 12, 18, 0.9)',
          borderColor: currentCostDifference > 0 ? '#8c6b13' : '#226f61',
          borderWidth: 1,
          borderRadius: 4,
          padding: [3, 5],
          fontSize: 11,
          fontWeight: 600,
          position: 'end' as const,
          distance: 8,
        },
        data: [[
          { coord: [avgTpm, paygAtAvg] },
          { coord: [avgTpm, hybridAtAvg] },
        ]],
      }
    : undefined
  const savingsWindow = breakEvenTpm
    ? {
        silent: true,
        tooltip: { show: false },
        itemStyle: { color: 'rgba(0, 212, 170, 0.08)' },
        label: {
          show: true,
          formatter: 'PTU savings window',
          color: '#8fe6d3',
          fontSize: 10,
          position: 'insideTop' as const,
        },
        data: [[
          { name: 'PTU-favorable savings window', xAxis: breakEvenTpm },
          { xAxis: Math.min(upperBreakEvenTpm ?? xMax, xMax) },
        ]],
      }
    : undefined

  // Clip each adjacent line segment to the interval where PAYG is above hybrid.
  const savingsData: Array<[number, number, number, number, number, number]> = []
  for (let i = 0; i < sustainedTpm.length - 1; i++) {
    const startDifference = payg[i] - hybrid[i]
    const endDifference = payg[i + 1] - hybrid[i + 1]
    if (startDifference <= 0 && endDifference <= 0) continue

    let startRatio = 0
    let endRatio = 1
    if (startDifference < 0 && endDifference > 0) {
      startRatio = -startDifference / (endDifference - startDifference)
    }
    if (startDifference > 0 && endDifference < 0) {
      endRatio = startDifference / (startDifference - endDifference)
    }

    const interpolate = (start: number, end: number, ratio: number) => start + (end - start) * ratio
    savingsData.push([
      interpolate(sustainedTpm[i], sustainedTpm[i + 1], startRatio),
      interpolate(sustainedTpm[i], sustainedTpm[i + 1], endRatio),
      interpolate(payg[i], payg[i + 1], startRatio),
      interpolate(hybrid[i], hybrid[i + 1], startRatio),
      interpolate(payg[i], payg[i + 1], endRatio),
      interpolate(hybrid[i], hybrid[i + 1], endRatio),
    ])
  }

  const option = {
    ...PTU_CHART_THEME,
    tooltip: {
      ...PTU_CHART_THEME.tooltip,
      trigger: 'axis' as const,
      appendTo: () => document.body,
      extraCssText: `${PTU_CHART_THEME.tooltip.extraCssText} max-width: min(360px, 75vw); box-sizing: border-box; white-space: normal; overflow-wrap: anywhere;`,
      formatter: (params: Array<{ seriesName: string; value: number[]; marker: string }>) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const tpm = params[0]?.value?.[0] ?? 0
        const inPtu = tpm <= ptuCapacityTpm
        const publicParams = params.filter((param) => !param.seriesName.startsWith('_'))
        let result = `<div style="font-weight:600;margin-bottom:6px">Sustained: ${formatNumber(tpm)} TPM</div>`
        result += `<div style="margin-bottom:4px;color:#cbd7f2">${selectedPtu} PTU — ${inPtu ? `All traffic fits within your ${selectedPtu} PTU — no spillover` : `Traffic exceeds PTU capacity — overflow goes to PAYG`}</div>`
        if (breakEvenTpm) result += `<div>${upperBreakEvenTpm ? 'Lower break-even' : 'Break-even'}: ${formatNumber(breakEvenTpm)} TPM${breakEvenCost != null ? ` (${formatCurrency(breakEvenCost)}/mo)` : ''}</div>`
        if (upperBreakEvenTpm) result += `<div>Upper break-even: ${formatNumber(upperBreakEvenTpm)} TPM</div>`
        result += `<div>${selectedPtu} PTU capacity: ${formatNumber(ptuCapacityTpm)} TPM</div>`
        if (avgTpm > 0) result += `<div>Your average: ${formatNumber(avgTpm)} TPM</div>`
        if (publicParams.length > 0) {
          result += '<div class="cost-tooltip-divider" role="separator" style="border-top:1px solid #273244;margin:6px 0 5px"></div>'
        }
        for (const p of publicParams) {
          const hoveredCost = p.value[1]
          let breakdown = ''
          if (p.seriesName === 'PTU + Spillover') {
            const rawSpilloverCost = hoveredCost - ptuFixedMonthly
            const floatingPointTolerance = Number.EPSILON * Math.max(1, Math.abs(hoveredCost), Math.abs(ptuFixedMonthly)) * 16
            const spilloverCost = rawSpilloverCost > floatingPointTolerance ? rawSpilloverCost : 0
            breakdown = ` (PTU ${formatCurrency(ptuFixedMonthly)} + spillover ${formatCurrency(spilloverCost)})`
          }
          result += `<div>${p.marker} ${p.seriesName}: ${formatCurrency(hoveredCost)}${breakdown}</div>`
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
      min: 0,
      max: yMax,
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
        ...(savingsWindow ? { markArea: savingsWindow } : {}),
      },
      {
        name: 'PTU + Spillover',
        type: 'line' as const,
        data: sustainedTpm.map((x, i) => [x, hybrid[i]]),
        smooth: false,
        symbol: 'none',
        lineStyle: { color: '#00d4aa', width: 2 },
        emphasis: { focus: 'series' as const },
        ...(currentCostGap ? { markLine: currentCostGap } : {}),
      },
      // Savings fill zone: custom polygon series filling between PAYG and PTU
      // lines where PTU is cheaper (the shaded "savings" area).
      {
        name: '_savings_fill',
        type: 'custom' as const,
        data: savingsData,
        encode: { x: [0, 1], y: [2, 3, 4, 5] },
        silent: true,
        tooltip: { show: false },
        z: -1,
        renderItem: (
          _params: { dataIndex: number },
          api: {
            value: (idx: number, dimIdx?: number) => number
            coord: (point: number[]) => number[]
          },
        ) => {
          const startX = api.value(0)
          const endX = api.value(1)
          const startPayg = api.value(2)
          const startHybrid = api.value(3)
          const endPayg = api.value(4)
          const endHybrid = api.value(5)
          return {
            type: 'polygon' as const,
            shape: {
              points: [
                api.coord([startX, startPayg]),
                api.coord([endX, endPayg]),
                api.coord([endX, endHybrid]),
                api.coord([startX, startHybrid]),
              ],
            },
            style: {
              fill: 'rgba(0, 212, 170, 0.15)',
            },
          }
        },
      },
    ],
    media: makeCompactChartMedia({
      grid: { top: 42, bottom: 48 },
      legend: { data: ['PAYG', 'PTU + Spillover'] },
      series: [
        {
          markLine: {
            data: markLines.map((line) => ({
              ...line,
              label: {
                ...((line.label as Record<string, unknown> | undefined) ?? {}),
                show: false,
              },
            })),
          },
        },
        {
          markLine: {
            label: { show: false },
          },
        },
      ],
    }),
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
