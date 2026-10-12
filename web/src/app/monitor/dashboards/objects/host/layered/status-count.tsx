'use client';

import React from 'react';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export type ProcessStatusTone = 'calm' | 'warning' | 'danger' | 'neutral';
export type ProcessStatusLayout = 'fill' | 'pair';

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
 * 运行中、休眠、阻塞、僵尸都能读到时横排五卡，进程总数是这四项之和。
 * 采集侧没有单独的总数序列；任一项没有读数则只留阻塞/僵尸两张等宽卡。
 */
export const processStatusView = (
  counts: ProcessStatusCounts,
  pending: boolean
): { layout: ProcessStatusLayout; items: StatusCountItem[] } => {
  const blocked = roundCount(counts.blocked);
  const zombies = roundCount(counts.zombies);
  const running = roundCount(counts.running);
  const sleeping = roundCount(counts.sleeping);
  const fillReady = [blocked, zombies, running, sleeping].every((value) => value != null);
  if (pending || fillReady) {
    const total = fillReady
      ? (blocked as number) + (zombies as number) + (running as number) + (sleeping as number)
      : null;
    return {
      layout: 'fill',
      items: [
        semanticItem('blocked', '阻塞', blocked, true),
        semanticItem('zombies', '僵尸', zombies, true),
        neutralItem('running', '运行中', running),
        neutralItem('sleeping', '休眠', sleeping),
        neutralItem('total', '进程总数', total)
      ].filter((item): item is StatusCountItem => item != null)
    };
  }
  return {
    layout: 'pair',
    items: [
      semanticItem('blocked', '阻塞', blocked, false),
      semanticItem('zombies', '僵尸', zombies, false)
    ].filter((item): item is StatusCountItem => item != null)
  };
};

/** 进程状态：标签在上，整数 +「个」，左侧色条。不画涨跌箭头。 */
export default function StatusCountRow({
  items,
  layout
}: {
  items: StatusCountItem[];
  layout: ProcessStatusLayout;
}) {
  if (!items.length) return null;
  return (
    <section className={`${classic.panel} ${styles.statusPanel}`}>
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>进程状态</div>
      </div>
      <div className={layout === 'fill' ? styles.statusCardsFill : styles.statusCardsPair}>
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
