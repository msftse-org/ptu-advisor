import { describe, expect, it, vi } from 'vitest'

const { useMock, markAreaComponent } = vi.hoisted(() => ({
  useMock: vi.fn(),
  markAreaComponent: { type: 'markArea' },
}))

vi.mock('echarts/core', () => ({ use: useMock }))
vi.mock('echarts/charts', () => ({
  LineChart: { type: 'line' },
  BarChart: { type: 'bar' },
  CustomChart: { type: 'custom' },
}))
vi.mock('echarts/components', () => ({
  DataZoomComponent: { type: 'dataZoom' },
  DataZoomInsideComponent: { type: 'dataZoomInside' },
  DataZoomSliderComponent: { type: 'dataZoomSlider' },
  TooltipComponent: { type: 'tooltip' },
  GridComponent: { type: 'grid' },
  MarkLineComponent: { type: 'markLine' },
  MarkPointComponent: { type: 'markPoint' },
  MarkAreaComponent: markAreaComponent,
  LegendComponent: { type: 'legend' },
  TitleComponent: { type: 'title' },
  ToolboxComponent: { type: 'toolbox' },
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: { type: 'canvas' } }))

import './echarts-setup'

describe('ECharts component registration', () => {
  it('registers mark areas used by the Cost Explorer savings window', () => {
    expect(useMock).toHaveBeenCalledTimes(1)
    expect(useMock.mock.calls[0]?.[0]).toContain(markAreaComponent)
  })
})