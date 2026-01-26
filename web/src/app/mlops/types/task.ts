import type { Option } from "@/types"

interface TrainJob {
  id: string | number,
  name: string,
  status?: string,
  created_at: string,
  train_data_id?: string | number;
  val_data_id?: string | number;
  test_data_id?: string | number;
  algorithm?: string;
  parameters?: string | Record<string, unknown>;
  dataset_id?: string | number;
  dataset?: string | number;
  dataset_version?: string | number;
  max_evals?: number;
}

interface TrainTaskModalProps {
  options?: Record<string, unknown>;
  onSuccess: () => void;
  activeTag: string[];
  datasetOptions: Option[];
}

interface AlgorithmParam {
  name: string;
  type: 'randint' | 'choice' | 'list' | 'boolean' | AlgorithmParam;
  default: string[] | number | [number, number];
  options?: Option[]
}

interface TrainTaskHistory {
  id: number;
  job_id: number;
  tenant_id: number;
  train_data_id: number;
  user_id: string;
  parameters: string;
  status: string;
  created_at?: string;
  started_at?: string;
  updated_at?: string;
  completed_at?: string;
  anomaly_detection_train_jobs: {
    name: string;
  }
}

// 算法配置相关类型
export type FieldType =
  | 'input'
  | 'inputNumber'
  | 'select'
  | 'multiSelect'
  | 'switch'
  | 'stringArray'; // 逗号分隔的字符串，内部转为数组

export interface FieldConfig {
  name: string | string[]; // 支持嵌套路径，如 ['search_space', 'n_estimators']
  label: string;
  type: FieldType;
  required?: boolean;
  tooltip?: string;
  placeholder?: string;
  defaultValue?: string | number | boolean | string[];
  options?: Option[]; // 用于 select/multiSelect
  min?: number; // 用于 inputNumber
  max?: number; // 用于 inputNumber
  step?: number; // 用于 inputNumber
  dependencies?: string[][]; // 依赖字段路径数组（支持多个依赖），如 [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_diff_features']]
  layout?: 'vertical' | 'horizontal'; // vertical: label在上, horizontal: label和input水平排列
}

export interface GroupConfig {
  title: string;
  subtitle?: string; // 子标题，如 "树结构参数"
  fields: FieldConfig[];
}

export interface AlgorithmConfig {
  algorithm: string;
  groups: {
    hyperparams: GroupConfig[];
    feature_engineering?: GroupConfig[];
    preprocessing?: GroupConfig[];
  };
}

export type {
  TrainJob,
  TrainTaskModalProps,
  AlgorithmParam,
  TrainTaskHistory
}