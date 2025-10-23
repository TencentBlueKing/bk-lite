import { FormInstance } from 'antd';
import { useAnomalyForm, useRasaForm } from './forms';
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
  const rasaFormResult = useRasaForm({ datasetOptions, activeTag, onSuccess, formRef });

  switch (activeType) {
    case 'anomaly':
      return anomalyFormResult;
    case 'rasa':
      return rasaFormResult;
    default:
      return anomalyFormResult;
  }
};

export {
  useTaskForm,
  useAnomalyForm
};
