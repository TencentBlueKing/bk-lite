'use client';

import React, { useState } from 'react';
// import { Tabs } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Introduction from '@/app/cmdb/components/introduction';
import ScanFeature from './scanFeature/page';
import SOID from './soid/page';

const CollectionPage: React.FC = () => {
  const [activeTab] = useState('soid');
  const { t } = useTranslation();
  //   const handleTabChange = (key: string) => setActiveTab(key);

  //   const tabItems = [
  //     { key: 'scanFeature', label: t('OidLibrary.scanFeatureTitle') },
  //     { key: 'soid', label: t('OidLibrary.soidTitle') },
  //   ];
  return (
    <div className="flex flex-col h-full">
      {/* <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} /> */}
      <Introduction
        title={
          activeTab === 'soid'
            ? t('OidLibrary.soidTitle')
            : t('OidLibrary.scanFeatureTitle')
        }
        message={
          activeTab === 'soid'
            ? t('OidLibrary.soidMessage')
            : t('OidLibrary.scanFeatureMessage')
        }
      />
      {activeTab === 'soid' ? <SOID /> : <ScanFeature />}
    </div>
  );
};

export default CollectionPage;
