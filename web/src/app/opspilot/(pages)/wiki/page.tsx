'use client';

import React from 'react';
import EntityList from '@/app/opspilot/components/entity-list';
import WikiCard from '@/app/opspilot/components/wiki/WikiCard';
import WikiModifyModal from '@/app/opspilot/components/wiki/WikiModifyModal';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';
import { useTranslation } from '@/utils/i18n';

const WikiListPage: React.FC = () => {
  const { t } = useTranslation();
  return (
    <EntityList<WikiKnowledgeBase>
      endpoint="/opspilot/wiki_mgmt/knowledge_base/"
      CardComponent={WikiCard}
      ModifyModalComponent={WikiModifyModal}
      itemTypeSingle="wiki"
      pageTitle={t('wiki.pageTitle')}
      pageDescription={t('wiki.pageDescription')}
    />
  );
};

export default WikiListPage;
