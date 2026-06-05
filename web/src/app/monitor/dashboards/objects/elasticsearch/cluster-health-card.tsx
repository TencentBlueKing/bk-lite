'use client';

import React, { useMemo } from 'react';
import { TitleWithGuide } from '../../shared/widgets';
import { PreparedSummaryCard } from '../common/simple-dashboard-core';
import { ChartData } from '@/app/monitor/types';

const HEALTH_COLORS = {
  normal: '#27c274',
  warning: '#ff8a1f',
  critical: '#ff4d4f',
  unknown: '#d7dfeb'
} as const;

const HEALTH_LEGEND = [
  { key: 'normal', label: '正常', color: HEALTH_COLORS.normal },
  { key: 'warning', label: '警告', color: HEALTH_COLORS.warning },
  { key: 'critical', label: '严重', color: HEALTH_COLORS.critical }
] as const;

const getHealthTone = (value: number | undefined): keyof typeof HEALTH_COLORS => {
  if (value === undefined || !Number.isFinite(value)) return 'unknown';
  if (value <= 1) return 'normal';
  if (value <= 2) return 'warning';
  return 'critical';
};

export interface ClusterHealthCardProps {
  prepared: PreparedSummaryCard;
  styles: Record<string, string>;
}

/**
 * Replaces the generic StatCard for the 集群健康状态 metric.
 * Renders a colour-coded timeline (green/orange/red blocks) instead of a
 * sparkline, matching the visual language of CollectionStatusCard.
 */
export const ClusterHealthCard = ({ prepared, styles }: ClusterHealthCardProps) => {
  const { mainValue, valueColor, trendData, card } = prepared;
  const mainValueColor =
    mainValue.value === '--' ? HEALTH_COLORS.unknown : valueColor ?? HEALTH_COLORS.normal;

  const timeline = useMemo(() => {
    const data = trendData as ChartData[];
    if (data.length === 0) return [];
    const step = Math.max(1, Math.floor(data.length / 18));
    const sampled: ChartData[] = [];
    for (let i = 0; i < data.length; i += step) {
      sampled.push(data[i]);
      if (sampled.length >= 18) break;
    }
    return sampled.map((d) => getHealthTone(d.value1 as number | undefined));
  }, [trendData]);

  return (
    <div className={`${styles.statCard} ${styles.collectionStatusCard}`}>
      <div className={styles.collectionStatusHeader}>
        <div className={styles.statLabel}>
          <TitleWithGuide title={card.title} items={card.guide} styles={styles} />
        </div>
      </div>
      <div className={styles.collectionStatusBody}>
        <div className={styles.collectionStatusValue} style={{ color: mainValueColor }}>
          {mainValue.value}
        </div>
        <div className={styles.collectionStatusTimelineTitle}>状态时间线</div>
        <div className={styles.collectionStatusTimelineBlock}>
          {timeline.length > 0 ? (
            <div className={styles.collectionStatusTimeline}>
              {timeline.map((tone, index) => (
                <span
                  key={index}
                  className={styles.collectionStatusSegment}
                  style={{
                    background: HEALTH_COLORS[tone],
                    borderColor: tone === 'unknown' ? 'transparent' : undefined
                  }}
                />
              ))}
            </div>
          ) : (
            <div className={styles.collectionStatusTimelineEmpty}>暂无健康时间线数据</div>
          )}
          {timeline.length > 0 ? (
            <div className={styles.collectionStatusLegend}>
              {HEALTH_LEGEND.map((item) => (
                <span key={item.key} className={styles.collectionStatusLegendItem}>
                  <span className={styles.collectionStatusLegendDot} style={{ background: item.color }} />
                  {item.label}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
