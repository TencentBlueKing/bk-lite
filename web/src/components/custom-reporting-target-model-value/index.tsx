import type { ReactNode } from 'react';
import type { CustomReportingTaskConfig } from '@/components/custom-reporting-shared/types';

export interface CustomReportingTargetModelValueProps {
  config?: CustomReportingTaskConfig | null;
  fallback?: ReactNode;
}

const CustomReportingTargetModelValue = ({
  config,
  fallback = '--',
}: CustomReportingTargetModelValueProps) => {
  const value =
    config?.mode === 'quick'
      ? config?.quick_model?.model_name || config?.quick_model?.model_id
      : config?.model_id;

  return <>{value || fallback}</>;
};

export default CustomReportingTargetModelValue;
