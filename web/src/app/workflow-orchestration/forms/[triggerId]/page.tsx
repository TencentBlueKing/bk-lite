'use client';

import { Empty } from 'antd';
import { useParams } from 'next/navigation';

import { useTranslation } from '@/utils/i18n';
import { WorkflowFormPage } from '../../components/workflow-form-page';

export default function WorkflowProductionFormRoute() {
  const { t } = useTranslation();
  const params = useParams<{ triggerId: string }>();
  if (!params.triggerId) return <Empty className="py-24" description={t('workflowOrchestration.form.invalidProductionUrl', '无效的生产表单地址')} />;
  return <WorkflowFormPage mode="production" triggerId={params.triggerId} />;
}
