'use client';

import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { PatchOriginType, PatchSourceDetail } from '@/app/patch-manager/types';
import { useTranslation } from '@/utils/i18n';

interface PatchSourceDisplayProps {
  sourceType?: PatchOriginType | null;
  sourceDetails?: PatchSourceDetail[];
}

export default function PatchSourceDisplay({
  sourceType,
  sourceDetails = [],
}: PatchSourceDisplayProps) {
  const { t } = useTranslation();

  if (sourceType === 'manual') {
    return (
      <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>
        {t('patchManager.libraryPage.manualEntry')}
      </span>
    );
  }

  const text = sourceDetails.length
    ? sourceDetails
      .map((item) => item.deleted
        ? `${t('patchManager.libraryPage.sourceDeleted')}${item.url ? `:${item.url}` : ''}`
        : item.url || '—')
      .join(',')
    : t('patchManager.libraryPage.sourceDeleted');

  return (
    <EllipsisWithTooltip
      text={text}
      className="w-full overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-3,#8c8c8c)]"
    />
  );
}
