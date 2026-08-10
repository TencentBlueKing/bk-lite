'use client';

import { useTranslation } from '@/utils/i18n';
import Introduction from '@/components/introduction';

export default function FeatureLibraryPage() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 overflow-x-auto">
        <Introduction
          title={t('OidLibrary.scanFeatureTitle')}
          message={t('OidLibrary.scanFeatureMessage')}
        />
      </div>
    </div>
  );
}
