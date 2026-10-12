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
 * 有读数的状态各出一张窄卡。四项都齐时补进程总数（四项之和）。
 * 采集侧没有单独的总数序列；运行中/休眠都没有时只留阻塞/僵尸。
 */
export const processStatusView = (
  counts: ProcessStatusCounts,
  pending: boolean
): StatusCountItem[] => {
  const blocked = roundCount(counts.blocked);
  const zombies = roundCount(counts.zombies);
  const running = roundCount(counts.running);
  const sleeping = roundCount(counts.sleeping);
  const states = [running, sleeping, blocked, zombies];
  const allReady = states.every((value) => value != null);
  if (pending) {
    const total = allReady
      ? (running as number) + (sleeping as number) + (blocked as number) + (zombies as number)
      : null;
    return [
      neutralItem('running', '运行中', running),
      neutralItem('sleeping', '休眠', sleeping),
      semanticItem('blocked', '阻塞', blocked, true),
      semanticItem('zombies', '僵尸', zombies, true),
      neutralItem('total', '进程总数', total)
    ].filter((item): item is StatusCountItem => item != null);
  }
  const items: StatusCountItem[] = [];
  if (running != null) items.push(neutralItem('running', '运行中', running));
  if (sleeping != null) items.push(neutralItem('sleeping', '休眠', sleeping));
  const blockedItem = semanticItem('blocked', '阻塞', blocked, false);
  const zombiesItem = semanticItem('zombies', '僵尸', zombies, false);
  if (blockedItem) items.push(blockedItem);
  if (zombiesItem) items.push(zombiesItem);
  if (allReady) {
    items.push(neutralItem(
      'total',
      '进程总数',
      (running as number) + (sleeping as number) + (blocked as number) + (zombies as number)
    ));
  }
  return items;
};

/** 进程状态：标签在上，整数 +「个」，左侧色条。不画涨跌箭头。 */
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
