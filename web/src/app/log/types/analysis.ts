export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  description?: string;
  valueConfig?: WidgetConfig;
}

export interface WidgetConfig {
  name?: string;
  chartType?: string;
  dataSource?: string | number;
  params?: { [key: string]: any };
  dataSourceParams?: any[];
}

export interface DirItem {
  id: string;
  name: string;
  desc?: string;
  filters?: Record<string, any>;
  other?: Record<string, any>;
  view_sets?: Array<any>;
}

export interface BaseWidgetProps {
  config?: any;
  globalTimeRange?: any;
  refreshKey?: number;
  otherConfig?: any;
  onDataChange?: (data: any) => void;
  onReady?: (hasData?: boolean) => void;
}
