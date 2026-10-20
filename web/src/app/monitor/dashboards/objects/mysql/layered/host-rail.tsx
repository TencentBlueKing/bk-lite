'use client';

import React from 'react';
import Link from 'next/link';
import type { MysqlHostCandidate } from './ia';
import shell from '../../host/layered/layered.module.scss';

interface MysqlHostRailProps {
  host: MysqlHostCandidate | null;
  href: string;
  cpuPercent: number | null;
  memPercent: number | null;
  loading?: boolean;
}

const percentText = (value: number | null) => (
  value != null && Number.isFinite(value) ? `${Math.round(value)}%` : '—'
);

/**
 * 健康六卡下的通栏宿主条。壳、主机名胶囊和入口都用主机事件轨的现成类。
 * 未关联不渲染整条。
 */
export default function MysqlHostRail({
  host,
  href,
  cpuPercent,
  memPercent,
  loading = false
}: MysqlHostRailProps) {
  if (!host && !loading) return null;

  return (
    <div
      className={shell.eventsRail}
      data-host-strip=""
      data-host-linked={host ? '' : undefined}
      aria-busy={loading && !host ? true : undefined}
    >
      {host ? (
        <>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="shrink-0 text-[var(--color-text-3)]">所属主机</span>
            <span className={`${shell.eventsChip} truncate`} title={host.name}>{host.name}</span>
            <span className="shrink-0 whitespace-nowrap">
              CPU <b className="font-semibold tabular-nums text-[var(--color-text-1)]">{percentText(cpuPercent)}</b>
            </span>
            <span className="shrink-0 whitespace-nowrap">
              内存 <b className="font-semibold tabular-nums text-[var(--color-text-1)]">{percentText(memPercent)}</b>
            </span>
          </div>
          <Link className={`${shell.jumpBtn} !mt-0 ml-auto shrink-0 self-center whitespace-nowrap no-underline`} href={href}>
            查看主机
          </Link>
        </>
      ) : (
        <span className={shell.eventsEmpty}>加载中</span>
      )}
    </div>
  );
}
