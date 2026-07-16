'use client';

import React from 'react';
import CompactEmptyState from '@/components/compact-empty-state';

export interface ToolEditorEmptyStateProps {
  description: React.ReactNode;
  fullHeight?: boolean;
}

const ToolEditorEmptyState: React.FC<ToolEditorEmptyStateProps> = ({
  description,
  fullHeight = false,
}) => {
  return (
    <div
      className={
        fullHeight
          ? 'flex h-full items-center justify-center'
          : 'flex items-center justify-center py-6'
      }
    >
      <CompactEmptyState description={description} className="py-8" />
    </div>
  );
};

export default ToolEditorEmptyState;
