/**
 * Tree-shaken ECharts module registration.
 * Only import the chart types and components we actually use.
 */
import * as echarts from 'echarts/core'
import { LineChart, BarChart, CustomChart } from 'echarts/charts'
import {
  DataZoomComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  TooltipComponent,
  GridComponent,
  MarkLineComponent,
  MarkPointComponent,
  LegendComponent,
  ToolboxComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  CustomChart,
  CanvasRenderer,
  DataZoomComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  TooltipComponent,
  GridComponent,
  MarkLineComponent,
  MarkPointComponent,
  LegendComponent,
  ToolboxComponent,
])

export { echarts }
