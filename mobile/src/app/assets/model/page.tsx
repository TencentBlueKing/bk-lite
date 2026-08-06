'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { MobileSkeleton } from '@/components/mobile-feedback';
import { useTranslation } from '@/utils/i18n';

function AssetModelRedirect() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const next = new URLSearchParams();
    const classificationId = params.get('classificationId');
    const modelId = params.get('modelId');
    const modelName = params.get('modelName');
    if (classificationId) next.set('classificationId', classificationId);
    if (modelId) next.set('modelId', modelId);
    if (modelName) next.set('modelName', modelName);
    const query = next.toString();
    router.replace(query ? `/assets?${query}` : '/assets');
  }, [params, router]);

  return null;
}

export default function ModelInstancesPage() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="list" rows={5} />}>
      <AssetModelRedirect />
    </Suspense>
  );
}
