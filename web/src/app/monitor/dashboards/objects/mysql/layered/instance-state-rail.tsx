'use client';

import React from 'react';
import type { MysqlProHeader } from './ia';
import styles from '../index.module.scss';

interface MysqlInstanceStateRailProps {
  header: MysqlProHeader | null;
  pending: boolean;
}

const SKELETON_PILLS = [
  { key: 'role', width: 'w-12' },
  { key: 'aside', width: 'w-12' },
  { key: 'binlog', width: 'w-28' }
] as const;

/**
 * 顶栏标题区之下、内容 Tab 之上的实例态窄条。
 * 与所属主机条分开：不复用事件轨，也不进宿主条。
 * 加载时只在条内留浅骨架，高度与有数态相同。
 */
export default function MysqlInstanceStateRail({
  header,
  pending
}: MysqlInstanceStateRailProps) {
  return (
    <div
      className={`${styles.instanceStateRail} box-border flex min-h-11 w-full items-center gap-2 rounded-lg px-3 py-2`}
      data-instance-state=""
      data-instance-state-pending={pending ? '' : undefined}
      aria-busy={pending ? true : undefined}
    >
      <span className={`${styles.instanceStateLabel} shrink-0 text-xs font-medium`}>实例态</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        {pending ? SKELETON_PILLS.map((pill) => (
          <span
            key={pill.key}
            className={`h-6 ${pill.width} animate-neutral-pulse rounded-full bg-[var(--color-fill-2)]`}
            aria-hidden="true"
          />
        )) : (
          <>
            {header?.pill ? (
              <span className={`${styles.identityPill} ${styles.identityPillRole}`}>{header.pill}</span>
            ) : null}
            {header?.aside ? (
              <span className={styles.identityPill}>{header.aside}</span>
            ) : null}
            {header?.binlog ? (
              <span className={styles.identityPill}>{header.binlog}</span>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
