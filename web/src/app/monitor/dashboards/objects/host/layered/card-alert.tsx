'use client';

import React from 'react';
import styles from './layered.module.scss';
import type { TabAlertLevel } from './tab-level';

export const cardAlertClass = (level: TabAlertLevel | undefined) => {
  if (!level || level === 'none') return '';
  return `${styles.cardAlert} ${level === 'critical' ? styles.cardAlertCritical : styles.cardAlertWarn}`;
};

/** 与页签达档点同尺寸同色。无达档不渲染。 */
export function CardAlertDot({ level }: { level: TabAlertLevel | undefined }) {
  if (!level || level === 'none') return null;
  return (
    <span
      className={`${styles.tabLevelDot} ${styles.cardAlertDot} ${level === 'critical' ? styles.tabLevelCritical : styles.tabLevelWarn}`}
      role="img"
      aria-label={level === 'critical' ? '警告' : '提醒'}
    />
  );
}
