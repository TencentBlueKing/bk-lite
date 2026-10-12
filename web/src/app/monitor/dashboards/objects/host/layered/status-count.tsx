'use client';

import React from 'react';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export interface StatusCountItem {
  key: string;
  label: string;
  value: string;
  tone?: string;
}

/** 进程态计数：整数 +「个」+ 语义色。不画箭头，也不把计数做成趋势图。 */
export default function StatusCountRow({ items }: { items: StatusCountItem[] }) {
  if (!items.length) return null;
  return (
    <section className={`${classic.panel} ${styles.statusPanel}`}>
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>进程状态</div>
      </div>
      <div className={styles.pillRow}>
        {items.map((item) => (
          <div key={item.key} className={styles.pill}>
            <span className={styles.pillLabel}>{item.label}</span>
            <span className={styles.pillValue} style={item.tone ? { color: item.tone } : undefined}>
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
