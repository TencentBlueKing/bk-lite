'use client';

import { useTranslation } from '@/utils/i18n';
import TopSection from '@/components/top-section';

export default function FeatureLibraryPage() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 overflow-x-auto">
        <TopSection
          title={t('OidLibrary.scanFeatureTitle')}
          content={t('OidLibrary.scanFeatureMessage')}
        />
      </div>
    </div>
  );
}
