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
  rest_api: string;
  desc: string;
  // [内部预留] is_active 字段仅后端/导入导出链路使用，前端不再暴露
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

export interface OperateModalProps {
  open: boolean;
  currentRow?: DatasourceItem;
  onClose: () => void;
  onSuccess?: () => void;
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
