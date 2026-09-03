'use client';

import { useParams } from 'next/navigation';
import ApplicationObservability from '@/app/apm/components/application-observability';
import { useTranslation } from '@/utils/i18n';

export default function ApmApplicationDetailPage() {
  const params = useParams<{ applicationId: string }>();
  const { t } = useTranslation();
  return (
    <ApplicationObservability
      applicationId={params.applicationId}
      showAddIngest
      parentHref="/apm/integration/applications"
      parentLabel={t('apm.applications.title', '应用管理')}
      parentAriaLabel={t('apm.applications.backToManagement', '返回应用管理')}
    />
  );
}
