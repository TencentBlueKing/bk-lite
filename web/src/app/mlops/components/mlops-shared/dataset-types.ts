export enum DatasetType {
  ANOMALY_DETECTION = 'anomaly_detection',
  CLASSIFICATION = 'classification',
  TIMESERIES_PREDICT = 'timeseries_predict',
  LOG_CLUSTERING = 'log_clustering',
  IMAGE_CLASSIFICATION = 'image_classification',
  OBJECT_DETECTION = 'object_detection',
}

export const ALGORITHM_TYPES = Object.values(DatasetType);

export const ALGORITHM_TYPE_CONFIG: Record<
  DatasetType,
  { labelKey: string; icon: string }
> = {
  [DatasetType.ANOMALY_DETECTION]: {
    labelKey: 'datasets.anomaly',
    icon: 'yichangjiance',
  },
  [DatasetType.TIMESERIES_PREDICT]: {
    labelKey: 'datasets.timeseriesPredict',
    icon: 'shixuyuce',
  },
  [DatasetType.LOG_CLUSTERING]: {
    labelKey: 'datasets.logClustering',
    icon: 'rizhijulei',
  },
  [DatasetType.CLASSIFICATION]: {
    labelKey: 'datasets.classification',
    icon: 'wenbenfenlei',
  },
  [DatasetType.IMAGE_CLASSIFICATION]: {
    labelKey: 'datasets.imageClassification',
    icon: 'tupianfenlei',
  },
  [DatasetType.OBJECT_DETECTION]: {
    labelKey: 'datasets.objectDetection',
    icon: 'mubiaojiance',
  },
};

export function isValidAlgorithmType(type: string): type is DatasetType {
  return ALGORITHM_TYPES.includes(type as DatasetType);
}
