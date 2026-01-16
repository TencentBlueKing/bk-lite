import { FormInstance } from 'antd';
import { useAnomalyForm, useClassificationForm, useRasaForm, useTimeseriesPredictForm, useLogClusteringForm, useImageClassificationForm, useObjectDetectionForm } from './forms';
import type { Option } from '@/types';
import { RefObject } from 'react';

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
  const rasaFormResult = useRasaForm({ datasetOptions, activeTag, onSuccess, formRef });
  const timeseriesPredictFormResult = useTimeseriesPredictForm({ datasetOptions, activeTag, onSuccess, formRef });
  const logClusteringFormResult = useLogClusteringForm({ datasetOptions, activeTag, onSuccess, formRef });
  const imageClassificationFormResult = useImageClassificationForm({ datasetOptions, activeTag, onSuccess, formRef });
  const objectDetectionFormResult = useObjectDetectionForm({ datasetOptions, activeTag, onSuccess, formRef });

  switch (activeType) {
    case 'anomaly_detection':
      return anomalyFormResult;
    case 'rasa':
      return rasaFormResult;
    case 'timeseries_predict':
      return timeseriesPredictFormResult;
    case 'log_clustering':
      return logClusteringFormResult;
    case 'classification':
      return classificationFormResult;
    case 'image_classification':
      return imageClassificationFormResult;
    case 'object_detection':
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

