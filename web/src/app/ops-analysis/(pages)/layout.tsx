'use client';

import React from 'react';
import CommonProvider from '@/app/cmdb/context/common';

export default function OpsAnalysisRootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <CommonProvider>{children}</CommonProvider>;
}
