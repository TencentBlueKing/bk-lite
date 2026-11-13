'use client';

import { useEffect, useState } from 'react';
import { Spin } from 'antd';
import { useParams, useRouter } from 'next/navigation';
import { activateScreenDisplay } from '@/app/ops-analysis/api/screenDisplay';
import { useTranslation } from '@/utils/i18n';

const reasonMessage = (reason: string, t: (id: string) => string) => {
  if (reason === 'paused') return t('opsAnalysis.screen.displayPausedPage');
  if (reason === 'expired') return t('opsAnalysis.screen.displayExpiredPage');
  return t('opsAnalysis.screen.displayInvalid');
};

export default function ScreenDisplayActivatePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { t } = useTranslation();
  const [reason, setReason] = useState<string | null>(null);

  useEffect(() => {
    const token = params.token;
    if (!token) {
      setReason('invalid');
      return;
    }
    let cancelled = false;
    activateScreenDisplay(decodeURIComponent(token))
      .then(() => {
        if (!cancelled) router.replace('/ops-analysis/display/view');
      })
      .catch((error: { reason?: string }) => {
        if (!cancelled) setReason(error.reason || 'invalid');
      });
    return () => {
      cancelled = true;
    };
  }, [params.token, router]);

  if (reason) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-bg-1)] p-8">
        <p className="m-0 max-w-[420px] text-center text-base text-[var(--color-text-1)]">
          {reasonMessage(reason, t)}
        </p>
      </div>
    );
  }

  return <Spin fullscreen tip={t('opsAnalysis.screen.displayLoading')} />;
}
