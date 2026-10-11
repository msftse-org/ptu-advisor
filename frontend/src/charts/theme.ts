/** Dark operational theme configuration for PTU Advisor ECharts. */

const CHART_DATA_FONT = 'SFMono-Regular, Cascadia Code, Roboto Mono, Consolas, monospace'

const HTML_ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => HTML_ENTITIES[character])
}

/** Format a timestamp for tooltip headers: M/D HH:mm */
export function fmtTooltipDate(iso: string): string {
  const d = new Date(iso)
  const mon = d.getMonth() + 1
  const day = d.getDate()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${mon}/${day} ${hh}:${mm}`
}

/** Format a date-only string for daily chart tooltips: M/D */
export function fmtTooltipDay(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** Format a numeric value as a rounded integer with locale separators. */
export function fmtNum(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '—'
  return Math.round(v).toLocaleString()
}

/** Format a percentage value for tooltip display (e.g., "42%"). Returns "—" for NaN/null. */
export function fmtPct(part: number, total: number): string {
  if (total === 0 || isNaN(part) || isNaN(total)) return '—'
  return `${Math.round((part / total) * 100)}%`
}

/** Build an adaptive X-axis label formatter based on timestamp span/density. */
export function makeAxisDateFormatter(timestamps: string[]): (iso: string) => string {
  if (timestamps.length === 0) return (iso) => {
    const d = new Date(iso); return `${d.getMonth() + 1}/${d.getDate()}`
  }
  const first = new Date(timestamps[0]).getTime()
  const last = new Date(timestamps[timestamps.length - 1]).getTime()
  const spanHours = (last - first) / (1000 * 60 * 60)
  const dense = timestamps.length > 80

  return (iso: string) => {
    const d = new Date(iso)
    const mon = d.getMonth() + 1
    const day = d.getDate()
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    if (spanHours <= 24) return `${hh}:${mm}`
    if (spanHours <= 168 && !dense) return `${mon}/${day} ${hh}:${mm}`
    return `${mon}/${day}`
  }
}

export const CHART_COLORS = {
  primary: '#5B7FFF',
  secondary: '#7B8EAF',
  success: '#2F9E77',
  danger: '#B35252',
  warning: '#C58A2A',
  neutral: '#9DAAC0',
  accent: '#A78BFA',
} as const

/**
 * Color palette for per-deployment chart traces in consolidation mode.
 * Colors assigned by index within the selected group.
 * The "Combined" trace uses `CHART_COLORS.neutral` with higher opacity.
 */
export const DEPLOYMENT_COLORS = [
  '#5B7FFF',  // blue
  '#2F9E77',  // green
  '#C58A2A',  // amber
  '#A78BFA',  // purple
  '#B35252',  // red
  '#4DC9F6',  // cyan
  '#F28E2B',  // orange
  '#59A14F',  // forest
  '#B07AA1',  // mauve
  '#FF9DA7',  // pink
] as const

/** Combined trace color (used for "Combined" series in consolidation charts). */
export const COMBINED_TRACE_COLOR = '#e5ebf5'

export const COMPACT_CHART_MAX_WIDTH = 560

export const COMPACT_CHART_OPTION = {
  grid: {
    left: 8,
    right: 8,
    top: 42,
    bottom: 64,
    containLabel: true,
  },
  legend: {
    type: 'scroll' as const,
    top: 0,
    right: 8,
    bottom: null,
    left: 8,
    itemGap: 12,
    pageButtonItemGap: 4,
    pageIconSize: 10,
    pageTextStyle: { color: '#8592a6', fontSize: 10 },
  },
  xAxis: {
    axisLabel: {
      fontSize: 10,
      hideOverlap: true,
      showMinLabel: true,
      showMaxLabel: true,
    },
  },
} as const

type CompactChartOverrides = {
  grid?: Record<string, unknown>
  legend?: Record<string, unknown>
  xAxis?: Record<string, unknown> & { axisLabel?: Record<string, unknown> }
  [key: string]: unknown
}

export function makeCompactChartMedia(overrides: CompactChartOverrides = {}) {
  const { grid, legend, xAxis, ...rest } = overrides
  return [{
    query: { maxWidth: COMPACT_CHART_MAX_WIDTH },
    option: {
      ...COMPACT_CHART_OPTION,
      ...rest,
      grid: { ...COMPACT_CHART_OPTION.grid, ...grid },
      legend: { ...COMPACT_CHART_OPTION.legend, ...legend },
      xAxis: {
        ...COMPACT_CHART_OPTION.xAxis,
        ...xAxis,
        axisLabel: {
          ...COMPACT_CHART_OPTION.xAxis.axisLabel,
          ...xAxis?.axisLabel,
        },
      },
    },
  }]
}

/**
 * Get the deployment color for a given index (wraps around palette).
 * Returns an rgba string for area fills at the specified opacity.
 */
export function getDeploymentColor(index: number): string {
  return DEPLOYMENT_COLORS[index % DEPLOYMENT_COLORS.length]
}

/** Convert a hex color to an rgba string. */
export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export const PTU_CHART_THEME = {
  color: [CHART_COLORS.primary, CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.danger, CHART_COLORS.accent, CHART_COLORS.secondary],
  backgroundColor: 'transparent',
  textStyle: { color: '#9aa8bc', fontFamily: 'Avenir Next, Segoe UI, sans-serif', fontSize: 11 },
  title: { textStyle: { color: '#edf2f7' } },
  legend: {
    textStyle: { color: '#b4bfd0', fontSize: 11 },
    icon: 'roundRect',
    itemWidth: 12,
    itemHeight: 3,
  },
  grid: {
    left: 50,
    right: 16,
    top: 12,
    bottom: 60,
    containLabel: true,
  },
  categoryAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: 'rgba(151,168,194,0.10)', type: 'dashed' as const } },
    axisLabel: { color: '#8592a6', fontFamily: CHART_DATA_FONT, fontSize: 11 },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: 'rgba(151,168,194,0.10)', type: 'dashed' as const } },
    axisLabel: { color: '#8592a6', fontFamily: CHART_DATA_FONT, fontSize: 10 },
  },
  dataZoom: [{
    type: 'slider' as const,
    backgroundColor: '#171e2b',
    fillerColor: 'rgba(91, 127, 255, 0.15)',
    borderColor: '#344158',
    handleStyle: { color: '#5b7fff', borderColor: '#5b7fff' },
    dataBackground: {
      lineStyle: { color: '#69778c', width: 1 },
      areaStyle: { color: 'rgba(105, 119, 140, 0.22)' },
    },
    selectedDataBackground: {
      lineStyle: { color: '#5b7fff' },
      areaStyle: { color: 'rgba(91, 127, 255, 0.15)' },
    },
    textStyle: { color: '#9aa8bc', fontSize: 10 },
    moveHandleSize: 5,
    height: 28,
    bottom: 8,
  }],
  tooltip: {
    confine: true,
    backgroundColor: 'rgba(8, 12, 18, 0.98)',
    borderColor: '#3b4a63',
    borderWidth: 1,
    padding: [10, 12] as [number, number],
    textStyle: {
      color: '#e8ecf2',
      fontFamily: 'Segoe UI Variable Text, Avenir Next, sans-serif',
      fontSize: 12,
      lineHeight: 19,
    },
    extraCssText: 'padding: 10px 12px; border-radius: 8px; box-shadow: 0 18px 48px rgba(0,0,0,0.42), 0 4px 12px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.055); backdrop-filter: blur(18px); z-index: 9999; pointer-events: none; font-variant-numeric: tabular-nums;',
  },
  media: makeCompactChartMedia(),
} as const
