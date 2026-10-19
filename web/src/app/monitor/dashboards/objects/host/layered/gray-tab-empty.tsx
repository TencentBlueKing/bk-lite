'use client';

import React from 'react';
import classic from '../index.module.scss';
import host from './layered.module.scss';

/** 无采 Tab 的空态。字色和卡片壳跟主机趋势卡空态一致。 */
export function GrayTabEmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <section className={`${classic.panel} ${host.chartPanel}`}>
      <div className={host.chartEmpty}>
        <div className="text-center">
          <div className="text-[13px] font-semibold text-[var(--color-text-2)]">{title}</div>
          <div className="mt-1 text-[12px] text-[var(--color-text-3)]">{hint}</div>
        </div>
      </div>
    </section>
  );
}
