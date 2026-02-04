import { RefObject } from 'react';
import { FormInstance } from 'antd';
import type { Option } from '@/types';
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
