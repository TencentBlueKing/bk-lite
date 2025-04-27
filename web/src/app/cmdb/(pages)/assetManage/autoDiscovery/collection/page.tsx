'use client';

import React, { useState } from 'react';
// import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import FullCollection from './full/page';
import ProfessionalCollection from './profess/page';
import Introduction from '@/app/cmdb/components/introduction';

const CollectionPage: React.FC = () => {
  const [activeTab] = useState('professional');
  const { t } = useTranslation();
  //   const handleTabChange = (key: string) => setActiveTab(key);

  //   const tabItems = [
  //     { key: 'full', label: t('Collection.fullTitle') },
  //     { key: 'professional', label: t('Collection.professionalTitle') },
  //   ];

  return (
    <div className="flex flex-col h-full">
      {/* <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} /> */}
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
      {activeTab === 'professional' ? (
        <ProfessionalCollection />
      ) : (
        <FullCollection />
      )}
    </div>
  );
};

export default CollectionPage;
