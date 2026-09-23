'use client';

import { Alert } from 'antd';

import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import { useTranslation } from '@/utils/i18n';

/** Temporary shell until each page is ported from core-admin. */
export default function RumPortPlaceholder({
  titleKey,
  degraded,
}: {
  titleKey: string;
  degraded?: 'control' | 'analytics' | null;
}) {
  const { t } = useTranslation();
  return (
    <>
      <h1 className="mb-3 text-base font-semibold">{t(titleKey)}</h1>
      {degraded ? <PipelineDegradedBanner reason={degraded} /> : null}
      <Alert
        type="info"
        showIcon
        message={t('rum.port.scaffoldTitle')}
        description={t('rum.port.scaffoldHint')}
      />
    </>
  );
}
