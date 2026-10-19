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
}

const percentText = (value: number) => `${Math.round(value)}%`;

/** 所属主机轻轨。没有关联时不写主机名，数字只在有采时出现。 */
export default function MysqlHostRail({
  host,
  href,
  cpuPercent,
  memPercent
}: MysqlHostRailProps) {
  const showCpu = cpuPercent != null && Number.isFinite(cpuPercent);
  const showMem = memPercent != null && Number.isFinite(memPercent);
  return (
    <div className={shell.eventsRail}>
      <span className={pro.railLabel}>所属主机</span>
      {host ? (
        <span className={pro.railHost}>{host.name}</span>
      ) : (
        <span className={shell.eventsEmpty}>未关联主机</span>
      )}
      {showCpu || showMem ? (
        <span className={pro.railNums}>
          {showCpu ? <span>CPU <b>{percentText(cpuPercent as number)}</b></span> : null}
          {showMem ? <span>内存 <b>{percentText(memPercent as number)}</b></span> : null}
        </span>
      ) : null}
      <Link className={`${shell.jumpBtn} ${pro.railLink} no-underline`} href={href}>
        查看主机
      </Link>
    </div>
  );
}
