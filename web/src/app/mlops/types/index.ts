import React from 'react';

/**
 * Dataset types supported by the ML Ops platform
 * 
 * @enum {string}
 * @property {string} ANOMALY_DETECTION - Anomaly detection datasets (异常检测)
 * @property {string} CLASSIFICATION - Text classification datasets (文本分类)
 * @property {string} TIMESERIES_PREDICT - Time series prediction datasets (时序预测)
 * @property {string} LOG_CLUSTERING - Log clustering datasets (日志聚类)
 * @property {string} IMAGE_CLASSIFICATION - Image classification datasets (图片分类)
 * @property {string} OBJECT_DETECTION - Object detection datasets (目标检测)
 */
export enum DatasetType {
  ANOMALY_DETECTION = 'anomaly_detection',
  CLASSIFICATION = 'classification',
  TIMESERIES_PREDICT = 'timeseries_predict',
  LOG_CLUSTERING = 'log_clustering',
  IMAGE_CLASSIFICATION = 'image_classification',
  OBJECT_DETECTION = 'object_detection',
}

export interface Option {
  label: string;
  value: string | number;
}

export interface ColumnItem {
  title: string;
  dataIndex: string;
  key: string;
  render?: (_: unknown, record: any) => React.ReactElement;
  [key: string]: unknown;
}

export interface MetricItem {
  id: number;
  metric_group: number;
  metric_object: number;
  name: string;
  type: string;
  display_name?: string;
  display_description?: string;
  instance_id_keys?: string[];
  dimensions: any[];
  query?: string;
  unit?: string;
  displayType?: string;
  description?: string;
  viewData?: any[];
  style?: {
    width: string;
    height: string;
  };
  [key: string]: unknown;
}

export interface ListItem {
  title?: string;
  label?: string;
  name?: string;
  display_name?: string;
  id?: string | number;
  value?: string | number;
}

export interface ChartData {
  timestamp: number;
  value1?: number;
  value2?: number;
  details?: Record<string, any>;
  [key: string]: unknown;
}

export interface TableDataItem {
  id?: number | string;
  [key: string]: any;
}

export interface ThresholdField {
  level: string;
  method: string;
  value: number | null;
}

export interface LevelMap {
  critical: string;
  error: string;
  warning: string;
  [key: string]: unknown;
}


//调用弹窗的类型
export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

export interface UserProfile {
  id: string,
  first_name: string,
  last_name: string
}

//调用弹窗接口传入的类型
export interface ModalConfig {
  type: string;
  title?: string;
  form?: any;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  nodes?: string[];
}

export interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

export interface TableData {
  id: number,
  name: string,
  anomaly?: number,
  [key: string]: any
}

export interface NodeType {
  type: string;
  label: string;
  color?: string;
  icon: string;
}

export interface NodeData {
  name: string;
  source: any[],
  target: any[],
  [key: string]: any
}

// YOLO格式的标注数据
export interface YOLOAnnotation {
  class_id: number;
  class_name: string;
  x_center: number;
  y_center: number;
  width: number;
  height: number;
}

// Object Detection 元数据结构
export interface ObjectDetectionMetadata {
  format: 'YOLO';
  classes: string[];
  num_classes: number;
  num_images: number;
  labels: Record<string, YOLOAnnotation[]>;
  statistics: {
    total_annotations: number;
    images_with_annotations: number;
    images_without_annotations: number;
    class_distribution: Record<string, number>;
  };
}

// 数据集版本发布
export interface DatasetRelease {
  id: number;
  dataset: number;
  version: string;
  name?: string;
  description?: string;
  train_file_id: number;
  val_file_id: number;
  test_file_id: number;
  created_at: string;
  is_archived: boolean;
}

// ========== 导出子模块类型 ==========
export * from './task';
export * from './manage';
export * from './serving';
