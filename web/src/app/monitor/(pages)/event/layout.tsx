'use client';

import React from 'react';
import WithSideMenuLayout from '@/components/sub-layout';

const EventLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <WithSideMenuLayout layoutType="segmented">{children}</WithSideMenuLayout>
  );
};

export default EventLayout;
