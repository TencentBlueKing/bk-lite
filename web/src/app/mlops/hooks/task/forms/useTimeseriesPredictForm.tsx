import { RefObject } from 'react';
import type { FormInstance } from 'antd';
import type { Option } from '@/types';
import { DatasetType } from '@/app/mlops/types';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseTimeseriesPredictFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useTimeseriesPredictForm = ({
  datasetOptions,
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
