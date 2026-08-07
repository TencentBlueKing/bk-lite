'use client';

import React from 'react';
import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import { CollectionStatusResult } from '../types';
import { COLLECTION_STATUS_LEGEND } from '../utils/constants';
import {
  CollectionStatusTimelineSegment,
  getCollectionStatusToneLabel
} from '../utils/collection-status';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export interface CollectionStatusCardStyles extends GuideTooltipStyles {
  statCard?: string;
  collectionStatusCard?: string;
  collectionStatusHeader?: string;
  statLabel?: string;
  statTitleWithGuide?: string;
  collectionStatusBody?: string;
  collectionStatusValue?: string;
  collectionStatusValueSuccess?: string;
  collectionStatusValueError?: string;
  collectionStatusValueEmpty?: string;
  collectionStatusTimelineBlock?: string;
  collectionStatusTimelineTitle?: string;
  collectionStatusTimelineHint?: string;
  collectionStatusTimeline?: string;
  collectionStatusSegment?: string;
  collectionStatusSegmentSuccess?: string;
  collectionStatusSegmentError?: string;
  collectionStatusSegmentEmpty?: string;
  collectionStatusLegend?: string;
  collectionStatusLegendItem?: string;
  collectionStatusLegendDot?: string;
}

export interface CollectionStatusCardProps {
  status: CollectionStatusResult;
  timeline: CollectionStatusTimelineSegment[];
  /** 例如「每格约 50 秒」 */
  timelineHint?: string;
  guideItems?: Array<{ label: string; detail: string }>;
  /** 作为 grid 子项时传入 span* 等栅格类,使其与相邻 StatCard 等高/等宽对齐。 */
  className?: string;
  styles: CollectionStatusCardStyles;
}

const DEFAULT_GUIDE_ITEMS = [
  { label: '采集状态', detail: '展示当前选中时间窗内该实例监控采集是否正常、缺失或异常。' },
  {
    label: '状态时间线',
    detail: '时间线覆盖当前时间窗并均分为 18 段；绿色表示该段有采集，灰色表示该段无数据，红色表示采集或查询异常。'
  }
];

const formatSegmentTooltip = (segment: CollectionStatusTimelineSegment): string => {
  const start = dayjs(segment.startMs).format('HH:mm:ss');
  const end = dayjs(segment.endMs).format('HH:mm:ss');
  return `${start} – ${end}\n${getCollectionStatusToneLabel(segment.tone)}`;
};

export const CollectionStatusCard = ({
  status,
  timeline,
  timelineHint,
  guideItems = DEFAULT_GUIDE_ITEMS,
  className,
  styles
}: CollectionStatusCardProps) => {
  return (
    <div className={[styles.statCard, styles.collectionStatusCard, className].filter(Boolean).join(' ')}>
      <div className={styles.collectionStatusHeader}>
        <div className={styles.statLabel}>
          <TitleWithGuide
            title="采集状态"
            items={guideItems}
            className={styles.statTitleWithGuide}
            styles={styles}
          />
        </div>
      </div>
      <div className={styles.collectionStatusBody}>
        <div className={`${styles.collectionStatusValue} ${styles[`collectionStatusValue${status.label === '正常' ? 'Success' : status.label === '异常' ? 'Error' : 'Empty'}`]}`}>
          {status.label}
        </div>
        <div className={styles.collectionStatusTimelineTitle}>
          <span>状态时间线</span>
          {timelineHint ? <span className={styles.collectionStatusTimelineHint}>{timelineHint}</span> : null}
        </div>
        <div className={styles.collectionStatusTimelineBlock}>
          <div className={styles.collectionStatusTimeline}>
            {timeline.map((segment, index) => (
              <Tooltip
                key={`${segment.tone}-${segment.startMs}-${index}`}
                title={<span style={{ whiteSpace: 'pre-line' }}>{formatSegmentTooltip(segment)}</span>}
              >
                <span
                  className={`${styles.collectionStatusSegment} ${styles[`collectionStatusSegment${segment.tone === 'success' ? 'Success' : segment.tone === 'error' ? 'Error' : 'Empty'}`]}`}
                />
              </Tooltip>
            ))}
          </div>
          <div className={styles.collectionStatusLegend}>
            {COLLECTION_STATUS_LEGEND.map((item) => (
              <span key={item.key} className={styles.collectionStatusLegendItem}>
                <span className={styles.collectionStatusLegendDot} style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
