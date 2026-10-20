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

const percentText = (value: number) => `${Math.round(value)}%`;

/** 所属主机内联旁注。复用事件轨壳，但收成贴内容的一条，不拉通栏。 */
export default function MysqlHostRail({
  host,
  href,
  cpuPercent,
  memPercent,
  loading = false
}: MysqlHostRailProps) {
  const showCpu = cpuPercent != null && Number.isFinite(cpuPercent);
  const showMem = memPercent != null && Number.isFinite(memPercent);
  return (
    <div className={pro.hostAsideWrap}>
      <div className={`${shell.eventsRail} ${pro.hostAside}`}>
        {loading ? (
          <span className={shell.eventsEmpty}>加载中</span>
        ) : host ? (
          <>
            <span className={pro.railHost}>{host.name}</span>
            {showCpu ? (
              <>
                <span className={pro.railDot} aria-hidden="true">·</span>
                <span>CPU <b>{percentText(cpuPercent as number)}</b></span>
              </>
            ) : null}
            {showMem ? (
              <>
                <span className={pro.railDot} aria-hidden="true">·</span>
                <span>内存 <b>{percentText(memPercent as number)}</b></span>
              </>
            ) : null}
            <Link className={`${shell.jumpBtn} ${pro.railLink} no-underline`} href={href}>
              查看主机
            </Link>
          </>
        ) : (
          <span className={shell.eventsEmpty}>未关联主机</span>
        )}
      </div>
    </div>
  );
}
