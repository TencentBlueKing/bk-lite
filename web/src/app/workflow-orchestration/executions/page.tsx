'use client';

import { Spin } from 'antd';
import { Suspense } from 'react';

import { ExecutionListPage } from '../components/execution-list-page';

export default function ExecutionsPage() {
  return (
    <Suspense fallback={<div className="flex h-full min-h-0 flex-1 items-center justify-center"><Spin /></div>}>
      <ExecutionListPage />
    </Suspense>
  );
}
