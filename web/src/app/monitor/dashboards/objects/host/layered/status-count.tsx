'use client';

import React from 'react';
import { ChartData } from '@/app/monitor/types';
import { Spark } from './signal-bar';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export interface StatusCountItem {
  key: string;
  label: string;
  value: string;
  tone?: string;
  trend: ChartData[];
}

/** 进程态小计数：整数 + 个 + 语义色，可选极短 sparkline，不得做成与 CPU 同尺寸数字墙。 */
export default function StatusCountRow({ items }: { items: StatusCountItem[] }) {
  return (
    <div className={styles.statusRow}>
      {items.map((item) => (
        <div key={item.key} className={`${classic.panel} ${styles.statusCap}`}>
          <div className={styles.statusCapLabel}>{item.label}</div>
          <div className={styles.statusCapValue} style={{ color: item.tone || undefined }}>
            {item.value}
          </div>
          <Spark data={item.trend} color={item.tone || 'var(--color-text-3)'} className={styles.statusSpark} />
        </div>
      ))}
    </div>
  );
}
