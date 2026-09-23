'use client';

import type { ReactNode } from 'react';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';

export type SetupStepState = 'active' | 'complete' | 'pending' | 'danger';

export default function SetupStep({
  n,
  title,
  state,
  isLast = false,
  children,
}: {
  n: number;
  title: string;
  state: SetupStepState;
  isLast?: boolean;
  children: ReactNode;
}) {
  const badgeClass =
    state === 'complete'
      ? 'bg-[var(--color-success)] text-white'
      : state === 'danger'
        ? 'bg-[var(--color-fail)] text-white'
        : state === 'active'
          ? 'bg-[var(--color-primary)] text-white'
          : 'bg-[var(--color-fill-2)] text-[var(--color-text-3)] ring-1 ring-inset ring-[var(--color-border-2)]';

  return (
    <li
      className="grid grid-cols-[28px_minmax(0,1fr)] gap-3.5"
      aria-current={state === 'active' ? 'step' : undefined}
    >
      <div className="flex flex-col items-center">
        <span
          className={`inline-flex size-[26px] shrink-0 items-center justify-center rounded-full text-xs font-semibold ${badgeClass}`}
        >
          {state === 'complete' ? (
            <CheckOutlined aria-hidden className="text-[10px]" />
          ) : state === 'danger' ? (
            <CloseOutlined aria-hidden className="text-[10px]" />
          ) : (
            n
          )}
        </span>
        {!isLast ? (
          <span className="my-1.5 w-px min-h-[18px] flex-1 bg-[var(--color-border-2)]" aria-hidden />
        ) : null}
      </div>
      <section className={`min-w-0 ${isLast ? 'pb-0' : 'pb-6'}`}>
        <h2
          className={`text-sm font-medium ${
            state === 'pending' ? 'text-[var(--color-text-3)]' : 'text-[var(--color-text-1)]'
          }`}
        >
          {title}
        </h2>
        <div className="mt-3 space-y-3">{children}</div>
      </section>
    </li>
  );
}
