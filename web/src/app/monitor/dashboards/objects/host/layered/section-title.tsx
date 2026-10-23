'use client';

import React from 'react';
import classic from '../index.module.scss';
import host from './layered.module.scss';

/** 专业盘分区标题：蓝浮标 + 字重与主机概览同一套。hint 贴标题右侧，extra 贴行尾。 */
export function ProSectionTitle({
  children,
  hint,
  extra
}: {
  children: React.ReactNode;
  /** 标题右侧说明槽。不传不占位。 */
  hint?: React.ReactNode;
  extra?: React.ReactNode;
}) {
  return (
    <div className={host.sectionHead}>
      <div className={`${classic.sectionLabel} ${host.sectionTitle}`}>
        {hint ? (
          <span className="inline-flex min-w-0 items-baseline gap-1.5">
            <span className="min-w-0">{children}</span>
            {hint}
          </span>
        ) : children}
      </div>
      {extra ? <div className={host.sectionExtra}>{extra}</div> : null}
    </div>
  );
}

/** 标题到内容 12px（gap-3）。区与区的间距留给父级列表。 */
export function ProSection({
  id,
  title,
  hint,
  children,
  className
}: {
  id?: string;
  title: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={['flex min-w-0 flex-col gap-3', className].filter(Boolean).join(' ')}>
      <ProSectionTitle hint={hint}>{title}</ProSectionTitle>
      {children}
    </section>
  );
}
