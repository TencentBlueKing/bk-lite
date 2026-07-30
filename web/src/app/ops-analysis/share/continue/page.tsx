'use client';

import { useEffect, useState } from 'react';
import { Button, Spin } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useDashboardShareApi } from '@/app/ops-analysis/api/dashboardShare';
import { useTranslation } from '@/utils/i18n';

export default function DashboardShareContinuePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const { exchangeShare } = useDashboardShareApi();
  const [invalid, setInvalid] = useState(false);
  const state = searchParams.get('state');

  useEffect(() => {
    if (!state) {
      setInvalid(true);
      return;
    }
    let active = true;
    exchangeShare({ state })
      .then((result) => {
        if (active) {
          router.replace(`/ops-analysis/share/session/${result.session_id}`);
        }
      })
      .catch(() => {
        if (active) setInvalid(true);
      });
    return () => {
      active = false;
    };
  }, [exchangeShare, router, state]);

  if (invalid) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg-1)] p-8">
        <div className="w-full max-w-[400px] text-center">
          <h2 className="mb-6 text-base font-medium text-[var(--color-text-1)]">
            {t('dashboard.shareInvalid')}
          </h2>
          <Button type="primary" onClick={() => router.push('/')}>
            {t('common.backToHome')}
          </Button>
        </div>
      </div>
    );
  }
  return <Spin fullscreen tip={t('dashboard.shareOpening')} />;
}
