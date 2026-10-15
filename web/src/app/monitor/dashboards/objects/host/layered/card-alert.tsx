'use client';

import React from 'react';
import styles from './layered.module.scss';
import type { TabAlertLevel } from './tab-level';

export const cardAlertClass = (level: TabAlertLevel | undefined) => {
  if (!level || level === 'none') return '';
  return styles.cardAlert;
};

/** 卡级气味是右上折角。无达档不渲染，也不加边框。页签圆点不走这里。 */
export function CardAlertDot({ level }: { level: TabAlertLevel | undefined }) {
  if (!level || level === 'none') return null;
  return (
    <span
      className={`${styles.cardAlertFold} ${level === 'critical' ? styles.cardAlertFoldCritical : styles.cardAlertFoldWarn}`}
      role="img"
      aria-label={level === 'critical' ? '警告' : '提醒'}
    />
  );
}
