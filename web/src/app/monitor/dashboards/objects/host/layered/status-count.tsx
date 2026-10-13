'use client';

import React from 'react';
import { Tooltip } from 'antd';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export type ProcessStatusTone = 'calm' | 'warning' | 'danger' | 'neutral';

/** 休眠卡悬浮说明。指标描述表没有这句 Linux/Windows 语义，按产品口径写在这里。 */
export const SLEEPING_STATUS_HINT = '休眠：Linux 多为可中断睡眠(S)，含等待 I/O；Windows 为等待态。';

export interface StatusCountItem {
  key: string;
  label: string;
  /** 整数。没有读数时为 null，卡上显示 --。 */
  value: number | null;
  tone: ProcessStatusTone;
  hint?: string;
}

export interface ProcessStatusCounts {
  blocked: number | null;
  zombies: number | null;
  running: number | null;
  sleeping: number | null;
}

const TONE_CLASS: Record<ProcessStatusTone, string> = {
  calm: styles.statusCardCalm,
  warning: styles.statusCardWarning,
  danger: styles.statusCardDanger,
  neutral: styles.statusCardNeutral
};

const roundCount = (value: number | null) => (
  value == null || !Number.isFinite(value) ? null : Math.round(value)
);

const semanticItem = (
  key: 'blocked' | 'zombies',
  label: string,
  value: number | null,
  keepEmpty: boolean
): StatusCountItem | null => {
  if (value == null && !keepEmpty) return null;
  return { key, label, value, tone: 'neutral' };
};

const neutralItem = (
  key: string,
  label: string,
  value: number | null,
  hint?: string
): StatusCountItem => ({
  key,
  label,
  value,
  tone: 'neutral',
  hint
});

/**
 * 固定五张卡铺满一行：运行中、休眠、阻塞、僵尸、进程总数。
 * 进程总数是前四项之和。句柄、线程不进状态卡。
 * settled=false 时缺读数仍占位显示 --；settled=true 且某卡不可采集时仍占位 --（不造假数、不画箭头）。
 */
export const processStatusView = (
  counts: ProcessStatusCounts,
  options?: { settled?: boolean }
): StatusCountItem[] => {
  const settled = options?.settled !== false;
  const blocked = roundCount(counts.blocked);
  const zombies = roundCount(counts.zombies);
  const running = roundCount(counts.running);
  const sleeping = roundCount(counts.sleeping);
  const states = [running, sleeping, blocked, zombies];
  const total = settled && states.every((value) => value != null)
    ? (running as number) + (sleeping as number) + (blocked as number) + (zombies as number)
    : null;
  return [
    neutralItem('running', '运行中', running),
    neutralItem('sleeping', '休眠', sleeping, SLEEPING_STATUS_HINT),
    semanticItem('blocked', '阻塞', blocked, true),
    semanticItem('zombies', '僵尸', zombies, true),
    neutralItem('total', '进程总数', total)
  ].filter((item): item is StatusCountItem => item != null);
};

/** 进程状态：标签在上，整数 +「个」，左侧色条。不画涨跌箭头、不画 spark。 */
export default function StatusCountRow({
  items
}: {
  items: StatusCountItem[];
}) {
  if (!items.length) return null;
  return (
    <section className={`${classic.panel} ${styles.statusPanel}`}>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>进程状态</div>
      </div>
      <div className={styles.statusCards}>
        {items.map((item) => {
          const card = (
            <div className={`${styles.statusCard} ${TONE_CLASS[item.tone]}`}>
              <span className={item.hint ? styles.statusHint : styles.statusLabel}>{item.label}</span>
              <span className={styles.statusValueRow}>
                <span className={styles.statusValue}>{item.value == null ? '--' : item.value}</span>
                {item.value != null ? <span className={styles.statusUnit}>个</span> : null}
              </span>
            </div>
          );
          if (!item.hint) return <React.Fragment key={item.key}>{card}</React.Fragment>;
          return (
            <Tooltip key={item.key} title={item.hint}>
              {card}
            </Tooltip>
          );
        })}
      </div>
    </section>
  );
}
