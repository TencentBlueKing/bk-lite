'use client';

import React from 'react';
import classic from '../index.module.scss';
import host from './layered.module.scss';

/** 专业盘分区标题：蓝浮标 + 字重与主机概览同一套。 */
export function ProSectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className={host.sectionHead}>
      <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>{children}</div>
    </div>
  );
}
