'use client';

import React, { useState } from 'react';
import { Tabs } from 'antd';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import CredentialListTab from '@/app/system-manager/components/credential/CredentialListTab';
import TypeCatalogTab from '@/app/system-manager/components/credential/TypeCatalogTab';
import SystemManagerWorkbenchShell, {
  SystemManagerWorkbenchPanel,
} from '@/app/system-manager/components/system-manager-workbench-shell';

const CredentialPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState('list');

  return (
    <SystemManagerWorkbenchShell
      header={(
        <TopSection
          title={t('system.credential.title')}
          content={t('system.credential.pageDesc')}
        />
      )}
      right={(
        <SystemManagerWorkbenchPanel bodyClassName="flex min-h-0 flex-col p-4">
          <Tabs
            activeKey={activeKey}
            onChange={setActiveKey}
            className="flex min-h-0 flex-1 flex-col [&>.ant-tabs-content-holder]:min-h-0 [&>.ant-tabs-content-holder]:flex-1 [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full"
            items={[
              {
                key: 'list',
                label: t('system.credential.listTab'),
                children: (
                  <CredentialListTab
                    active={activeKey === 'list'}
                    onGoTypes={() => setActiveKey('types')}
                  />
                ),
              },
              {
                key: 'types',
                label: t('system.credential.typeTab'),
                children: <TypeCatalogTab />,
              },
            ]}
          />
        </SystemManagerWorkbenchPanel>
      )}
    />
  );
};

export default CredentialPage;
