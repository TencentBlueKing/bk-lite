import { RefObject } from 'react';
import { FormInstance } from 'antd';
import type { Option } from '@/types';
import { OBJECT_DETECTION_ALGORITHM_CONFIGS, OBJECT_DETECTION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';
import { DatasetType } from '@/app/mlops/types';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { useGenericDatasetForm } from './useGenericDatasetForm';

interface UseObjectDetectionFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useObjectDetectionForm = ({ datasetOptions, onSuccess, formRef }: UseObjectDetectionFormProps) => {
  const {
    addObjectDetectionTrainTask,
    updateObjectDetectionTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  return useGenericDatasetForm({
    datasetType: DatasetType.OBJECT_DETECTION,
    algorithmConfigs: OBJECT_DETECTION_ALGORITHM_CONFIGS,
    algorithmScenarios: OBJECT_DETECTION_ALGORITHM_SCENARIOS,
    algorithmOptions: [
      { value: 'YOLODetection', label: 'YOLODetection' },
    ],
    datasetOptions,
    formRef,
    onSuccess,
    apiMethods: {
      addTask: addObjectDetectionTrainTask,
      updateTask: updateObjectDetectionTrainTask,
      getDatasetReleases,
      getDatasetReleaseByID
    }
  });
};
