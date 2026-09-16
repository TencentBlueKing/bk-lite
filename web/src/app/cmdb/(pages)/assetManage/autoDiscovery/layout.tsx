'use client';

import React from 'react';
import WithSideMenuLayout from '@/components/sub-layout';

const AutoDiscoveryLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <div
      className="h-full min-h-0 min-w-0 w-full"
      style={{ ['--custom-height' as string]: '100%' }}
    >
      <WithSideMenuLayout showBackButton={false}>{children}</WithSideMenuLayout>
    </div>
  );
};

export default AutoDiscoveryLayout;
