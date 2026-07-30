import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';

export type ChartType =
  | 'line'
  | 'bar'
  | 'pie'
  | 'single'
  | 'multiValue'
  | 'table'
  | 'eventTable'
  | 'topN'
  | 'gauge'
  | 'room3D'
  | 'message';

export type DataSourceSourceType =
  | 'nats'
  | 'mysql'
  | 'postgresql'
  | 'rest_api'
  | 'excel';

/** 接口返回字段定义（数据源级配置） */
export interface ResponseFieldDefinition {
  key: string;
  title: string;
  value_type: 'string' | 'number' | 'boolean' | 'datetime';
  description?: string;
}

/** 接口字段定义配置（数据源级别） */

/** 表格列配置（组件级别的列配置） */
export interface TableColumnConfig {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
}

/** 表格默认配置（数据源级别的默认列配置） */
export interface TableDefaultConfig {
  columns: TableColumnConfig[];
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
  source_type?: DataSourceSourceType;
  /** 普通列表接口返回；分享元数据刻意不返回，避免暴露内部执行路径 */
  rest_api?: string;
  connection_config?: Record<string, any>;
  query_config?: Record<string, any>;
  desc: string;
  // [内部预留] is_active 字段仅后端/导入导出链路使用，前端不再暴露
  params: ParamItem[];
  chart_type: ChartType[];
  namespaces: number[];
  namespace_options?: Array<{
    id: number;
    name: string;
  }>;
  tag?: number[];
  groups?: number[];
  hasAuth?: boolean;
  field_schema?: ResponseFieldDefinition[];
}

export interface DataSourcePreviewResult {
  items: Record<string, any>[];
  count: number;
  fields: ResponseFieldDefinition[];
}

export interface OperateModalProps {
  open: boolean;
  currentRow?: DatasourceItem;
  onClose: () => void;
  onSuccess?: () => void;
}

export type DataSourceParamFilterType =
  | 'filter'
  | 'fixed'
  | 'params';
export interface InputOption {
  label: string;
  value: string | number;
}

export interface RestApiSourceRef {
  type: 'rest_api';
  value: string;
}

export type SourceRef = RestApiSourceRef;

export interface StaticOptionsSource {
  type: 'static';
  staticItems: InputOption[];
}

export interface DynamicOptionsSource {
  type: 'dynamic';
  sourceId?: number;
  sourceRef?: SourceRef;
  valueField: string;
  labelField: string;
}

export type InputControlConfig =
  | {
    control: 'input';
  }
  | {
    control: 'select' | 'radio';
    optionsSource: StaticOptionsSource | DynamicOptionsSource;
    componentSwitch?: boolean;
  };

export interface ParamItem {
  id?: string;
  name: string;
  value: string | number | boolean | [number, number] | DateRangeValue | null;
  alias_name: string;
  type?: string;
  filterType?: DataSourceParamFilterType;
  desc?: string;
  required?: boolean;
  /**
   * 旧字段：手动下拉选项，只读兼容历史数据；
   * 新配置写入 inputConfig。
   */
  options?: Array<{ label: string; value: string | number }>;
  /**
   * 新字段：参数输入控件配置（文本输入 / 静态选项 / 动态数据源）。
   */
  inputConfig?: InputControlConfig;
}
