'use client';

import React from 'react';
import { Tag } from 'antd';

export type KnowledgeProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface KnowledgeProcessingStatusBadgeProps {
  status: KnowledgeProcessingStatus;
  label: string;
  className?: string;
}

const statusColorMap: Record<KnowledgeProcessingStatus, string> = {
  pending: 'default',
  processing: 'blue',
  completed: 'green',
  failed: 'red',
};

const KnowledgeProcessingStatusBadge: React.FC<KnowledgeProcessingStatusBadgeProps> = ({
  status,
  label,
  className,
}) => {
  return (
    <Tag color={statusColorMap[status] ?? 'default'} bordered={false} className={className}>
      {label}
    </Tag>
  );
};

export default KnowledgeProcessingStatusBadge;
