'use client';

import React from 'react';
import KnowledgeQADetailDrawer, {
  type KnowledgeQADetailDrawerProps,
} from '@/app/opspilot/components/knowledge/qa-detail-drawer';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

type RuntimeProps = Omit<KnowledgeQADetailDrawerProps, 'getChunkDetailAction'>;

const KnowledgeQADetailDrawerRuntime: React.FC<RuntimeProps> = (props) => {
  const { getChunkDetail } = useKnowledgeApi();

  return (
    <KnowledgeQADetailDrawer
      {...props}
      getChunkDetailAction={getChunkDetail}
    />
  );
};

export default KnowledgeQADetailDrawerRuntime;
