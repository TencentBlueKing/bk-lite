import { FormInstance } from 'antd';
import { useMemo, RefObject } from 'react';
import type { Option } from '@/types';
import { DatasetType, TrainJob, CreateTrainJobParams, UpdateTrainJobParams, DatasetRelease } from '@/app/mlops/types';
import { useGenericDatasetForm } from './forms/useGenericDatasetForm';
import useMlopsTaskApi from '@/app/mlops/api/task';

interface UseTaskFormProps {
  datasetOptions: Option[];
  activeTag: string[];
  onSuccess: () => void;
  formRef: RefObject<FormInstance>
}

/**
 * 统一的训练任务表单 Hook
 * 根据 activeType 动态选择对应的 API 方法，只初始化当前类型的表单
 * 避免同时加载所有 6 种算法类型的配置
 */
const useTaskForm = ({ datasetOptions, activeTag, onSuccess, formRef }: UseTaskFormProps) => {
  const [activeType] = activeTag;
  
  const {
    addAnomalyTrainTask,
    updateAnomalyTrainTask,
    addClassificationTrainTask,
    updateClassificationTrainTask,
    addTimeSeriesTrainTask,
    updateTimeSeriesTrainTask,
    addLogClusteringTrainTask,
    updateLogClusteringTrainTask,
    addImageClassificationTrainTask,
    updateImageClassificationTrainTask,
    addObjectDetectionTrainTask,
    updateObjectDetectionTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  // 根据 activeType 动态选择 API 方法
  const apiMethods = useMemo(() => {
    const apiMethodsMap: Record<string, {
      addTask: (params: CreateTrainJobParams) => Promise<TrainJob>;
      updateTask: (id: string, params: UpdateTrainJobParams) => Promise<TrainJob>;
      getDatasetReleases: (datasetType: DatasetType, params: { dataset: number }) => Promise<DatasetRelease[]>;
      getDatasetReleaseByID: (datasetType: DatasetType, id: number) => Promise<DatasetRelease>;
    }> = {
      [DatasetType.ANOMALY_DETECTION]: {
        addTask: addAnomalyTrainTask,
        updateTask: updateAnomalyTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      },
      [DatasetType.CLASSIFICATION]: {
        addTask: addClassificationTrainTask,
        updateTask: updateClassificationTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      },
      [DatasetType.TIMESERIES_PREDICT]: {
        addTask: addTimeSeriesTrainTask,
        updateTask: updateTimeSeriesTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      },
      [DatasetType.LOG_CLUSTERING]: {
        addTask: addLogClusteringTrainTask,
        updateTask: updateLogClusteringTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      },
      [DatasetType.IMAGE_CLASSIFICATION]: {
        addTask: addImageClassificationTrainTask,
        updateTask: updateImageClassificationTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      },
      [DatasetType.OBJECT_DETECTION]: {
        addTask: addObjectDetectionTrainTask,
        updateTask: updateObjectDetectionTrainTask,
        getDatasetReleases,
        getDatasetReleaseByID
      }
    };

    // 返回当前类型的 API 方法，默认使用异常检测
    return apiMethodsMap[activeType] || apiMethodsMap[DatasetType.ANOMALY_DETECTION];
  }, [
    activeType,
    addAnomalyTrainTask,
    updateAnomalyTrainTask,
    addClassificationTrainTask,
    updateClassificationTrainTask,
    addTimeSeriesTrainTask,
    updateTimeSeriesTrainTask,
    addLogClusteringTrainTask,
    updateLogClusteringTrainTask,
    addImageClassificationTrainTask,
    updateImageClassificationTrainTask,
    addObjectDetectionTrainTask,
    updateObjectDetectionTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  ]);

  // 确定当前的 datasetType
  const datasetType = useMemo(() => {
    const validTypes = Object.values(DatasetType) as string[];
    return validTypes.includes(activeType) 
      ? activeType as DatasetType 
      : DatasetType.ANOMALY_DETECTION;
  }, [activeType]);

  // 只调用一次 useGenericDatasetForm，使用动态的 datasetType 和 apiMethods
  return useGenericDatasetForm({
    datasetType,
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods
  });
};

export { useTaskForm };
