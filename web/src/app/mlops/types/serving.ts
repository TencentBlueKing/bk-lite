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

// 异常检测推理参数（通过后端代理）
export interface AnomalyDetectionReasonParams {
  url: string;  // 服务器地址，如 http://192.168.1.100
  data: Array<{ timestamp: number; value: number }>;  // 时序数据
  config?: {
    threshold?: number;
  };
}

// 时序预测推理参数
export interface TimeseriesPredictReasonParams {
  url: string;
  data: Array<{ timestamp: number; value: number }>;
  config: {
    steps: number;  // 预测步数（必填）
  };
}

// 日志聚类推理参数
export interface LogClusteringReasonParams {
  url: string;
  data: string[];  // 日志文本数组
  config?: {
    return_details?: boolean;
    max_samples?: number;
    sort_by?: string;
  };
}

// 文本分类推理参数
export interface ClassificationReasonParams {
  url: string;
  texts: string[];  // 待分类文本数组
  config?: {
    top_k?: number;
    return_probabilities?: boolean;
    return_feature_importance?: boolean;
  };
}

// 图片分类推理参数
export interface ImageClassificationReasonParams {
  url: string;
  images: string[];  // base64 编码的图片数组
  config?: {
    top_k?: number;
  };
}

// 目标检测推理参数
export interface ObjectDetectionReasonParams {
  url: string;
  images: string[];  // base64 编码的图片数组
  config?: {
    conf_threshold?: number;
    iou_threshold?: number;
    max_detections?: number;
  };
}

// 通用推理参数（用于配置驱动的 API 调用）
export type ReasonParams = 
  | AnomalyDetectionReasonParams
  | TimeseriesPredictReasonParams
  | LogClusteringReasonParams
  | ClassificationReasonParams
  | ImageClassificationReasonParams
  | ObjectDetectionReasonParams;

export interface ClassificationDataPoint {
  [key: string]: string | number; // 特征字段动态
}
