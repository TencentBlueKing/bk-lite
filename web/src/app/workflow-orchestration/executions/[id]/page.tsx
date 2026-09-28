'use client';

import { Empty, Spin } from 'antd';
import { useParams, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { useTranslation } from '@/utils/i18n';
import { ExecutionListPage } from '../../components/execution-list-page';

export default function ExecutionPage() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const executionId = params.id;

  if (!executionId) {
    return <Empty className="py-24" description={t('workflowOrchestration.form.invalidExecutionId', '无效的执行 ID')} />;
  }

  return <Suspense fallback={<div className="flex h-full min-h-0 flex-1 items-center justify-center"><Spin /></div>}><ExecutionListPage initialExecutionId={executionId} initialNodeReference={searchParams.get('node') || undefined} initialInstanceId={searchParams.get('instance_id') || undefined} /></Suspense>;
}
