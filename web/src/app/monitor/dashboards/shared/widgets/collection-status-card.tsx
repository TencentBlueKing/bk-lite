'use client';

import React from 'react';
import { CollectionStatusResult } from '../types';
import { COLLECTION_STATUS_LEGEND } from '../utils/constants';
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
  timeline: Array<'success' | 'empty' | 'error'>;
  guideItems?: Array<{ label: string; detail: string }>;
  styles: CollectionStatusCardStyles;
}

export const CollectionStatusCard = ({
  status,
  timeline,
  guideItems = [
    { label: '采集状态', detail: '展示最近一段时间内该实例监控采集是否正常、缺失或异常。' },
    { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' }
  ],
  styles
}: CollectionStatusCardProps) => {
  return (
    <div className={`${styles.statCard} ${styles.collectionStatusCard}`}>
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
        <div className={styles.collectionStatusTimelineTitle}>状态时间线</div>
        <div className={styles.collectionStatusTimelineBlock}>
          <div className={styles.collectionStatusTimeline}>
            {timeline.map((tone, index) => (
              <span key={`${tone}-${index}`} className={`${styles.collectionStatusSegment} ${styles[`collectionStatusSegment${tone === 'success' ? 'Success' : tone === 'error' ? 'Error' : 'Empty'}`]}`} />
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
