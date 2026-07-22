'use client';

import React, { useState } from 'react';
// import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import FullCollection from './full/page';
import ProfessionalCollection from './profess/page';
import Introduction from '@/components/introduction';

const CollectionPage: React.FC = () => {
  const [activeTab] = useState('professional');
  const { t } = useTranslation();
  //   const handleTabChange = (key: string) => setActiveTab(key);

  //   const tabItems = [
  //     { key: 'full', label: t('Collection.fullTitle') },
  //     { key: 'professional', label: t('Collection.professionalTitle') },
  //   ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} /> */}
      <div className="shrink-0">
        <Introduction
          title={
            activeTab === 'professional'
              ? t('Collection.professionalTitle')
              : t('Collection.fullTitle')
          }
          message={
            activeTab === 'professional'
              ? t('Collection.professionalMessage')
              : t('Collection.fullMessage')
          }
        />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === 'professional' ? (
          <ProfessionalCollection />
        ) : (
          <FullCollection />
        )}
      </div>
    </div>
  );
};

export default CollectionPage;
