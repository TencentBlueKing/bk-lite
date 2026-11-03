'use client';

import { Skeleton } from 'antd';
import { usePathname, useSearchParams } from 'next/navigation';
import { Suspense, type ReactNode } from 'react';

import { ExecutionListPage } from '../components/execution-list-page';

const EXECUTION_PATH = /^\/workflow\/executions\/([^/]+)\/?$/;

function executionIdFromPath(pathname: string) {
  const match = EXECUTION_PATH.exec(pathname);
  if (!match) return undefined;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function ExecutionListRoute() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <ExecutionListPage
      initialExecutionId={executionIdFromPath(pathname)}
      initialNodeReference={searchParams.get('node') || undefined}
      initialInstanceId={searchParams.get('instance_id') || undefined}
    />
  );
}

export default function ExecutionsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-0 min-w-0 w-full flex-1 flex-col">
      <Suspense fallback={<div className="flex h-full min-h-0 flex-1 items-center justify-center p-6"><Skeleton active paragraph={{ rows: 8 }} title={false} /></div>}>
        <ExecutionListRoute />
      </Suspense>
      {children}
    </div>
  );
}
