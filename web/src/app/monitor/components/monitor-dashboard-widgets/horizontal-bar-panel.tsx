'use client';

import React from 'react';
import type { ChartData, GuideItem } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/app/monitor/components/monitor-dashboard-widgets/guide-tooltip';
import { MiniTrendChart } from '@/app/monitor/components/monitor-dashboard-widgets/mini-trend-chart';
import ChartEmptyState from '@/components/chart-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

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
  trend?: ChartData[];
  rank?: number;
}

export interface HorizontalBarPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: BarItem[];
  className?: string;
  emphasizeTop?: number;
  tiered?: boolean;
  isEmpty?: boolean;
  emptyDescription?: React.ReactNode;
  styles: HorizontalBarPanelStyles;
}

export interface BarListProps {
  items: BarItem[];
  emphasizeTop?: number;
  tiered?: boolean;
  styles: HorizontalBarPanelStyles;
}

export const BarList = ({ items, emphasizeTop = 0, tiered = false, styles }: BarListProps) => {
  const isTrendPanel = items.some((item) => item.trend && item.trend.length > 0);
  return (
    <div
      className={`${styles.bars} ${styles.compactBars} ${styles.barsFull} ${
        isTrendPanel ? styles.barsTrend || '' : ''
      }`}
    >
      {items.map((item, idx) => {
        const rank = item.rank;
        const isRanked = typeof rank === 'number';
        let rowClass = '';
        let badgeSize = 24;
        let badgeFont = 14;
        if (tiered && isRanked) {
          if (rank! <= 3) {
            rowClass = styles.barRowEmphasis || '';
            badgeSize = 28;
            badgeFont = 16;
          } else {
            rowClass = styles.barRowMuted || '';
            badgeSize = 22;
            badgeFont = 13;
          }
        } else if (emphasizeTop > 0 && isRanked && rank! <= emphasizeTop) {
          rowClass = styles.barRowEmphasis || '';
          badgeSize = 28;
          badgeFont = 16;
        }

        return (
          <div
            key={`${idx}-${item.label}`}
            className={[styles.barRow, rowClass].filter(Boolean).join(' ')}
          >
            <div
              className={styles.barLabel}
              style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}
            >
              {isRanked ? (
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
                    background: rank! <= 3 ? RANK_TOP3[rank! - 1] : '#475569',
                    color: '#fff',
                  }}
                >
                  {rank}
                </span>
              ) : null}
              <EllipsisWithTooltip
                text={item.label}
                disclosure="interactive"
                className="min-w-0 flex-1 cursor-default overflow-hidden text-ellipsis whitespace-nowrap"
              />
            </div>
            {item.trend && item.trend.length > 0 ? (
              <div className={styles.barSpark}>
                <MiniTrendChart data={item.trend} color={item.color} styles={styles} />
              </div>
            ) : (
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{
                    width: `${Math.min((item.value / item.max) * 100, 100)}%`,
                    background: item.color,
                  }}
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
  isEmpty = false,
  emptyDescription,
  styles,
}: HorizontalBarPanelProps) => {
  const { t } = useTranslation();

  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <div className={styles.panelHeader}>
        <div className={styles.panelHeading}>
          <h3 className={styles.panelTitle}>
            {guide ? (
              <TitleWithGuide
                title={title}
                items={guide}
                className={styles.panelTitleWithGuide}
                styles={styles}
              />
            ) : (
              title
            )}
          </h3>
          {subtitle ? <div className={styles.panelSubTitle}>{subtitle}</div> : null}
        </div>
      </div>
      {isEmpty ? (
        <div className="flex min-h-[176px] items-center justify-center">
          <ChartEmptyState
            description={emptyDescription === undefined ? t('common.noData') : emptyDescription}
            compact
          />
        </div>
      ) : (
        <BarList items={items} emphasizeTop={emphasizeTop} tiered={tiered} styles={styles} />
      )}
    </div>
  );
};
