export interface TableDataItem {
  id?: number | string;
  [key: string]: any;
}

export interface DashboardBarChartProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

export interface ChartDataItem {
  name: string;
  value: number;
}

export interface SeriesDataItem {
  name: string;
  data: (number | null)[];
}

export interface LineBarChartData {
  categories: string[];
  values?: (number | null)[];
  series?: SeriesDataItem[];
}

export type PieChartData = ChartDataItem[];

export interface LineChartConfig {
  type: 'single' | 'multiple' | 'dual';
  key: string;
  value: string;
  tooltipField?: string;
  barField?: string;
  lineField?: string;
  barLabel?: string;
  lineLabel?: string;
}
