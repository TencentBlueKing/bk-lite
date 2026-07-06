'use client';

import React from 'react';
import EntityList from '@/app/opspilot/components/entity-list';
import WikiCard from '@/app/opspilot/components/wiki/WikiCard';
import WikiModifyModal from '@/app/opspilot/components/wiki/WikiModifyModal';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

const WikiListPage: React.FC = () => {
  return (
    <EntityList<WikiKnowledgeBase>
      endpoint="/opspilot/wiki_mgmt/knowledge_base/"
      CardComponent={WikiCard}
      ModifyModalComponent={WikiModifyModal}
      itemTypeSingle="wiki"
    />
  );
};

export default WikiListPage;
