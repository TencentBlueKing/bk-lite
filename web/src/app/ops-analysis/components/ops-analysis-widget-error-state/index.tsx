import React from 'react';
import WidgetState from '@/app/ops-analysis/components/widget-state';

export interface OpsAnalysisWidgetErrorStateProps {
  message: string;
}

const OpsAnalysisWidgetErrorState: React.FC<OpsAnalysisWidgetErrorStateProps> = ({
  message,
}) => {
  return <WidgetState kind="error" description={message} />;
};

export default OpsAnalysisWidgetErrorState;
