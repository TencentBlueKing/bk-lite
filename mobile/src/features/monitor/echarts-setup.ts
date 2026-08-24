import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  AxisPointerComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  MarkAreaComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export default echarts;
