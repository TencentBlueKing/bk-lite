'use client';

import React from 'react';
import { seriesFoldOutline, type CardAlertFold } from './card-alert-fold';
import styles from './layered.module.scss';
import type { TabAlertLevel } from './tab-level';

export { seriesFoldOutline, type CardAlertFold } from './card-alert-fold';

export const cardAlertClass = (level: TabAlertLevel | undefined) => {
  if (!level || level === 'none') return '';
  return styles.cardAlert;
};

/** 卡级气味是右上折角。无达档不渲染，也不加边框。页签圆点不走这里。 */
export function CardAlertDot({
  level,
  fold
}: {
  level: TabAlertLevel | undefined;
  /** @deprecated 勿再用于控制折角。主值色只染数字。 */
  valueColor?: string;
  /** 默认实心。主机 load1 等同色糊字时才传 outline。 */
  fold?: CardAlertFold;
}) {
  if (!level || level === 'none') return null;
  const outline = seriesFoldOutline(fold);
  const tone = level === 'critical' ? styles.cardAlertFoldCritical : styles.cardAlertFoldWarn;
  return (
    <span
      className={`${styles.cardAlertFold} ${tone}${outline ? ` ${styles.cardAlertFoldOutline}` : ''}`}
      role="img"
      aria-label={level === 'critical' ? '警告' : '提醒'}
    />
  );
}
