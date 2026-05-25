import React from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';

interface WidgetErrorStateProps {
  message: string;
}

const WidgetErrorState: React.FC<WidgetErrorStateProps> = ({ message }) => {
  return (
    <div className="h-full flex flex-col items-center justify-center px-4 text-center">
      <ExclamationCircleOutlined
        style={{ color: '#faad14', fontSize: '24px', marginBottom: '12px' }}
      />
      <span style={{ fontSize: '14px', color: '#666' }}>{message}</span>
    </div>
  );
};

export default WidgetErrorState;
