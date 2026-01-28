import { RefObject } from 'react';
import { FormInstance } from 'antd';
import { DatasetType } from '@/app/mlops/types';
import type { Option } from '@/types';
import { ANOMALY_ALGORITHM_CONFIGS, ANOMALY_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseAnomalyFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useAnomalyForm = ({ datasetOptions, onSuccess, formRef }: UseAnomalyFormProps) => {
  const {
    addAnomalyTrainTask,
    updateAnomalyTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: DatasetType.ANOMALY_DETECTION,
    algorithmConfigs: ANOMALY_ALGORITHM_CONFIGS,
    algorithmScenarios: ANOMALY_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'ECOD', label: 'ECOD' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addAnomalyTrainTask,
      updateTask: updateAnomalyTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
