'use client';

import React from 'react';
import { RiseOutlined, FallOutlined } from '@ant-design/icons';
import { ChartData } from '@/app/monitor/types';
import { CompareFavorableDirection, PeriodCompare } from '../types';
import { getCompareTone } from '../utils/format';
import { MiniTrendChart, MiniTrendChartStyles } from './mini-trend-chart';

export interface StatCardStyles extends MiniTrendChartStyles {
  statCard?: string;
  statHeader?: string;
  statLabel?: string;
  statIcon?: string;
  statBody?: string;
  statValue?: string;
  statUnit?: string;
  statCompare?: string;
  statCompareFlat?: string;
  statComparePositive?: string;
  statCompareNegative?: string;
  statCompareLabel?: string;
  statCompareValue?: string;
  statMeta?: string;
  statExtra?: string;
  miniTrend?: string;
}

export interface StatCardProps {
  title: React.ReactNode;
  value: React.ReactNode;
  unit: string;
  icon: React.ReactNode;
  iconStyle?: React.CSSProperties;
  color: string;
  footer: React.ReactNode;
  compare?: PeriodCompare | null;
  compareFavorableDirection?: CompareFavorableDirection;
  trendData?: ChartData[];
  hideTrend?: boolean;
  noDataType?: 'empty' | 'error';
  className?: string;
  bodyClassName?: string;
  extra?: React.ReactNode;
  styles: StatCardStyles;
}

export const StatCard = ({
  title,
  value,
  unit,
  icon,
  iconStyle,
  color,
  footer,
  compare,
  compareFavorableDirection = 'down',
  trendData = [],
  hideTrend = false,
  noDataType = 'empty',
  className,
  bodyClassName,
  extra,
  styles
}: StatCardProps) => {
  const compareTone = compare ? getCompareTone(compare.direction, compareFavorableDirection) : 'flat';

  return (
    <div className={`${styles.statCard} ${className || ''}`}>
      <div className={styles.statHeader}>
        <div className={styles.statLabel}>{title}</div>
        <div className={styles.statIcon} style={iconStyle}>
          {icon}
        </div>
      </div>
      <div className={`${styles.statBody} ${bodyClassName || ''}`}>
        <div className={styles.statValue} style={{ color }}>
          {value}
          {unit ? <span className={styles.statUnit}>{unit}</span> : null}
        </div>
        {compare ? (
          <div className={`${styles.statCompare} ${styles[`statCompare${compareTone === 'flat' ? 'Flat' : compareTone === 'positive' ? 'Positive' : 'Negative'}`]}`}>
            <span className={styles.statCompareLabel}>较上一周期</span>
            <span className={styles.statCompareValue}>
              {compare.direction === 'up' ? <RiseOutlined /> : compare.direction === 'down' ? <FallOutlined /> : null}
              {compare.value}
            </span>
          </div>
        ) : null}
        <div className={styles.statMeta}>{footer}</div>
      </div>
      {extra ? <div className={styles.statExtra}>{extra}</div> : null}
      {!hideTrend ? (
        <div className={styles.miniTrend} style={{ flexShrink: 0 }}>
          <MiniTrendChart data={noDataType === 'error' ? [] : trendData} color={color} styles={styles} />
        </div>
      ) : null}
    </div>
  );
};
