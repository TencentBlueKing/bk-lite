'use client';

import CommonProvider from '@/app/monitor/context/common';
import '@/app/monitor/styles/index.css';
import useApiClient from '@/utils/request';

export default function RootMonitor({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { isLoading } = useApiClient();
  return <CommonProvider>{isLoading ? null : children}</CommonProvider>;
}
