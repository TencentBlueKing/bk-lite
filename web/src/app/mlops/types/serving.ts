// ========== 模型发布参数类型 ==========
export interface ServingParams {
  name: string;
  description: string;
  model_version: string;
  status: string;
  train_job: string;
}

// ========== 推理请求类型 ==========
export interface ReasonLabelData {
  timestamp: string;
  value: string;
  label: number;
}

export interface AnomalyDetectionReasonParams {
  model_name: string;
  model_version: string;
  algorithm: string;
  data: ReasonLabelData[];
}

export interface ClassificationDataPoint {
  [key: string]: string | number; // 特征字段动态
}

export interface ClassificationReasonParams {
  model_name: string;
  model_version: string;
  algorithm: string;
  data: ClassificationDataPoint[];
}
