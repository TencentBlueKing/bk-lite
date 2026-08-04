import React from 'react';
import WidgetState from '@/app/ops-analysis/components/widget-state';

interface WidgetErrorStateProps {
  message: string;
}

const WidgetErrorState: React.FC<WidgetErrorStateProps> = ({ message }) => {
  return <WidgetState kind="error" description={message} />;
};

export default WidgetErrorState;
