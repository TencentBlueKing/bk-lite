'use client';

import React, { type ReactNode } from 'react';
import { Skeleton } from 'antd';

interface PanelProps {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  footer?: ReactNode;
}

export function SystemManagerWorkbenchPanel({
  title,
  extra,
  children,
  className = '',
  bodyClassName = '',
  footer,
}: PanelProps) {
  return (
    <section className={`flex h-full min-h-0 flex-col overflow-hidden rounded-md bg-[var(--color-bg)] ${className}`}>
      {title ? (
        <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/60 px-4">
          <div className="min-w-0 truncate text-sm font-semibold text-[var(--color-text-1)]">{title}</div>
          {extra ? <div className="shrink-0">{extra}</div> : null}
        </header>
      ) : null}
      <div className={`min-h-0 flex-1 overflow-auto ${bodyClassName}`}>{children}</div>
      {footer ? (
        <footer className="flex h-12 shrink-0 items-center justify-between gap-3 border-t border-[var(--color-border-1)] px-5">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}

interface SplitProps {
  header?: ReactNode;
  left?: ReactNode;
  right: ReactNode;
  leftWidthClassName?: string;
  loading?: boolean;
}

export default function SystemManagerWorkbenchShell({
  header,
  left,
  right,
  leftWidthClassName = 'w-[230px]',
  loading = false,
}: SplitProps) {
  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        {header ? <div className="shrink-0">{header}</div> : null}
        <div className="mt-4 flex min-h-0 flex-1 gap-4" aria-busy="true" aria-label="loading">
          {left ? (
            <div className={`h-full ${leftWidthClassName} overflow-hidden rounded-md bg-[var(--color-bg)] p-4`}>
              <Skeleton active paragraph={{ rows: 8 }} />
            </div>
          ) : null}
          <div className="h-full min-w-0 flex-1 overflow-hidden rounded-md bg-[var(--color-bg)] p-4">
            <Skeleton active paragraph={{ rows: 8 }} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {header ? <div className="shrink-0">{header}</div> : null}
      <div className={`flex min-h-0 flex-1 gap-4 ${header ? 'mt-4' : ''}`}>
        {left ? <div className={`h-full min-h-0 shrink-0 ${leftWidthClassName}`}>{left}</div> : null}
        <div className="h-full min-h-0 min-w-0 flex-1">{right}</div>
      </div>
    </div>
  );
}

interface SettingsSectionProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export function SystemManagerSettingsSection({
  title,
  children,
  className = '',
}: SettingsSectionProps) {
  return (
    <section className={`border-t border-[var(--color-border-1)] pt-5 first:border-t-0 first:pt-0 ${className}`}>
      <div className="mb-3.5 flex items-center gap-2">
        <span className="h-3.5 w-1 rounded-full bg-[var(--color-primary)]" aria-hidden />
        <h3 className="text-[13px] font-semibold text-[var(--color-text-1)]">{title}</h3>
      </div>
      {children}
    </section>
  );
}
