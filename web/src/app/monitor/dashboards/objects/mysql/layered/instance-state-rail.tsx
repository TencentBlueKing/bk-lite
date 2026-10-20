'use client';

import React from 'react';
import type { MysqlProHeader } from './ia';
import styles from '../index.module.scss';

interface MysqlInstanceStateRailProps {
  header: MysqlProHeader | null;
  pending: boolean;
}

/**
 * 顶栏标题区之下、内容 Tab 之上的实例态窄条。
 * 与所属主机条分开：不复用事件轨，也不进宿主条。
 * 条宽贴内容。加载时只在「实例态」旁写「加载中」，不留灰骨架、不进顶栏 meta。
 * pending 时忽略 header，避免切实例还亮着上一份角色 / 只读 / Binlog。
 */
export default function MysqlInstanceStateRail({
  header,
  pending
}: MysqlInstanceStateRailProps) {
  return (
    <div
      className={`${styles.instanceStateRail} box-border inline-flex min-h-11 max-w-full flex-wrap items-center gap-2 rounded-lg px-3 py-2`}
      data-instance-state=""
      data-instance-state-pending={pending ? '' : undefined}
      aria-busy={pending ? true : undefined}
    >
      <span className={`${styles.instanceStateLabel} shrink-0 text-xs font-medium`}>实例态</span>
      {pending ? (
        <span className={styles.instanceStateLoading}>加载中</span>
      ) : (
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
  );
}
