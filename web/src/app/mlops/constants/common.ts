import { LevelMap, DatasetType } from "@/app/mlops/types";

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
};

const TRAIN_STATUS_MAP = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error'
};

const TYPE_CONTENT: Record<string, any> = {
  is_test_data: 'test',
  is_train_data: 'train',
  is_val_data: 'validate',
};

const TYPE_COLOR: Record<string, any> = {
  is_test_data: 'orange',
  is_train_data: 'blue',
  is_val_data: 'green',
};

const TRAIN_TEXT = {
  pending: 'notStarted',
  running: 'inProgress',
  completed: 'completed',
  failed: 'failed'
};

const ANOMALY_ALGORITHMS_TYPE: Record<string, any> = {
  'RandomForest': {
    n_estimators: 'randint',
    max_depth: 'randint',
    min_samples_split: 'randint',
    min_samples_leaf: 'randint',
    max_features: 'choice',
    bootstrap: 'choice',
    class_weight: 'choice'
  }
};

const LOG_CLUSTERING_ALGORITHMS_TYPE: Record<string, any> = {
  'KMeans': {},
  'DBSCAN': {},
  'AgglomerativeClustering': {},
  'Drain': {},
  'LogCluster': {},
};

const TIMESERIES_PREDICT_ALGORITHMS_TYPE: Record<string, any> = {
  // 'Prophet': {},
  'GradientBoosting': {
    metric: 'choice',
    learning_rate: 'randint',
    max_depth: 'randint',
    min_samples_split: 'randint',
    min_samples_leaf: 'randint',
    subsample: 'randint',
    lag_features: 'randint',
    n_estimators: 'randint',
    feature_engineering: 'choice'
  }
};

const ALGORITHMS_TYPE: Record<string, any> = {
  ...ANOMALY_ALGORITHMS_TYPE,
  ...LOG_CLUSTERING_ALGORITHMS_TYPE,
  ...TIMESERIES_PREDICT_ALGORITHMS_TYPE
};

type TRAIN_STATUS = 'not_started' | 'in_progress' | 'completed' | 'failed';

const DATASET_MAP: Record<DatasetType, string> = {
  [DatasetType.ANOMALY_DETECTION]: 'anomaly_detection_datasets',
  [DatasetType.CLASSIFICATION]: 'classification_datasets',
  [DatasetType.TIMESERIES_PREDICT]: 'timeseries_predict_datasets',
  [DatasetType.LOG_CLUSTERING]: 'log_clustering_datasets',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image_classification_datasets',
  [DatasetType.OBJECT_DETECTION]: 'object_detection_datasets',
};

const TRAINDATA_MAP: Partial<Record<DatasetType, string>> = {
  [DatasetType.ANOMALY_DETECTION]: 'anomaly_detection_train_data',
  [DatasetType.CLASSIFICATION]: 'classification_train_data',
  [DatasetType.TIMESERIES_PREDICT]: 'timeseries_predict_train_data',
  [DatasetType.LOG_CLUSTERING]: 'log_clustering_train_data',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image_classification_train_data',
  [DatasetType.OBJECT_DETECTION]: 'object_detection_train_data',
};

const TRAINJOB_MAP: Record<DatasetType, string> = {
  [DatasetType.ANOMALY_DETECTION]: 'anomaly_detection_train_jobs',
  [DatasetType.CLASSIFICATION]: 'classification_train_jobs',
  [DatasetType.TIMESERIES_PREDICT]: 'timeseries_predict_train_jobs',
  [DatasetType.LOG_CLUSTERING]: 'log_clustering_train_jobs',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image_classification_train_jobs',
  [DatasetType.OBJECT_DETECTION]: 'object_detection_train_jobs',
};

const DATASET_RELEASE_MAP: Partial<Record<DatasetType, string>> = {
  [DatasetType.ANOMALY_DETECTION]: 'anomaly_detection_dataset_releases',
  [DatasetType.CLASSIFICATION]: 'classification_dataset_releases',
  [DatasetType.TIMESERIES_PREDICT]: 'timeseries_predict_dataset_releases',
  [DatasetType.LOG_CLUSTERING]: 'log_clustering_dataset_releases',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image_classification_dataset_releases',
  [DatasetType.OBJECT_DETECTION]: 'object_detection_dataset_releases'
};

const SERVING_MAP: Partial<Record<DatasetType, string>> = {
  [DatasetType.ANOMALY_DETECTION]: 'anomaly_detection_servings',
  [DatasetType.CLASSIFICATION]: 'classification_servings',
  [DatasetType.TIMESERIES_PREDICT]: 'timeseries_predict_servings',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image_classification_servings',
  [DatasetType.LOG_CLUSTERING]: 'log_clustering_servings',
  [DatasetType.OBJECT_DETECTION]: 'object_detection_servings'
};

const TYPE_FILE_MAP: Partial<Record<DatasetType, string>> = {
  [DatasetType.ANOMALY_DETECTION]: 'csv',
  [DatasetType.LOG_CLUSTERING]: 'txt',
  [DatasetType.TIMESERIES_PREDICT]: 'csv',
  [DatasetType.CLASSIFICATION]: 'csv',
  [DatasetType.IMAGE_CLASSIFICATION]: 'image',
  [DatasetType.OBJECT_DETECTION]: 'image'
};

export {
  LEVEL_MAP,
  TRAIN_STATUS_MAP,
  TRAIN_TEXT,
  TYPE_CONTENT,
  TYPE_COLOR,
  ALGORITHMS_TYPE,
  ANOMALY_ALGORITHMS_TYPE,
  LOG_CLUSTERING_ALGORITHMS_TYPE,
  TIMESERIES_PREDICT_ALGORITHMS_TYPE,
  type TRAIN_STATUS,
  DATASET_MAP,
  TRAINDATA_MAP,
  TRAINJOB_MAP,
  DATASET_RELEASE_MAP,
  SERVING_MAP,
  TYPE_FILE_MAP
};
