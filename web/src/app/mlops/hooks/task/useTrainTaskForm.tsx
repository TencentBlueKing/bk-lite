import { FormInstance } from 'antd';
import { useAnomalyForm, useClassificationForm, useTimeseriesPredictForm, useLogClusteringForm, useImageClassificationForm, useObjectDetectionForm } from './forms';
import type { Option } from '@/types';
import { RefObject } from 'react';
import { DatasetType } from '@/app/mlops/types';

interface UseTaskFormProps {
  datasetOptions: Option[];
  activeTag: string[];
  onSuccess: () => void;
  formRef: RefObject<FormInstance>
}

const useTaskForm = ({ datasetOptions, activeTag, onSuccess, formRef }: UseTaskFormProps) => {
  const [activeType] = activeTag;
  const anomalyFormResult = useAnomalyForm({ datasetOptions, activeTag, onSuccess, formRef });
  const classificationFormResult = useClassificationForm({ datasetOptions, activeTag, onSuccess, formRef });
  const timeseriesPredictFormResult = useTimeseriesPredictForm({ datasetOptions, activeTag, onSuccess, formRef });
  const logClusteringFormResult = useLogClusteringForm({ datasetOptions, activeTag, onSuccess, formRef });
  const imageClassificationFormResult = useImageClassificationForm({ datasetOptions, activeTag, onSuccess, formRef });
  const objectDetectionFormResult = useObjectDetectionForm({ datasetOptions, activeTag, onSuccess, formRef });

  switch (activeType) {
    case DatasetType.ANOMALY_DETECTION:
      return anomalyFormResult;
    case DatasetType.TIMESERIES_PREDICT:
      return timeseriesPredictFormResult;
    case DatasetType.LOG_CLUSTERING:
      return logClusteringFormResult;
    case DatasetType.CLASSIFICATION:
      return classificationFormResult;
    case DatasetType.IMAGE_CLASSIFICATION:
      return imageClassificationFormResult;
    case DatasetType.OBJECT_DETECTION:
      return objectDetectionFormResult;
    default:
      return anomalyFormResult;
  }
};

export {
  useTaskForm,
  useAnomalyForm,
  useLogClusteringForm,
  useImageClassificationForm,
  useObjectDetectionForm
};

