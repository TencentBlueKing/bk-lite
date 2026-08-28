'use client';

import type { ReactNode } from 'react';

export interface DesignCompareFrameProps {
  title: string;
  rule: string;
  note?: string;
  before: ReactNode;
  after: ReactNode;
  beforeCaption?: string;
  afterCaption?: string;
}

/**
 * Story-only layout shell for Before / After design compares.
 * Not a shared product component — lives under stories/.
 */
export function DesignCompareFrame({
  title,
  rule,
  note = 'After 仅为 DESIGN 契约示意（Story 内包装），不是线上同一文件。',
  before,
  after,
  beforeCaption = 'Before · 当前实现',
  afterCaption = 'After · DESIGN 目标态示意',
}: DesignCompareFrameProps) {
  return (
    <div className="space-y-4 p-4" style={{ background: 'var(--color-background-body)' }}>
      <header className="space-y-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <h1 className="m-0 text-base font-semibold text-[var(--color-text-1)]">{title}</h1>
        <p className="m-0 text-sm text-[var(--color-text-2)]">
          <span className="font-medium text-[var(--color-primary)]">{rule}</span>
          {' · '}
          {note}
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
          <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2 text-xs font-medium text-[var(--color-text-2)]">
            {beforeCaption}
          </div>
          <div className="min-h-[280px] flex-1 p-3">{before}</div>
        </section>

        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-[var(--color-primary)] bg-[var(--color-bg)]">
          <div
            className="border-b border-[var(--color-border)] px-3 py-2 text-xs font-medium text-[var(--color-primary)]"
            style={{
              background:
                'color-mix(in srgb, var(--color-primary) 8%, transparent)',
            }}
          >
            {afterCaption}
          </div>
          <div className="min-h-[280px] flex-1 p-3">{after}</div>
        </section>
      </div>
    </div>
  );
}

export function CompareAnnotation({ children }: { children: ReactNode }) {
  return (
    <p className="mb-3 rounded border border-dashed border-[var(--color-border)] bg-[var(--color-fill-1)] px-2 py-1.5 text-xs text-[var(--color-text-3)]">
      {children}
    </p>
  );
}
