'use client';

import React from 'react';
import { Empty } from 'antd';

export interface CompactEmptyStateProps {
  description: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

const CompactEmptyState: React.FC<CompactEmptyStateProps> = ({
  description,
  className = '',
  children,
}) => {
  return (
    <div className={`py-1 ${className}`.trim()}>
      <Empty
        className="!my-0"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        styles={{
          image: {
            height: 28,
            marginBottom: 2,
            filter: 'grayscale(1)',
            opacity: 0.78,
          },
        }}
        description={
          <span className="text-xs leading-4 text-[var(--color-text-3)]">
            {description}
          </span>
        }
      >
        {children}
      </Empty>
    </div>
  );
};

export default CompactEmptyState;
