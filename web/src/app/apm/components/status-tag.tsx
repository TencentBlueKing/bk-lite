import type { CatalogStatus } from '@/app/apm/types';

const statusCopy: Record<CatalogStatus, { className: string; dotClassName: string; label: string }> = {
  active: {
    className: 'border-[color-mix(in_srgb,var(--color-success)_24%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg))] text-[var(--color-success)]',
    dotClassName: 'bg-[var(--color-success)]',
    label: '活跃',
  },
  silent: {
    className: 'border-[color-mix(in_srgb,var(--theme-color-status-warning)_28%,var(--color-border))] bg-[color-mix(in_srgb,var(--theme-color-status-warning)_10%,var(--color-bg))] text-[var(--theme-color-status-warning)]',
    dotClassName: 'bg-[var(--theme-color-status-warning)]',
    label: '静默',
  },
  archived: {
    className: 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)]',
    dotClassName: 'bg-[var(--color-text-4)]',
    label: '已归档',
  },
};

export default function ApmStatusTag({ status }: { status: CatalogStatus }) {
  const item = statusCopy[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${item.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${item.dotClassName}`} aria-hidden="true" />
      {item.label}
    </span>
  );
}
