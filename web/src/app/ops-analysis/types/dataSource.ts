import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';

export type ChartType =
  | 'line'
  | 'bar'
  | 'pie'
  | 'single'
  | 'multiValue'
  | 'table'
  | 'eventTable'
  | 'eventTimeline'
  | 'cardList'
  | 'topN'
  | 'gauge'
  | 'radar'
  | 'nodeGraph'
  | 'topologyMap'
  | 'room3D'
  | 'message';

export type DataSourceSourceType =
  | 'nats'
  | 'mysql'
  | 'postgresql'
  | 'rest_api'
  | 'excel'
  | 'prometheus';

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
  connection_overrides?: Record<string, any>;
  connection?: number | null;
  connection_id?: number | null;
  query_config?: Record<string, any>;
  transform_config?: {
    enabled?: boolean;
    language?: string;
    script?: string;
  };
  excel_materialization?: {
    status?: string;
    generation?: number;
    success_slot_id?: number | null;
    candidate_slot_id?: number | null;
    candidate_status?: string | null;
    error_code?: string;
    error_summary?: string;
    success_updated_at?: string | null;
    has_saved_source?: boolean;
    can_retry?: boolean;
  };
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
  is_build_in?: boolean;
}

export interface DataSourcePreviewResult {
  items: Record<string, any>[];
  count: number;
  fields: ResponseFieldDefinition[];
  warnings?: string[];
  raw_items?: Record<string, any>[];
  raw_count?: number;
  raw_fields?: ResponseFieldDefinition[];
  transform_error?: { code?: string; message?: string } | null;
}

export interface OperateModalProps {
  open: boolean;
  mode: 'add' | 'edit' | 'view';
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
    multiple?: boolean;
    maxCount?: number;
    /** select 专用：dropdown 为默认下拉；table 点击后弹表格批量勾选 */
    picker?: 'dropdown' | 'table';
  };

export interface ParamItem {
  id?: string;
  name: string;
  value: string | number | boolean | Array<string | number> | [number, number] | DateRangeValue | null | undefined;
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
