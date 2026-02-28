/**
 * Serving related constants for MLOps
 */

import { DatasetType } from '@/app/mlops/types';

// Request examples for each algorithm type
export const REQUEST_EXAMPLES: Record<DatasetType, object> = {
  [DatasetType.ANOMALY_DETECTION]: {
    data: [
      { timestamp: 1700000000, value: 100.5 },
      { timestamp: 1700000060, value: 102.3 },
      { timestamp: 1700000120, value: 98.7 }
    ],
    config: {
      threshold: 0.8
    }
  },
  [DatasetType.TIMESERIES_PREDICT]: {
    data: [
      { timestamp: 1700000000, value: 100.5 },
      { timestamp: 1700000060, value: 102.3 },
      { timestamp: 1700000120, value: 98.7 }
    ],
    config: {
      steps: 5
    }
  },
  [DatasetType.LOG_CLUSTERING]: {
    data: [
      "2024-01-15 10:23:45 ERROR Failed to connect to database server",
      "2024-01-15 10:23:46 ERROR Connection timeout to database",
      "2024-01-15 10:23:47 INFO User login successful",
      "2024-01-15 10:23:48 WARN Memory usage exceeded 80%"
    ],
    config: {
      return_details: true
    }
  },
  [DatasetType.CLASSIFICATION]: {
    texts: [
      "服务器CPU使用率异常升高",
      "数据库连接池耗尽",
      "网络延迟超过阈值"
    ],
    config: {
      top_k: 3,
      return_probabilities: true
    }
  },
  [DatasetType.IMAGE_CLASSIFICATION]: {
    images: [
      "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    ],
    config: {
      top_k: 3
    }
  },
  [DatasetType.OBJECT_DETECTION]: {
    images: [
      "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    ],
    config: {
      conf_threshold: 0.5,
      iou_threshold: 0.45
    }
  },
};

// Response examples for each algorithm type
export const RESPONSE_EXAMPLES: Record<DatasetType, object> = {
  [DatasetType.ANOMALY_DETECTION]: {
    data: [
      { timestamp: 1700000000, value: 100.5, is_anomaly: false, score: 0.12 },
      { timestamp: 1700000060, value: 102.3, is_anomaly: false, score: 0.15 },
      { timestamp: 1700000120, value: 98.7, is_anomaly: true, score: 0.89 }
    ]
  },
  [DatasetType.TIMESERIES_PREDICT]: {
    predictions: [
      { timestamp: 1700000180, value: 101.2 },
      { timestamp: 1700000240, value: 103.5 },
      { timestamp: 1700000300, value: 99.8 },
      { timestamp: 1700000360, value: 102.1 },
      { timestamp: 1700000420, value: 100.9 }
    ]
  },
  [DatasetType.LOG_CLUSTERING]: {
    clusters: [
      {
        cluster_id: 0,
        template: "ERROR * to connect to database *",
        count: 2,
        logs: [
          "2024-01-15 10:23:45 ERROR Failed to connect to database server",
          "2024-01-15 10:23:46 ERROR Connection timeout to database"
        ]
      },
      {
        cluster_id: 1,
        template: "INFO User login *",
        count: 1,
        logs: ["2024-01-15 10:23:47 INFO User login successful"]
      }
    ],
    total_clusters: 3
  },
  [DatasetType.CLASSIFICATION]: {
    results: [
      {
        text: "服务器CPU使用率异常升高",
        prediction: "performance",
        probabilities: { performance: 0.85, network: 0.10, database: 0.05 }
      }
    ]
  },
  [DatasetType.IMAGE_CLASSIFICATION]: {
    results: [
      {
        image_index: 0,
        prediction: "server_rack",
        top_k: [
          { label: "server_rack", probability: 0.92 },
          { label: "network_switch", probability: 0.05 },
          { label: "storage_device", probability: 0.03 }
        ]
      }
    ]
  },
  [DatasetType.OBJECT_DETECTION]: {
    results: [
      {
        image_index: 0,
        detections: [
          {
            class: "server",
            confidence: 0.95,
            bbox: { x1: 100, y1: 50, x2: 300, y2: 200 }
          },
          {
            class: "cable",
            confidence: 0.87,
            bbox: { x1: 150, y1: 180, x2: 250, y2: 350 }
          }
        ]
      }
    ]
  },
};

// Default test request body for each algorithm type
export const DEFAULT_TEST_BODY: Record<DatasetType, object> = {
  [DatasetType.ANOMALY_DETECTION]: {
    data: [
      { timestamp: 1700000000, value: 100.5 },
      { timestamp: 1700000060, value: 102.3 },
      { timestamp: 1700000120, value: 98.7 }
    ]
  },
  [DatasetType.TIMESERIES_PREDICT]: {
    data: [
      { timestamp: 1700000000, value: 100.5 },
      { timestamp: 1700000060, value: 102.3 },
      { timestamp: 1700000120, value: 98.7 }
    ],
    config: {
      steps: 5
    }
  },
  [DatasetType.LOG_CLUSTERING]: {
    data: [
      "2024-01-15 10:23:45 ERROR Failed to connect to database server",
      "2024-01-15 10:23:46 ERROR Connection timeout to database",
      "2024-01-15 10:23:47 INFO User login successful"
    ]
  },
  [DatasetType.CLASSIFICATION]: {
    texts: [
      "服务器CPU使用率异常升高",
      "数据库连接池耗尽"
    ]
  },
  [DatasetType.IMAGE_CLASSIFICATION]: {
    images: []
  },
  [DatasetType.OBJECT_DETECTION]: {
    images: []
  },
};

// I18n keys for request/response tips
export const TIP_KEYS: Record<DatasetType, { request: string; response: string }> = {
  [DatasetType.ANOMALY_DETECTION]: {
    request: 'serving-guide.tip.anomalyDetection.request',
    response: 'serving-guide.tip.anomalyDetection.response',
  },
  [DatasetType.TIMESERIES_PREDICT]: {
    request: 'serving-guide.tip.timeseriesPredict.request',
    response: 'serving-guide.tip.timeseriesPredict.response',
  },
  [DatasetType.LOG_CLUSTERING]: {
    request: 'serving-guide.tip.logClustering.request',
    response: 'serving-guide.tip.logClustering.response',
  },
  [DatasetType.CLASSIFICATION]: {
    request: 'serving-guide.tip.classification.request',
    response: 'serving-guide.tip.classification.response',
  },
  [DatasetType.IMAGE_CLASSIFICATION]: {
    request: 'serving-guide.tip.imageClassification.request',
    response: 'serving-guide.tip.imageClassification.response',
  },
  [DatasetType.OBJECT_DETECTION]: {
    request: 'serving-guide.tip.objectDetection.request',
    response: 'serving-guide.tip.objectDetection.response',
  },
};

// Get data field name for different algorithm types
export const getDataFieldName = (algorithmType: DatasetType): string => {
  switch (algorithmType) {
    case DatasetType.CLASSIFICATION:
      return 'texts';
    case DatasetType.IMAGE_CLASSIFICATION:
    case DatasetType.OBJECT_DETECTION:
      return 'images';
    default:
      return 'data';
  }
};
