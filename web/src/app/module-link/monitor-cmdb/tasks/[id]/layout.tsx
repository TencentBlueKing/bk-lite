'use client';

import { Suspense } from 'react';
import { Spin } from 'antd';

export default function MonitorCmdbTaskLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full w-full items-center justify-center">
          <Spin size="large" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
