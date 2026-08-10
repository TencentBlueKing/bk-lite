'use client';

import React from 'react';
import { Drawer, Descriptions } from 'antd';

export interface KnowledgeEdgeLike {
  fact?: string;
  label?: string;
  source_name?: string;
  target_name?: string;
}

export interface KnowledgeEdgeDetailDrawerProps {
  visible: boolean;
  onClose: () => void;
  edge?: KnowledgeEdgeLike | null;
}

const KnowledgeEdgeDetailDrawer: React.FC<KnowledgeEdgeDetailDrawerProps> = ({
  visible,
  onClose,
  edge,
}) => {
  return (
    <Drawer
      open={visible}
      onClose={onClose}
      title="Knowledge edge detail"
      width={520}
      destroyOnClose
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="Label">{edge?.label ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="Source">{edge?.source_name ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="Target">{edge?.target_name ?? '—'}</Descriptions.Item>
        <Descriptions.Item label="Fact">{edge?.fact ?? '—'}</Descriptions.Item>
      </Descriptions>
    </Drawer>
  );
};

export default KnowledgeEdgeDetailDrawer;
