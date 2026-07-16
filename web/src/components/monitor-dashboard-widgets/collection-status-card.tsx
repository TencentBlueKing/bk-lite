'use client';

import React from 'react';
import type { CollectionStatusResult } from '@/components/monitor-dashboard-widgets/types';
import { COLLECTION_STATUS_LEGEND } from '@/components/monitor-dashboard-widgets/runtime';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/components/monitor-dashboard-widgets/guide-tooltip';

export type CollectionStatusTone = 'success' | 'warning' | 'error' | 'empty';

export interface CollectionStatusLegendItem {
  key: CollectionStatusTone;
  label: string;
  color: string;
}

export interface CollectionStatusCardStyles extends GuideTooltipStyles {
  statCard?: string;
  collectionStatusCard?: string;
  collectionStatusHeader?: string;
  statLabel?: string;
  statTitleWithGuide?: string;
  collectionStatusBody?: string;
  collectionStatusValue?: string;
  collectionStatusValueSuccess?: string;
  collectionStatusValueWarning?: string;
  collectionStatusValueError?: string;
  collectionStatusValueEmpty?: string;
  collectionStatusTimelineBlock?: string;
  collectionStatusTimelineTitle?: string;
  collectionStatusTimeline?: string;
  collectionStatusSegment?: string;
  collectionStatusSegmentSuccess?: string;
  collectionStatusSegmentWarning?: string;
  collectionStatusSegmentError?: string;
  collectionStatusSegmentEmpty?: string;
  collectionStatusTimelineEmpty?: string;
  collectionStatusLegend?: string;
  collectionStatusLegendItem?: string;
  collectionStatusLegendDot?: string;
}

export interface CollectionStatusCardProps {
  status: CollectionStatusResult;
  timeline: CollectionStatusTone[];
  title?: React.ReactNode;
  timelineTitle?: React.ReactNode;
  statusTone?: CollectionStatusTone;
  guideItems?: Array<{ label: string; detail: string }>;
  legendItems?: CollectionStatusLegendItem[];
  emptyTimelineText?: React.ReactNode;
  className?: string;
  styles: CollectionStatusCardStyles;
}

const getStatusTone = (
  status: CollectionStatusResult,
  statusTone?: CollectionStatusTone
): CollectionStatusTone => {
  if (statusTone) return statusTone;
  if (status.tagColor === 'success') return 'success';
  if (status.tagColor === 'warning') return 'warning';
  if (status.tagColor === 'error') return 'error';
  if (status.label === '正常') return 'success';
  if (status.label === '异常') return 'error';
  return 'empty';
};

export const CollectionStatusCard = ({
  status,
  timeline,
  title = '采集状态',
  timelineTitle = '状态时间线',
  statusTone,
  guideItems = [
    { label: '采集状态', detail: '展示最近一段时间内该实例监控采集是否正常、缺失或异常。' },
    { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' },
  ],
  legendItems = COLLECTION_STATUS_LEGEND,
  emptyTimelineText,
  className,
  styles,
}: CollectionStatusCardProps) => {
  const resolvedStatusTone = getStatusTone(status, statusTone);

  return (
    <div
      className={[styles.statCard, styles.collectionStatusCard, className]
        .filter(Boolean)
        .join(' ')}
    >
      <div className={styles.collectionStatusHeader}>
        <div className={styles.statLabel}>
          <TitleWithGuide
            title={title}
            items={guideItems}
            className={styles.statTitleWithGuide}
            styles={styles}
          />
        </div>
      </div>
      <div className={styles.collectionStatusBody}>
        <div
          className={`${styles.collectionStatusValue} ${
            styles[
              `collectionStatusValue${
                resolvedStatusTone === 'success'
                  ? 'Success'
                  : resolvedStatusTone === 'warning'
                    ? 'Warning'
                    : resolvedStatusTone === 'error'
                      ? 'Error'
                      : 'Empty'
              }`
            ]
          }`}
        >
          {status.label}
        </div>
        <div className={styles.collectionStatusTimelineTitle}>{timelineTitle}</div>
        <div className={styles.collectionStatusTimelineBlock}>
          {timeline.length > 0 ? (
            <>
              <div className={styles.collectionStatusTimeline}>
                {timeline.map((tone, index) => (
                  <span
                    key={`${tone}-${index}`}
                    className={`${styles.collectionStatusSegment} ${
                      styles[
                        `collectionStatusSegment${
                          tone === 'success'
                            ? 'Success'
                            : tone === 'warning'
                              ? 'Warning'
                              : tone === 'error'
                                ? 'Error'
                                : 'Empty'
                        }`
                      ]
                    }`}
                  />
                ))}
              </div>
              <div className={styles.collectionStatusLegend}>
                {legendItems.map((item) => (
                  <span key={item.key} className={styles.collectionStatusLegendItem}>
                    <span
                      className={styles.collectionStatusLegendDot}
                      style={{ background: item.color }}
                    />
                    {item.label}
                  </span>
                ))}
              </div>
            </>
          ) : emptyTimelineText ? (
            <div className={styles.collectionStatusTimelineEmpty}>{emptyTimelineText}</div>
          ) : (
            <div className={styles.collectionStatusTimeline} />
          )}
        </div>
      </div>
    </div>
  );
};
