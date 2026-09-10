'use client';

import CommonProvider from '@/app/node-manager/context/common';
import '@/app/node-manager/styles/index.css';

export default function RootMonitor({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <CommonProvider>{children}</CommonProvider>;
}
