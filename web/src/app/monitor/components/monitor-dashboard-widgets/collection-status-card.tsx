'use client';

import React from 'react';
import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import type { CollectionStatusResult } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import { COLLECTION_STATUS_LEGEND } from '@/app/monitor/components/monitor-dashboard-widgets/runtime';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/app/monitor/components/monitor-dashboard-widgets/guide-tooltip';

export type CollectionStatusTone = 'success' | 'warning' | 'error' | 'empty';

export interface CollectionStatusTimelineSegment {
  tone: CollectionStatusTone;
  startMs?: number;
  endMs?: number;
}

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
  collectionStatusTimelineHint?: string;
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
  timeline: CollectionStatusTimelineSegment[];
  timelineHint?: string;
  title?: React.ReactNode;
  timelineTitle?: React.ReactNode;
  statusTone?: CollectionStatusTone;
  guideItems?: Array<{ label: string; detail: string }>;
  legendItems?: CollectionStatusLegendItem[];
  emptyTimelineText?: React.ReactNode;
  className?: string;
  styles: CollectionStatusCardStyles;
}

const TONE_LABEL: Record<CollectionStatusTone, string> = {
  success: '正常',
  warning: '警告',
  error: '异常',
  empty: '无数据',
};

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

const formatSegmentTooltip = (segment: CollectionStatusTimelineSegment): string => {
  const label = TONE_LABEL[segment.tone];
  if (
    Number.isFinite(segment.startMs) &&
    Number.isFinite(segment.endMs) &&
    typeof segment.startMs === 'number' &&
    typeof segment.endMs === 'number'
  ) {
    const start = dayjs(segment.startMs).format('HH:mm:ss');
    const end = dayjs(segment.endMs).format('HH:mm:ss');
    return `${start} – ${end}\n${label}`;
  }
  return label;
};

const resolveSegmentClass = (
  tone: CollectionStatusTone,
  styles: CollectionStatusCardStyles
): string => {
  const suffix =
    tone === 'success'
      ? 'Success'
      : tone === 'warning'
        ? 'Warning'
        : tone === 'error'
          ? 'Error'
          : 'Empty';
  return `${styles.collectionStatusSegment} ${styles[`collectionStatusSegment${suffix}` as keyof CollectionStatusCardStyles] || ''}`;
};

export const CollectionStatusCard = ({
  status,
  timeline,
  timelineHint,
  title = '采集状态',
  timelineTitle = '状态时间线',
  statusTone,
  guideItems = [
    { label: '采集状态', detail: '展示当前选中时间窗内该实例监控采集是否正常、缺失或异常。' },
    {
      label: '状态时间线',
      detail: '时间线覆盖当前时间窗并均分为若干段；绿色表示该段有采集，灰色表示该段无数据，红色表示采集或查询异常。',
    },
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
        <div className={styles.collectionStatusTimelineTitle}>
          <span>{timelineTitle}</span>
          {timelineHint ? (
            <span className={styles.collectionStatusTimelineHint}>{timelineHint}</span>
          ) : null}
        </div>
        <div className={styles.collectionStatusTimelineBlock}>
          {timeline.length > 0 ? (
            <>
              <div className={styles.collectionStatusTimeline}>
                {timeline.map((segment, index) => (
                  <Tooltip
                    key={`${segment.tone}-${segment.startMs ?? index}-${index}`}
                    title={
                      <span style={{ whiteSpace: 'pre-line' }}>
                        {formatSegmentTooltip(segment)}
                      </span>
                    }
                  >
                    <span className={resolveSegmentClass(segment.tone, styles)} />
                  </Tooltip>
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
