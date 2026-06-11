'use client';

import { useTranslation } from '@/utils/i18n';

export default function FeatureLibraryPage() {
  const { t } = useTranslation();
  return <div>{t('OidLibrary.scanFeatureTitle')}</div>;
}
