'use client';

import CommonProvider from '@/app/node-manager/context/common';
import '@/app/node-manager/styles/index.css';
import useApiClient from '@/utils/request';

export default function RootMonitor({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { isLoading } = useApiClient();
  return <CommonProvider>{isLoading ? null : children}</CommonProvider>;
}
