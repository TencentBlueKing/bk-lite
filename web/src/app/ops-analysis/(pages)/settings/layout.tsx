'use client';

import React from 'react';
import { useSearchParams } from 'next/navigation';
import WithSideMenuLayout from '@/components/sub-layout';
import { isScreenModeEnabled } from '@/console-layout';
import { OpsAnalysisProvider } from '../../context/common';

const SettingsLayout = ({ children }: { children: React.ReactNode }) => {
  const searchParams = useSearchParams();
  const screenMode = isScreenModeEnabled(searchParams);

  return (
    <OpsAnalysisProvider>
      {screenMode ? (
        children
      ) : (
        <WithSideMenuLayout
          layoutType="segmented"
          pagePathName="/ops-analysis/settings/"
        >
          {children}
        </WithSideMenuLayout>
      )}
    </OpsAnalysisProvider>
  );
};

export default SettingsLayout;
