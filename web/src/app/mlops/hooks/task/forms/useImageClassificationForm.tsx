import { RefObject } from 'react';
import { FormInstance } from 'antd';
import type { Option } from '@/types';
import { IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS, IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseImageClassificationFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useImageClassificationForm = ({ datasetOptions, onSuccess, formRef }: UseImageClassificationFormProps) => {
  const {
    addImageClassificationTrainTask,
    updateImageClassificationTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: 'image_classification',
    algorithmConfigs: IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS,
    algorithmScenarios: IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'YOLOClassification', label: 'YOLOClassification' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addImageClassificationTrainTask,
      updateTask: updateImageClassificationTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
