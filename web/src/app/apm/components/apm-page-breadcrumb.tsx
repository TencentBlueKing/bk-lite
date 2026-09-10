'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useTranslation } from '@/utils/i18n';

export interface ApmPageBreadcrumbProps {
  parentHref: string;
  parentLabel: string;
  parentAriaLabel?: string;
  current: ReactNode;
  trailing?: ReactNode;
}

export default function ApmPageBreadcrumb({
  parentHref,
  parentLabel,
  parentAriaLabel,
  current,
  trailing,
}: ApmPageBreadcrumbProps) {
  const { t } = useTranslation();

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <nav
        aria-label={t('apm.common.breadcrumb', '页面路径')}
        className="flex min-w-0 items-center gap-1.5"
      >
        <Link
          href={parentHref}
          aria-label={parentAriaLabel ?? parentLabel}
          className="shrink-0 text-sm text-[var(--color-text-3)] no-underline transition-colors hover:text-[var(--color-primary)]"
        >
          {parentLabel}
        </Link>
        <span className="shrink-0 text-[var(--color-text-3)]" aria-hidden="true">
          /
        </span>
        <div className="flex min-w-0 items-center gap-1.5">{current}</div>
      </nav>
      {trailing}
    </div>
  );
}
