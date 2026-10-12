'use client';

import React from 'react';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export type ProcessStatusTone = 'calm' | 'warning' | 'danger' | 'neutral';

export interface StatusCountItem {
  key: string;
  label: string;
  /** 整数。没有读数时为 null，卡上显示 --。 */
  value: number | null;
  tone: ProcessStatusTone;
}

export interface ProcessStatusCounts {
  blocked: number | null;
  zombies: number | null;
  running: number | null;
  sleeping: number | null;
  /** 进程表 procstat 线程数合计。 */
  threads: number | null;
  /** 进程表 procstat 打开文件数合计。 */
  fds: number | null;
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
  const tone: ProcessStatusTone = value == null || value <= 0
    ? 'calm'
    : key === 'zombies'
      ? 'danger'
      : 'warning';
  return { key, label, value, tone };
};

const neutralItem = (key: string, label: string, value: number | null): StatusCountItem => ({
  key,
  label,
  value,
  tone: 'neutral'
});

/**
 * 固定七张卡铺满一行。进程总数是运行中/休眠/阻塞/僵尸之和；
 * 线程、句柄来自进程表合计。
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
    neutralItem('sleeping', '休眠', sleeping),
    semanticItem('blocked', '阻塞', blocked, true),
    semanticItem('zombies', '僵尸', zombies, true),
    neutralItem('total', '进程总数', total),
    neutralItem('threads', '线程', roundCount(counts.threads)),
    neutralItem('fds', '句柄', roundCount(counts.fds))
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
        <div className={classic.sectionLabel}>进程状态</div>
      </div>
      <div className={styles.statusCards}>
        {items.map((item) => (
          <div key={item.key} className={`${styles.statusCard} ${TONE_CLASS[item.tone]}`}>
            <span className={styles.statusLabel}>{item.label}</span>
            <span className={styles.statusValueRow}>
              <span className={styles.statusValue}>{item.value == null ? '--' : item.value}</span>
              {item.value != null ? <span className={styles.statusUnit}>个</span> : null}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
