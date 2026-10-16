'use client';

import React from 'react';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../config';
import styles from './layered.module.scss';
import type { TabAlertLevel } from './tab-level';

export const cardAlertClass = (level: TabAlertLevel | undefined) => {
  if (!level || level === 'none') return '';
  return styles.cardAlert;
};

const sameHex = (left?: string, right?: string) => (
  Boolean(left && right && left.trim().toLowerCase() === right.trim().toLowerCase())
);

/** 主值已经是同色时改描边：警告叠 load1 橙，严重叠阈值红。页签圆点不走这里。 */
export const seriesFoldOutline = (level: TabAlertLevel | undefined, valueColor?: string) => {
  if (level === 'warn') return sameHex(valueColor, HOST_SERIES_COLOR.load1);
  if (level === 'critical') return sameHex(valueColor, HOST_THRESHOLD_COLOR.crit);
  return false;
};

/** 卡级气味是右上折角。无达档不渲染，也不加边框。页签圆点不走这里。 */
export function CardAlertDot({
  level,
  valueColor
}: {
  level: TabAlertLevel | undefined;
  /** 主值色。与折角同色时改描边，避免橙字叠橙折角、红字叠红折角。 */
  valueColor?: string;
}) {
  if (!level || level === 'none') return null;
  const outline = seriesFoldOutline(level, valueColor);
  const tone = level === 'critical' ? styles.cardAlertFoldCritical : styles.cardAlertFoldWarn;
  return (
    <span
      className={`${styles.cardAlertFold} ${tone}${outline ? ` ${styles.cardAlertFoldOutline}` : ''}`}
      role="img"
      aria-label={level === 'critical' ? '警告' : '提醒'}
    />
  );
}
