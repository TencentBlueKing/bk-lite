import { TopologyNodeData } from './topology';
import type { Dayjs } from 'dayjs';

export type FilterType = 'selector' | 'fixed';

export interface TimeConfig {
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface OtherConfig {
  timeSelector?: TimeConfig;
  [key: string]: unknown;
}

export interface TimeRangeData {
  start: number;
  end: number;
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export interface LayoutChangeItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface AddComponentConfig {
  name?: string;
  description?: string;
  dataSource?: string | number;
  chartType?: string;
  dataSourceParams?: DataSourceParam[];
}

export interface DataSourceParam {
  name: string;
  type: string;
  value: any;
  alias_name?: string;
  filterType?: 'params' | 'fixed' | 'filter';
}

export interface WidgetConfig {
  name?: string;
  chartType?: string;
  dataSource?: string | number;
  params?: { [key: string]: any };
  dataSourceParams?: any[];
}

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

export type ViewConfigItem = LayoutItem | TopologyNodeData;

export interface ViewConfigProps {
  open: boolean;
  item: ViewConfigItem;
  onConfirm?: (values: any) => void;
  onClose?: () => void;
}

export interface ComponentSelectorProps {
  visible: boolean;
  onCancel: () => void;
  onOpenConfig?: (item: any) => void;
}

export interface BaseWidgetProps {
  config?: any;
  globalTimeRange?: any;
  refreshKey?: number;
  onDataChange?: (data: any) => void;
  onReady?: (hasData?: boolean) => void;
}

export interface WidgetMeta {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  defaultConfig?: any;
}

export interface WidgetDefinition {
  meta: WidgetMeta;
  configComponent?: React.ComponentType<any>;
}