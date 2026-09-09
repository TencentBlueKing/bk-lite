'use client';

import React, { useState } from 'react';
import { Tabs } from 'antd';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import CredentialListTab from '@/app/system-manager/components/credential/CredentialListTab';
import TypeCatalogTab from '@/app/system-manager/components/credential/TypeCatalogTab';

const CredentialPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState('list');

  return (
    <PageLayout
      height="calc(100vh - 200px)"
      topSection={
        <TopSection
          title={t('system.credential.title')}
          content={t('system.credential.pageDesc')}
        />
      }
      rightSection={
        <div className="flex h-full flex-col">
          <Tabs
            activeKey={activeKey}
            onChange={setActiveKey}
            items={[
              {
                key: 'list',
                label: t('system.credential.listTab'),
                children: (
                  <div className="h-[calc(100vh-290px)]">
                    <CredentialListTab
                      active={activeKey === 'list'}
                      onGoTypes={() => setActiveKey('types')}
                    />
                  </div>
                ),
              },
              {
                key: 'types',
                label: t('system.credential.typeTab'),
                children: (
                  <div className="h-[calc(100vh-290px)]">
                    <TypeCatalogTab />
                  </div>
                ),
              },
            ]}
          />
        </div>
      }
    />
  );
};

export default CredentialPage;
