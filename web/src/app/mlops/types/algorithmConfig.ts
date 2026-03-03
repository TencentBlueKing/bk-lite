/**
 * 算法配置管理相关类型定义
 */

// 算法类型枚举
export type AlgorithmType =
  | 'anomaly_detection'
  | 'timeseries_predict'
  | 'log_clustering'
  | 'classification'
  | 'image_classification'
  | 'object_detection';

// 算法配置实体
export interface AlgorithmConfigEntity {
  id: number;
  algorithm_type: AlgorithmType;
  name: string;           // 算法标识: ECOD, XGBoost 等
  display_name: string;   // 显示名称
  scenario_description: string;  // 场景描述
  image: string;          // Docker 镜像
  form_config: FormConfig;  // 表单配置 JSON
  is_active: boolean;     // 是否启用
  created_by?: string;
  created_at?: string;
  updated_by?: string;
  updated_at?: string;
}

// 列表项（不含 form_config）
export interface AlgorithmConfigListItem {
  id: number;
  algorithm_type: AlgorithmType;
  name: string;
  display_name: string;
  scenario_description: string;
  image: string;
  is_active: boolean;
  created_by?: string;
  created_at?: string;
  updated_by?: string;
  updated_at?: string;
}

// 创建/更新参数
export interface AlgorithmConfigParams {
  algorithm_type: AlgorithmType;
  name: string;
  display_name: string;
  scenario_description: string;
  image: string;
  form_config: FormConfig;
  is_active?: boolean;
}

// 表单配置结构（与后端 form_config JSON 字段对应）
export interface FormConfig {
  groups: {
    hyperparams: GroupConfig[];
    preprocessing?: GroupConfig[];
    feature_engineering?: GroupConfig[];
  };
}

export interface GroupConfig {
  title: string;
  subtitle?: string;
  fields: FieldConfig[];
}

export type FieldType =
  | 'input'
  | 'inputNumber'
  | 'select'
  | 'multiSelect'
  | 'switch'
  | 'stringArray';

export interface FieldConfig {
  name: string | string[];
  label: string;
  type: FieldType;
  required?: boolean;
  tooltip?: string;
  placeholder?: string;
  defaultValue?: string | number | boolean | string[];
  options?: { label: string; value: string | number }[];
  min?: number;
  max?: number;
  step?: number;
  dependencies?: string[][];
  layout?: 'vertical' | 'horizontal';
}

// API 响应类型
export interface AlgorithmConfigListResponse {
  items: AlgorithmConfigListItem[];
  count: number;
}

// 查询参数
export interface AlgorithmConfigQueryParams {
  algorithm_type?: AlgorithmType;
  name?: string;
  display_name?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}
