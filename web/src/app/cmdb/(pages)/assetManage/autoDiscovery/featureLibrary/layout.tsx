'use client';

import React from 'react';
import { Tabs } from 'antd';
import { usePathname, useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';

const SOID_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';
const PORT_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/port';

export default function FeatureLibraryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();

  const isFeatureLibrary =
    pathname?.includes('/featureLibrary/soid') ||
    pathname?.includes('/featureLibrary/port');

  if (!isFeatureLibrary) {
    return <>{children}</>;
  }

  const activeKey = pathname?.includes('/featureLibrary/port')
    ? PORT_PATH
    : SOID_PATH;

  const handleTabChange = (key: string) => {
    router.push(key);
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 mb-3 border-b border-[var(--color-border-2)] bg-[var(--color-bg-1)]">
        <Tabs
          activeKey={activeKey}
          onChange={handleTabChange}
          className="!mb-0"
          items={[
            {
              key: SOID_PATH,
              label: t('OidLibrary.soidTab'),
            },
            {
              key: PORT_PATH,
              label: t('OidLibrary.portTab'),
            },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
