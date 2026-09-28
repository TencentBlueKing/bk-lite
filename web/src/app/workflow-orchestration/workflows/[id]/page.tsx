'use client';

import { Empty } from 'antd';
import { useParams, useSearchParams } from 'next/navigation';

import { useTranslation } from '@/utils/i18n';
import { WorkflowOrchestrationConsole } from '../../components/workflow-orchestration-console';

export default function WorkflowEditorPage() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const isNew = params.id === 'new';
  const workflowId = isNew ? null : Number(params.id);
  const mode = searchParams.get('mode') === 'view' ? 'view' : 'edit';

  if (!isNew && (!Number.isInteger(workflowId) || !workflowId || workflowId <= 0)) {
    return <Empty className="py-24" description={t('workflowOrchestration.form.invalidWorkflowId', '无效的流程 ID')} />;
  }

  return <WorkflowOrchestrationConsole workflowId={workflowId} initialName={searchParams.get('name') || t('workflowOrchestration.editor.newWorkflow', '新建流程')} mode={mode} />;
}
