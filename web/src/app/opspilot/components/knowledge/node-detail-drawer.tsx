'use client';

import React from 'react';
import { Drawer, Descriptions, Empty, Tag } from 'antd';
import type { KnowledgeGraphNodeLike } from './node-detail-drawer-types';

export interface KnowledgeNodeDetailDrawerProps {
  visible: boolean;
  onClose: () => void;
  node?: KnowledgeGraphNodeLike | null;
}

const KnowledgeNodeDetailDrawer: React.FC<KnowledgeNodeDetailDrawerProps> = ({
  visible,
  onClose,
  node,
}) => {
  return (
    <Drawer
      open={visible}
      onClose={onClose}
      title="Knowledge node detail"
      width={520}
      destroyOnClose
    >
      {node ? (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="UUID">{node.uuid}</Descriptions.Item>
          <Descriptions.Item label="Name">{node.name ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Summary">{node.summary ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Fact">{node.fact ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Labels">
            {(node.labels ?? []).map((label) => (
              <Tag key={label}>{label}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>
      ) : (
        <Empty description="No node selected" />
      )}
    </Drawer>
  );
};

export default KnowledgeNodeDetailDrawer;
