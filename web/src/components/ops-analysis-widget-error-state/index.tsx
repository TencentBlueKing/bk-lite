import React from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';

export interface OpsAnalysisWidgetErrorStateProps {
  message: string;
}

const OpsAnalysisWidgetErrorState: React.FC<OpsAnalysisWidgetErrorStateProps> = ({
  message,
}) => {
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 text-center">
      <ExclamationCircleOutlined
        style={{ color: '#faad14', fontSize: '24px', marginBottom: '12px' }}
      />
      <span style={{ fontSize: '14px', color: '#666' }}>{message}</span>
    </div>
  );
};

export default OpsAnalysisWidgetErrorState;
