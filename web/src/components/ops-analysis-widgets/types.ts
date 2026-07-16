import type { Dayjs } from 'dayjs';
import type {
  ThresholdColorConfig,
  ValueMapping,
} from '@/components/ops-analysis-config-sections/types';

export type ChartType =
  | 'line'
  | 'bar'
  | 'pie'
  | 'single'
  | 'table'
  | 'eventTable'
  | 'topN'
  | 'gauge'
  | 'message';

export interface ResponseFieldDefinition {
  key: string;
  title: string;
  value_type: 'string' | 'number' | 'boolean' | 'datetime';
  description?: string;
}

export interface TableColumnConfig {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
}

export interface TableDefaultConfig {
  columns: TableColumnConfig[];
}

export interface ParamItem {
  id?: string;
  name: string;
  value: string | number | boolean | [number, number] | null;
  alias_name: string;
  type?: string;
  filterType?: string;
  desc?: string;
  required?: boolean;
  options?: Array<{ label: string; value: string | number }>;
}

export interface DatasourceItem {
  id: number;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  domain: string;
  updated_by_domain: string;
  name: string;
  rest_api: string;
  desc: string;
  params: ParamItem[];
  chart_type: ChartType[];
  namespaces: number[];
  namespace_options?: Array<{
    id: number;
    name: string;
  }>;
  tag: number[];
  groups?: number[];
  hasAuth?: boolean;
  field_schema?: ResponseFieldDefinition[];
}

export interface TimeRangeValue {
  start: string;
  end: string;
  selectValue?: number;
}

export type FilterValue = string | number | TimeRangeValue | null;

export interface FilterOption {
  label: string;
  value: string;
}

export interface UnifiedFilterDefinition {
  id: string;
  key: string;
  name: string;
  type: 'timeRange' | 'string';
  defaultValue?: FilterValue;
  order: number;
  enabled: boolean;
  inputMode?: 'input' | 'select' | 'radio' | 'organization';
  options?: FilterOption[];
}

export interface DashboardFiltersState {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
}

export type DashboardFilters = UnifiedFilterDefinition[];

export interface FilterBindings {
  [filterId: string]: boolean;
}

export interface ScannedFilterParam {
  key: string;
  type: 'string' | 'timeRange';
  componentCount: number;
  sampleAlias: string;
  sampleDefaultValue: FilterValue;
}

export interface BindingValidationResult {
  filterId: string;
  isValid: boolean;
  reason?: 'filter_not_found' | 'param_not_found' | 'type_mismatch';
}

export interface TableFilterFieldConfig {
  key: string;
  label: string;
  inputType: 'keyword' | 'time_range' | 'select';
  options?: string[];
}

export interface TableColumnConfigItem {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
  columnType?: 'data' | 'actions';
  valueMappings?: ValueMapping[];
  cellType?: 'text' | 'colorBackground' | 'gauge';
  cellThresholdColors?: ThresholdColorConfig[];
  cellMax?: number;
}

export interface TableConfig {
  filterFields?: TableFilterFieldConfig[];
  columns?: TableColumnConfigItem[];
}

export interface DashboardActionParamMapping {
  key: string;
  source: 'rowField' | 'fixed';
  sourceKey?: string;
  value?: string | number | boolean | null;
}

export interface DashboardActionConfig {
  columnKey: string;
  text: string;
  url?: string;
  openMode?: 'sameTab' | 'newTab';
  params?: DashboardActionParamMapping[];
}

export interface ValueConfig {
  chartType?: string;
  dataSource?: string | number;
  compare?: boolean;
  params?: Record<string, string | number | boolean | [number, number] | null>;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
  filterBindings?: FilterBindings;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueMapping[];
  stack?: boolean;
  fillOpacity?: number;
  content?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  thresholdColors?: ThresholdColorConfig[];
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
}

export interface OpsAnalysisWidgetContractPreview {
  chartType?: string;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  timeRange?: [Dayjs, Dayjs] | null;
}
