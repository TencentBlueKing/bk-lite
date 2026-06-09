'use client';

import React from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide } from './guide-tooltip';
import { BarList, BarItem, HorizontalBarPanelStyles } from './horizontal-bar-panel';

export interface GroupedBarColumn {
  key: string;
  title: React.ReactNode;
  subtitle?: string;
  items: BarItem[];
  emphasizeTop?: number;
  tiered?: boolean;
}

export interface GroupedBarPanelStyles extends HorizontalBarPanelStyles {
  groupedColumns?: string;
  groupedColumn?: string;
  groupedColumnTitle?: string;
  groupedColumnLabel?: string;
}

export interface GroupedBarPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  columns: GroupedBarColumn[];
  className?: string;
  styles: GroupedBarPanelStyles;
}

/**
 * 一张大卡片内并排多列排行榜(每列一个 BarList),用于把同一维度的多个 Top 榜
 * (如 Pod 的 CPU / 内存 / 重启)归并成一张卡,而非散成多张同级卡片。
 */
export const GroupedBarPanel = ({
  title,
  subtitle,
  guide,
  columns,
  className,
  styles
}: GroupedBarPanelProps) => {
  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <div className={styles.panelHeader}>
        <div className={styles.panelHeading}>
          <h3 className={styles.panelTitle}>
            {guide ? (
              <TitleWithGuide title={title} items={guide} className={styles.panelTitleWithGuide} styles={styles} />
            ) : (
              title
            )}
          </h3>
          {subtitle ? <div className={styles.panelSubTitle}>{subtitle}</div> : null}
        </div>
      </div>
      <div
        className={styles.groupedColumns}
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
      >
        {columns.map((col) => (
          <div key={col.key} className={styles.groupedColumn}>
            <div className={styles.groupedColumnTitle}>
              <span className={styles.groupedColumnLabel}>{col.title}</span>
              {col.subtitle ? <span className={styles.panelSubTitle}>{col.subtitle}</span> : null}
            </div>
            <BarList items={col.items} emphasizeTop={col.emphasizeTop} tiered={col.tiered} styles={styles} />
          </div>
        ))}
      </div>
    </div>
  );
};
