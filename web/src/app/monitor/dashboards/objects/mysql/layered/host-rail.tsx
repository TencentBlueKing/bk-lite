'use client';

import React from 'react';
import Link from 'next/link';
import type { MysqlHostCandidate } from './ia';
import shell from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

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
 * 健康六卡下的通栏宿主条。复用事件轨壳，左簇贴边、查看主机贴右缘。
 * 未关联不渲染整条，避免空条或置灰入口。
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
      className={`${shell.eventsRail} ${pro.hostStrip}`}
      data-host-strip=""
      data-host-linked={host ? '' : undefined}
      aria-busy={loading && !host ? true : undefined}
    >
      {host ? (
        <>
          <div className={pro.hostStripLead}>
            <span className={pro.hostStripLabel}>所属主机</span>
            <span className={pro.hostStripName} title={host.name}>{host.name}</span>
            <span className={pro.hostStripMetric}>
              CPU <b>{percentText(cpuPercent)}</b>
            </span>
            <span className={pro.hostStripMetric}>
              内存 <b>{percentText(memPercent)}</b>
            </span>
          </div>
          <Link className={`${shell.jumpBtn} ${pro.hostStripLink} no-underline`} href={href}>
            查看主机
          </Link>
        </>
      ) : (
        <span className={shell.eventsEmpty}>加载中</span>
      )}
    </div>
  );
}
