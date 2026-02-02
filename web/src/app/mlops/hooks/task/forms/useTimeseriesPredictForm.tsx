import { RefObject } from 'react';
import type { FormInstance } from 'antd';
import type { Option } from '@/types';
import { TIMESERIES_ALGORITHM_CONFIGS, TIMESERIES_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import { DatasetType } from '@/app/mlops/types';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseTimeseriesPredictFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

export const useTimeseriesPredictForm = ({
  datasetOptions,
  // activeTag,
  onSuccess,
  formRef
}: UseTimeseriesPredictFormProps) => {
  const {
    addTimeSeriesTrainTask,
    updateTimeSeriesTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: DatasetType.TIMESERIES_PREDICT,
    algorithmConfigs: TIMESERIES_ALGORITHM_CONFIGS,
    algorithmScenarios: TIMESERIES_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'GradientBoosting', label: 'GradientBoosting' },
      { value: 'RandomForest', label: 'RandomForest' },
      { value: 'Prophet', label: 'Prophet' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addTimeSeriesTrainTask,
      updateTask: updateTimeSeriesTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
