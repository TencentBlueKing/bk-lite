import * as echarts from 'echarts/core';
import { CustomChart, LineChart, PieChart, TreemapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  GraphicComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  CustomChart,
  LineChart,
  PieChart,
  TreemapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  GraphicComponent,
  CanvasRenderer
]);

export default echarts;
