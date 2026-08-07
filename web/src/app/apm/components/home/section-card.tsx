'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Button } from 'antd';

interface SectionCardProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  viewAllHref?: string;
  viewAllLabel?: string;
  failed?: boolean;
  onRetry?: () => void;
  children: ReactNode;
  /** Extra class on the card shell */
  className?: string;
  /** Minimum body height so empty/fail states keep row alignment */
  bodyMinHeight?: number;
}

export default function SectionCard({
  icon,
  title,
  subtitle,
  viewAllHref,
  viewAllLabel = '查看全部 →',
  failed = false,
  onRetry,
  children,
  className = '',
  bodyMinHeight = 200,
}: SectionCardProps) {
  return (
    <div
      className={`flex h-full min-h-0 flex-col rounded-[6px] border border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-5 ${className}`}
    >
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {icon ? <span className="inline-flex shrink-0 text-[15px] leading-none">{icon}</span> : null}
          <h3 className="m-0 truncate text-[15px] font-semibold leading-6 text-[var(--color-text-1)]">
            {title}
          </h3>
          {subtitle ? (
            <span className="shrink-0 text-xs font-normal text-[var(--color-text-3)]">{subtitle}</span>
          ) : null}
        </div>
        {viewAllHref ? (
          <Link
            href={viewAllHref}
            className="shrink-0 text-[13px] text-[var(--color-primary)] hover:underline"
          >
            {viewAllLabel}
          </Link>
        ) : null}
      </div>
      <div className="min-h-0 flex-1" style={{ minHeight: bodyMinHeight }}>
        {failed ? (
          <div className="flex h-full items-center justify-center py-10 text-center">
            <Button type="link" onClick={onRetry}>
              加载失败，点击重试
            </Button>
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

export function SectionEmpty({
  children,
  tone = 'muted',
}: {
  children: ReactNode;
  tone?: 'muted' | 'success';
}) {
  return (
    <div
      className={`flex h-full min-h-[160px] items-center justify-center px-4 py-10 text-center text-[13px] leading-5 ${
        tone === 'success' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-3)]'
      }`}
    >
      {children}
    </div>
  );
}

export function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: 'success' | 'danger' | 'warning';
}) {
  const styles =
    tone === 'success'
      ? {
          color: 'var(--color-success)',
          background: 'color-mix(in srgb, var(--color-success) 12%, var(--color-bg))',
        }
      : tone === 'danger'
        ? {
            color: 'var(--color-fail)',
            background: 'color-mix(in srgb, var(--color-fail) 12%, var(--color-bg))',
          }
        : {
            color: 'var(--theme-color-status-warning)',
            background: 'color-mix(in srgb, var(--theme-color-status-warning) 12%, var(--color-bg))',
          };

  return (
    <span
      className="inline-block min-w-[50px] rounded px-2.5 py-0.5 text-center text-[11px] font-medium leading-[18px]"
      style={styles}
    >
      {label}
    </span>
  );
}
