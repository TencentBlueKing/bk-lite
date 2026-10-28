'use client';

import React from 'react';
import { Tabs } from 'antd';
import { usePathname } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';

const SOID_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';
const PORT_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/port';
const PROCESS_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/process';

export default function FeatureLibraryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useScreenAwareRouter();

  const isFeatureLibrary =
    pathname?.includes('/featureLibrary/soid') ||
    pathname?.includes('/featureLibrary/port') ||
    pathname?.includes('/featureLibrary/process');

  if (!isFeatureLibrary) {
    return <>{children}</>;
  }

  const activeKey = pathname?.includes('/featureLibrary/process')
    ? PROCESS_PATH
    : pathname?.includes('/featureLibrary/port')
      ? PORT_PATH
      : SOID_PATH;

  const handleTabChange = (key: string) => {
    router.push(key);
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 px-4">
        <Tabs
          activeKey={activeKey}
          onChange={handleTabChange}
          className="[&>.ant-tabs-nav]:!mb-0 [&>.ant-tabs-content-holder]:hidden"
          items={[
            {
              key: SOID_PATH,
              label: t('OidLibrary.soidTab'),
            },
            {
              key: PORT_PATH,
              label: t('OidLibrary.portTab'),
            },
            {
              key: PROCESS_PATH,
              label: t('OidLibrary.processTab'),
            },
          ]}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {children}
      </div>
    </div>
  );
}
