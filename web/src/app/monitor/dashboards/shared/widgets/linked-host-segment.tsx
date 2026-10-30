'use client';

import Link from 'next/link';
import { useDashboardText } from '../utils/content-i18n';
import {
  LINKED_HOST_LABEL,
  LINKED_HOST_LABEL_ID,
  LINKED_HOST_UNLINKED,
  LINKED_HOST_UNLINKED_ID,
  type LinkedHostCandidate
} from '../linked-host';

/**
 * 专业盘实例名下的所属主机槽。
 * 有唯一主机关联时，「所属主机」后接可点的主机名。
 * 对不上时仍留下「无所属主机」，不是链接。
 */
export function LinkedHostSegment({
  host,
  href,
  pending
}: {
  host: LinkedHostCandidate | null;
  href: string;
  pending: boolean;
}) {
  const { t } = useDashboardText();
  if (pending) {
    return (
      <span
        className="inline-block h-3 w-[88px] shrink-0 animate-neutral-pulse rounded bg-[var(--color-fill-2)]"
        data-linked-host="pending"
        aria-hidden="true"
      />
    );
  }
  if (host && href) {
    return (
      <span
        className="inline-flex min-w-0 items-center overflow-hidden"
        data-linked-host="linked"
        data-mysql-identity-host="linked"
      >
        <span className="mr-1 shrink-0">{t(LINKED_HOST_LABEL_ID, LINKED_HOST_LABEL)}</span>
        <Link
          className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-primary)] underline underline-offset-2"
          href={href}
          title={host.name}
        >
          {host.name}
        </Link>
      </span>
    );
  }
  return (
    <span
      className="shrink-0 text-[var(--color-text-3)]"
      data-linked-host="unlinked"
      data-mysql-identity-host="unlinked"
    >
      {t(LINKED_HOST_UNLINKED_ID, LINKED_HOST_UNLINKED)}
    </span>
  );
}
