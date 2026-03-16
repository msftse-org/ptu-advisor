/** Dark theme configuration for PTU Advisor ECharts. */
export const CHART_COLORS = {
  primary: '#5B7FFF',
  secondary: '#7B8EAF',
  success: '#2F9E77',
  danger: '#B35252',
  warning: '#C58A2A',
  neutral: '#9DAAC0',
  accent: '#A78BFA',
} as const

export const PTU_CHART_THEME = {
  color: [CHART_COLORS.primary, CHART_COLORS.success, CHART_COLORS.warning, CHART_COLORS.danger, CHART_COLORS.accent, CHART_COLORS.secondary],
  backgroundColor: 'transparent',
  textStyle: { color: '#a0aec0', fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11 },
  title: { textStyle: { color: '#e8ecf2' } },
  legend: {
    textStyle: { color: '#b5becc', fontSize: 11 },
    icon: 'roundRect',
    itemWidth: 12,
    itemHeight: 3,
  },
  grid: {
    left: 50,
    right: 16,
    top: 12,
    bottom: 60,
    containLabel: false,
  },
  categoryAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: 'rgba(120,140,170,0.12)', type: 'dashed' as const } },
    axisLabel: { color: '#8f9ec4', fontSize: 11 },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: 'rgba(120,140,170,0.12)', type: 'dashed' as const } },
    axisLabel: { color: '#8f9ec4', fontSize: 10 },
  },
  dataZoom: [{
    type: 'slider' as const,
    backgroundColor: 'rgba(26, 32, 44, 0.8)',
    fillerColor: 'rgba(91, 127, 255, 0.15)',
    borderColor: '#2d3748',
    handleStyle: { color: '#5b7fff', borderColor: '#5b7fff' },
    dataBackground: {
      lineStyle: { color: '#4a5568', width: 1 },
      areaStyle: { color: 'rgba(74, 85, 104, 0.3)' },
    },
    selectedDataBackground: {
      lineStyle: { color: '#5b7fff' },
      areaStyle: { color: 'rgba(91, 127, 255, 0.15)' },
    },
    textStyle: { color: '#a0aec0', fontSize: 10 },
    moveHandleSize: 5,
    height: 28,
    bottom: 8,
  }],
  tooltip: {
    backgroundColor: 'rgba(8, 14, 26, 0.96)',
    borderColor: 'rgba(91, 127, 255, 0.32)',
    borderWidth: 1,
    textStyle: { color: '#e8ecf2', fontSize: 12 },
    extraCssText: 'border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);',
  },
} as const
