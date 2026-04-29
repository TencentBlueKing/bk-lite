import type { Option } from "@/types"
// 复用 algorithmConfig 中的类型定义
export type { FieldType, FieldConfig, GroupConfig, FormConfig as AlgorithmConfig } from './algorithmConfig';

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
  hyperopt_config?: HyperoptConfig;
  team?: number[];
}

// 超参数配置类型
export interface HyperoptConfig {
  hyperparams?: Record<string, unknown>;
  preprocessing?: Record<string, unknown>;
  feature_engineering?: Record<string, unknown>;
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
  run_id: string;
  run_name: string;
  status: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_minutes: number;
  is_latest_run?: boolean;
  can_delete_run?: boolean;
  delete_block_reason?: string | null;
}

// ========== API 参数类型 ==========
export interface CreateTrainJobParams {
  name: string;
  algorithm: string;
  dataset: number;
  dataset_version: number;
  max_evals: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  description: string;
  hyperopt_config: HyperoptConfig;
  team: number[];
}

export interface UpdateTrainJobParams extends Partial<CreateTrainJobParams> {
  id?: never; // 防止在 params 中传递 id
}

// ========== 表单数据类型 ==========
export interface TrainJobFormValues {
  name: string;
  algorithm: string;
  dataset: number;
  dataset_version: number | string;  // 表单中使用字符串（Select 组件），提交时转为数字
  max_evals: number;
  team: number[];
  // 动态算法参数（根据 AlgorithmConfig 生成）
  [key: string]: unknown;
}

export type {
  TrainJob,
  TrainTaskModalProps,
  AlgorithmParam,
  TrainTaskHistory
}
