'use client';

import React from 'react';
import { ToolOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';

export interface MonitorIntegrationConfigStateProps {
  description: string;
  variant: 'reportedOnly' | 'missingConfig' | 'collectNotSupported';
  className?: string;
}

const MonitorIntegrationConfigState: React.FC<MonitorIntegrationConfigStateProps> = ({
  description,
  variant,
  className = '',
}) => {
  if (variant === 'reportedOnly') {
    return (
      <div className={`flex flex-col items-center justify-center px-4 py-8 ${className}`.trim()}>
        <span className="mb-3 text-4xl text-[var(--color-text-3)]">
          <ToolOutlined />
        </span>
        <span className="text-[12px] text-[var(--color-text-3)]">
          {description}
        </span>
      </div>
    );
  }

  return (
    <CompactEmptyState
      description={description}
      className={className || 'py-8'}
    />
  );
};

export default MonitorIntegrationConfigState;
