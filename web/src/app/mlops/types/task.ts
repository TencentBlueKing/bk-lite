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
}

export interface UpdateTrainJobParams extends Partial<CreateTrainJobParams> {
  id?: never; // 防止在 params 中传递 id
}

// ========== 表单数据类型 ==========
export interface TrainJobFormValues {
  name: string;
  algorithm: string;
  dataset: number;
  dataset_version: number;
  max_evals: number;
  // 动态算法参数（根据 AlgorithmConfig 生成）
  [key: string]: unknown;
}

export type {
  TrainJob,
  TrainTaskModalProps,
  AlgorithmParam,
  TrainTaskHistory
}