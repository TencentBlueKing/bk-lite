'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { MobileAppLoading } from '@/components/mobile-feedback';
import { useMobileAvailability } from '@/platform/availability/context';
import { useTranslation } from '@/utils/i18n';

export default function RootRedirect() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status, resolveSafeRoot } = useMobileAvailability();

  useEffect(() => {
    if (status === 'ready' || status === 'error') {
      router.replace(resolveSafeRoot());
    }
  }, [resolveSafeRoot, router, status]);

  return <MobileAppLoading label={t('common.loading')} />;
}
