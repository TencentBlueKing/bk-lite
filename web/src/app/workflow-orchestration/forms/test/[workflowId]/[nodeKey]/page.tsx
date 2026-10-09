'use client';

import { Empty } from 'antd';
import { useParams } from 'next/navigation';

import { useTranslation } from '@/utils/i18n';
import { WorkflowFormPage } from '../../../../components/workflow-form-page';

export default function WorkflowTestFormRoute() {
  const { t } = useTranslation();
  const params = useParams<{ workflowId: string; nodeKey: string }>();
  const workflowId = Number(params.workflowId);
  if (!Number.isInteger(workflowId) || workflowId <= 0 || !params.nodeKey) return <Empty className="py-24" description={t('workflowOrchestration.form.invalidTestUrl', '无效的测试表单地址')} />;
  return <WorkflowFormPage mode="test" workflowId={workflowId} nodeKey={params.nodeKey} />;
}
