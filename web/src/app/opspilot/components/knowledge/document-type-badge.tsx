'use client';

import React from 'react';
import { Tag } from 'antd';

export type KnowledgeDocumentType = 'file' | 'web_page' | 'manual' | string;

export interface KnowledgeDocumentTypeBadgeProps {
  type: KnowledgeDocumentType;
  label: string;
  active?: boolean;
}

const typeColorMap: Record<string, string> = {
  file: 'blue',
  web_page: 'cyan',
  manual: 'purple',
};

const KnowledgeDocumentTypeBadge: React.FC<KnowledgeDocumentTypeBadgeProps> = ({
  type,
  label,
  active = true,
}) => {
  return (
    <Tag color={typeColorMap[type] ?? 'default'} bordered={false} className={active ? '' : 'opacity-50'}>
      {label}
    </Tag>
  );
};

export default KnowledgeDocumentTypeBadge;
