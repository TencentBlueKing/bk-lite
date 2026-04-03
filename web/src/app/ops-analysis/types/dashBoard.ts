import { TopologyNodeData } from './topology';
import type { ParamItem, DatasourceItem } from './dataSource';
import type { Dayjs } from 'dayjs';

export type FilterType = 'selector' | 'fixed';

export interface EChartsInstance {
  dispatchAction: (action: {
    type: string;
    name?: string;
    [key: string]: unknown;
  }) => void;
  setOption: (option: unknown) => void;
  resize: () => void;
  dispose: () => void;
  [key: string]: unknown;
}

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
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
}

/** 表格筛选字段配置（组件级别） */
export interface TableFilterFieldConfig {
  key: string;
  label: string;
  inputType: 'keyword' | 'time_range' | 'select';
  options?: string[];
}

/** 表格列配置（组件级别） */
export interface TableColumnConfigItem {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
}

/** 表格组件配置 */
export interface TableConfig {
  filterFields?: TableFilterFieldConfig[];
  columns?: TableColumnConfigItem[];
}

export interface ValueConfig {
  chartType?: string;
  dataSource?: string | number;
  params?: Record<string, string | number | boolean | [number, number] | null>;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
}

export interface WidgetConfig extends ValueConfig {
  name: string;
  description?: string;
  tableConfig?: TableConfig;
}

export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  description?: string;
  valueConfig?: ValueConfig;
}

export type ViewConfigItem = LayoutItem | TopologyNodeData;

export interface ViewConfigProps {
  open: boolean;
  item: ViewConfigItem;
  onConfirm?: (values: WidgetConfig) => void;
  onClose?: () => void;
}

export interface ComponentSelectorProps {
  visible: boolean;
  onCancel: () => void;
  onOpenConfig?: (item: DatasourceItem) => void;
}

export interface BaseWidgetProps {
  config?: ValueConfig;
  globalTimeRange?: TimeRangeData;
  refreshKey?: number;
  onDataChange?: (data: unknown) => void;
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