import { RefObject } from 'react';
import { FormInstance } from 'antd';
import type { Option } from '@/types';
import { LOG_CLUSTERING_ALGORITHM_CONFIGS, LOG_CLUSTERING_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseLogClusteringFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useLogClusteringForm = ({ datasetOptions, onSuccess, formRef }: UseLogClusteringFormProps) => {
  const {
    addLogClusteringTrainTask,
    updateLogClusteringTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: 'log_clustering',
    algorithmConfigs: LOG_CLUSTERING_ALGORITHM_CONFIGS,
    algorithmScenarios: LOG_CLUSTERING_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'Spell', label: 'Spell' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addLogClusteringTrainTask,
      updateTask: updateLogClusteringTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
