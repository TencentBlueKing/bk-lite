'use client';

import type { CatalogStatus } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

const statusTone: Record<CatalogStatus, { className: string; dotClassName: string }> = {
  active: {
    className: 'border-[color-mix(in_srgb,var(--color-success)_24%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg))] text-[var(--color-success)]',
    dotClassName: 'bg-[var(--color-success)]',
  },
  silent: {
    className: 'border-[color-mix(in_srgb,var(--theme-color-status-warning)_28%,var(--color-border))] bg-[color-mix(in_srgb,var(--theme-color-status-warning)_10%,var(--color-bg))] text-[var(--theme-color-status-warning)]',
    dotClassName: 'bg-[var(--theme-color-status-warning)]',
  },
  archived: {
    className: 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)]',
    dotClassName: 'bg-[var(--color-text-4)]',
  },
};

export default function ApmStatusTag({ status }: { status: CatalogStatus }) {
  const { t } = useTranslation();
  const item = statusTone[status];
  const label = t(`apm.status.${status}`, status === 'active' ? '活跃' : status === 'silent' ? '静默' : '已归档');
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${item.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${item.dotClassName}`} aria-hidden="true" />
      {label}
    </span>
  );
}
