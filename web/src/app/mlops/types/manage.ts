import { ObjectDetectionMetadata, YOLOAnnotation } from './index'

enum TrainingStatus {
  'not_stared',
  'in_progress',
  'completed',
  'failed'
}

interface AnomalyTrainData {
  id: number;
  tenant_id: number;
  dataset_id: number;
  name: string,
  storage_path: string,
  metadata: Record<string, unknown>;
  user_id: string;
  latest_status?: TrainingStatus;
}

interface AsideProps {
  // children: any,
  menuItems: AnomalyTrainData[],
  loading: boolean,
  isChange: boolean,
  onChange: (value: boolean) => void,
  changeFlag: (value: boolean) => void
}

interface TrainData {
  id: number;
  name: string;
  dataset_id: string | number;
  is_train_data: boolean,
  is_val_data: boolean,
  is_test_data: boolean,
}

interface TrainDataModalProps {
  options?: Record<string, unknown>;
  onSuccess: () => void;
  trainData: TrainData[];
}


interface DataSet {
  id: number;
  name: string;
  description: string;
  icon: string;
  creator: string;
  // user_id: string;
  // tenant_id: number;
}

interface AnomalyDataSet {
  id: number,
  tenant_id: number,
  description: string,
  has_labels: boolean,
  created_at: string,
  user_id: string,
  name?: string,
  storage_path?: string,
}

interface LabelData {
  timestamp: string,
  value: number,
  label?: number
}

interface AnnotationData {
  timestamp: number;
  value: number;
  label: number;
  index?: number;
  [key: string]: unknown;
}


interface RasaMenus {
  menu: string;
  icon: string;
  content: string;
}

// ========== 训练数据更新参数 ==========
export interface BaseTrainDataUpdateParams {
  is_train_data?: boolean;
  is_val_data?: boolean;
  is_test_data?: boolean;
}

export interface AnomalyTrainDataUpdateParams extends BaseTrainDataUpdateParams {
  meta_data?: Record<string, unknown>;
  train_data?: LabelData[];
}

export interface ObjectDetectionTrainDataUpdateParams extends BaseTrainDataUpdateParams {
  meta_data?: ObjectDetectionMetadata;
  train_data?: YOLOAnnotation[];
}

export interface ImageClassificationTrainDataUpdateParams extends BaseTrainDataUpdateParams {
  meta_data?: Record<string, unknown>;
}

// ========== 目标检测相关类型 ==========
export interface ObjectDetectionTrainData {
  width: number;
  height: number;
  image_url: string;
  image_name: string;
  image_size: number;
  batch_index: number;
  batch_total: number;
  content_type: string;
  type: string;
}

// ========== 标注相关类型 ==========
export interface AnnotationLabel {
  id: string;
  label: string;
  coordinates: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export type {
  AsideProps,
  TrainingStatus,
  AnomalyTrainData,
  TrainDataModalProps,
  TrainData,
  DataSet,
  AnomalyDataSet,
  LabelData,
  AnnotationData,
  RasaMenus
}