'use client';

import React from 'react';
import classic from '../index.module.scss';
import host from './layered.module.scss';

/** 专业盘分区标题：蓝浮标 + 字重与主机概览同一套。extra 贴在同一行右侧。 */
export function ProSectionTitle({
  children,
  extra
}: {
  children: React.ReactNode;
  extra?: React.ReactNode;
}) {
  return (
    <div className={host.sectionHead}>
      <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>{children}</div>
      {extra ? <div className={host.sectionExtra}>{extra}</div> : null}
    </div>
  );
}
