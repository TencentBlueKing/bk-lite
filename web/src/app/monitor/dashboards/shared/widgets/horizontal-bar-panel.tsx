'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { GuideItem } from '../types';
import { ChartData } from '@/app/monitor/types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';
import { MiniTrendChart } from './mini-trend-chart';

const RANK_TOP3 = ['#f5a623', '#9aa7bd', '#cd7f32'];

export interface HorizontalBarPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  bars?: string;
  compactBars?: string;
  barsFull?: string;
  barsTrend?: string;
  barRow?: string;
  barRowEmphasis?: string;
  barRowHero?: string;
  barRowMuted?: string;
  barLabel?: string;
  barTrack?: string;
  barFill?: string;
  barSpark?: string;
  barValue?: string;
  miniTrendPlaceholder?: string;
}

export interface BarItem {
  label: string;
  value: number;
  display: string;
  color: string;
  max: number;
  /** 提供时间序列则渲染 sparkline 趋势(替代静态进度条);不提供则保留进度条。 */
  trend?: ChartData[];
  /** 排行序号;提供时标签前渲染独立徽章(前三名暖色)。 */
  rank?: number;
}

export interface HorizontalBarPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: BarItem[];
  className?: string;
  /** 排行榜前 N 名做放大强调(更大字号/更高条/更大徽章)。需要 item.rank。默认 0=不强调。 */
  emphasizeTop?: number;
  /** 分档模式:第 1 名醒目大行、2-3 名强调、≥4 名弱化。开启后忽略 emphasizeTop。需 item.rank。 */
  tiered?: boolean;
  styles: HorizontalBarPanelStyles;
}

export interface BarListProps {
  items: BarItem[];
  emphasizeTop?: number;
  /** 分档模式:第 1 名醒目大行、2-3 名强调、≥4 名弱化。开启后忽略 emphasizeTop。需 item.rank。 */
  tiered?: boolean;
  styles: HorizontalBarPanelStyles;
}

/** 仅条形列表(不含卡片外框/标题),供 HorizontalBarPanel 与 GroupedBarPanel 复用。 */
export const BarList = ({ items, emphasizeTop = 0, tiered = false, styles }: BarListProps) => {
  // 趋势(sparkline)列表让缩略图横向撑满;进度条(分布/对比)列表保持固定窄列。
  const isTrendPanel = items.some((item) => item.trend && item.trend.length > 0);
  return (
    <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull} ${isTrendPanel ? styles.barsTrend || '' : ''}`}>
      {items.map((item) => {
        const rank = item.rank;
        let rowClass = '';
        let badgeSize = 24;
        let badgeFont = 14;
        if (tiered && typeof rank === 'number') {
          if (rank <= 3) { rowClass = styles.barRowEmphasis || ''; badgeSize = 28; badgeFont = 16; }
          else { rowClass = styles.barRowMuted || ''; badgeSize = 22; badgeFont = 13; }
        } else if (emphasizeTop > 0 && typeof rank === 'number' && rank <= emphasizeTop) {
          rowClass = styles.barRowEmphasis || ''; badgeSize = 28; badgeFont = 16;
        }
        return (
          <div
            key={item.label}
            className={[styles.barRow, rowClass].filter(Boolean).join(' ')}
          >
            <div className={styles.barLabel} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              {typeof rank === 'number' ? (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: badgeSize,
                    height: badgeSize,
                    padding: '0 6px',
                    borderRadius: 7,
                    flexShrink: 0,
                    fontSize: badgeFont,
                    fontWeight: 800,
                    fontVariantNumeric: 'tabular-nums',
                    background: rank <= 3 ? RANK_TOP3[rank - 1] : '#475569',
                    color: '#fff'
                  }}
                >
                  {rank}
                </span>
              ) : null}
              <Tooltip title={item.label} mouseEnterDelay={0.2}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'default' }}>{item.label}</span>
              </Tooltip>
            </div>
            {item.trend && item.trend.length > 0 ? (
              <div className={styles.barSpark}>
                <MiniTrendChart data={item.trend} color={item.color} styles={styles} />
              </div>
            ) : (
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{ width: `${Math.min((item.value / item.max) * 100, 100)}%`, background: item.color }}
                />
              </div>
            )}
            <div className={styles.barValue}>{item.display}</div>
          </div>
        );
      })}
    </div>
  );
};

export const HorizontalBarPanel = ({
  title,
  subtitle,
  guide,
  items,
  className,
  emphasizeTop = 0,
  tiered = false,
  styles
}: HorizontalBarPanelProps) => {
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
      <BarList items={items} emphasizeTop={emphasizeTop} tiered={tiered} styles={styles} />
    </div>
  );
};
