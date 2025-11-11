'use client';

import React from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import { OpsAnalysisProvider } from '../../context/common';

const SettingsLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <OpsAnalysisProvider>
      <WithSideMenuLayout
        layoutType="segmented"
        pagePathName="/ops-analysis/settings/"
      >
        {children}
      </WithSideMenuLayout>
    </OpsAnalysisProvider>
  );
};

export default SettingsLayout;
