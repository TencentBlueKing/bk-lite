'use client';

import React from 'react';
import WithSideMenuLayout from '@/components/sub-layout';

const AutoDiscoveryLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <div
      style={{
        height: 'calc(100vh - 155px)',
        ['--custom-height' as string]: 'calc(100vh - 155px)',
      }}
    >
      <WithSideMenuLayout showBackButton={false} pagePathName="/cmdb/assetManage/autoDiscovery/collection">{children}</WithSideMenuLayout>
    </div>
  );
};

export default AutoDiscoveryLayout;
