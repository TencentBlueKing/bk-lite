'use client';

import { Empty } from 'antd';
import { useParams, useSearchParams } from 'next/navigation';

import { useTranslation } from '@/utils/i18n';
import { WorkflowOrchestrationConsole } from '../../components/workflow-orchestration-console';

export default function MarketWorkflowViewPage() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const workflowId = Number(params.id);

  if (!Number.isInteger(workflowId) || workflowId <= 0) {
    return <Empty className="py-24" description={t('workflowOrchestration.form.invalidWorkflowId', '无效的流程 ID')} />;
  }

  return (
    <WorkflowOrchestrationConsole
      workflowId={workflowId}
      initialName={searchParams.get('name') || ''}
      mode="view"
      listHref="/workflow-orchestration/market"
      permissionArea="market"
    />
  );
}
