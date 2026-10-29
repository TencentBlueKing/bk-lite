'use client';

import React from 'react';
import classic from '../index.module.scss';
import host from './layered.module.scss';

/**
 * KPI / 焦点卡壳的公共类名。数值来自主机 layered.module.scss，对象只拿这份入口：
 * 圆角 12、KPI padding 8×12、栅格 gap 12、焦点卡 min-height 112、折角 22×22。
 */
export const proChromeClass = {
  kpiGrid: host.kpiGrid,
  kpiCard: host.kpiCard,
  kpiCardLoading: host.kpiCardLoading,
  kpiLabel: host.kpiLabel,
  kpiValueRow: host.kpiValueRow,
  kpiValue: host.kpiValue,
  kpiAside: host.kpiAside,
  shortcutGrid: host.shortcutGrid,
  shortcutCard: host.shortcutCard,
  shortcutCopy: host.shortcutCopy,
  shortcutValue: host.shortcutValue,
  shortcutSub: host.shortcutSub,
  shortcutMain: host.shortcutMain,
  focusChart: host.focusChart,
  jumpBtn: host.jumpBtn
} as const;

/** 重点关注卡：左文右图。边框与圆角来自 classic.panel，排布来自 shortcutCard。 */
export function ProFocusCard({
  children,
  className
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={[classic.panel, host.shortcutCard, className].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}
