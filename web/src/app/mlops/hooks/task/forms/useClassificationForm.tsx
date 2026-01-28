import { RefObject } from 'react';
import { FormInstance } from 'antd';
import { DatasetType } from '@/app/mlops/types';
import type { Option } from '@/types';
import { CLASSIFICATION_ALGORITHM_CONFIGS, CLASSIFICATION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseClassificationFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useClassificationForm = ({ datasetOptions, onSuccess, formRef }: UseClassificationFormProps) => {
  const {
    addClassificationTrainTask,
    updateClassificationTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: DatasetType.CLASSIFICATION,
    algorithmConfigs: CLASSIFICATION_ALGORITHM_CONFIGS,
    algorithmScenarios: CLASSIFICATION_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'XGBoost', label: 'XGBoost' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addClassificationTrainTask,
      updateTask: updateClassificationTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
