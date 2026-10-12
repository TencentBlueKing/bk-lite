'use client';

import React from 'react';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export type ProcessStatusTone = 'calm' | 'warning' | 'danger';

export interface StatusCountItem {
  key: string;
  label: string;
  /** 整数。没有读数时为 null，卡上显示 --。 */
  value: number | null;
  tone: ProcessStatusTone;
}

const TONE_CLASS: Record<ProcessStatusTone, string> = {
  calm: styles.statusCardCalm,
  warning: styles.statusCardWarning,
  danger: styles.statusCardDanger
};

/** 阻塞 >0 为警告，僵尸 >0 为危险，0 为平静。两卡各自上色。 */
export const processStatusItems = (
  blocked: number | null,
  zombies: number | null,
  loading: boolean
): StatusCountItem[] => {
  const item = (
    key: 'blocked' | 'zombies',
    label: string,
    value: number | null
  ): StatusCountItem[] => {
    if (value == null && !loading) return [];
    const rounded = value == null || !Number.isFinite(value) ? null : Math.round(value);
    const tone: ProcessStatusTone = rounded == null || rounded <= 0
      ? 'calm'
      : key === 'zombies'
        ? 'danger'
        : 'warning';
    return [{ key, label, value: rounded, tone }];
  };
  return [
    ...item('blocked', '阻塞', blocked),
    ...item('zombies', '僵尸', zombies)
  ];
};

/** 进程状态：标签在上，大号整数 +「个」，左侧色条。不画涨跌箭头。 */
export default function StatusCountRow({
  items,
  onOpenProcess
}: {
  items: StatusCountItem[];
  onOpenProcess?: () => void;
}) {
  if (!items.length) return null;
  return (
    <section className={`${classic.panel} ${styles.statusPanel}`}>
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>进程状态</div>
        {onOpenProcess ? (
          <button type="button" className={`${styles.jumpBtn} ${styles.statusJump}`} onClick={onOpenProcess}>
            查看进程
          </button>
        ) : null}
      </div>
      <div className={styles.statusCards}>
        {items.map((item) => {
          const body = (
            <>
              <span className={styles.statusLabel}>{item.label}</span>
              <span className={styles.statusValueRow}>
                <span className={styles.statusValue}>{item.value == null ? '--' : item.value}</span>
                {item.value != null ? <span className={styles.statusUnit}>个</span> : null}
              </span>
            </>
          );
          const className = `${styles.statusCard} ${TONE_CLASS[item.tone]}`;
          if (!onOpenProcess) {
            return (
              <div key={item.key} className={className}>
                {body}
              </div>
            );
          }
          return (
            <button
              key={item.key}
              type="button"
              className={`${className} ${styles.statusCardButton}`}
              onClick={onOpenProcess}
            >
              {body}
            </button>
          );
        })}
      </div>
    </section>
  );
}
