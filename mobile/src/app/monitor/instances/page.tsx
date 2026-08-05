'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { MobileSkeleton } from '@/components/mobile-feedback';
import { useTranslation } from '@/utils/i18n';

function MonitorInstancesRedirect() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const next = new URLSearchParams();
    const objectId = params.get('objectId');
    const objectName = params.get('objectName');
    if (objectId) next.set('objectId', objectId);
    if (objectName) next.set('objectName', objectName);
    const query = next.toString();
    router.replace(query ? `/monitor?${query}` : '/monitor');
  }, [params, router]);

  return null;
}

export default function MonitorInstancesPage() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="list" rows={5} />}>
      <MonitorInstancesRedirect />
    </Suspense>
  );
}
