'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { ApiOutlined } from '@ant-design/icons';
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
  statHeader?: string;
  statLabel?: string;
  statTitleWithGuide?: string;
  statIcon?: string;
  collectionStatusHeaderIcon?: string;
  collectionStatusHeaderIconSuccess?: string;
  collectionStatusHeaderIconWarning?: string;
  collectionStatusHeaderIconError?: string;
  collectionStatusHeaderIconEmpty?: string;
  collectionStatusPulseDot?: string;
  collectionStatusBody?: string;
  collectionStatusValue?: string;
  collectionStatusValueSuccess?: string;
  collectionStatusValueWarning?: string;
  collectionStatusValueError?: string;
  collectionStatusValueEmpty?: string;
  collectionStatusHeadlineRow?: string;
  collectionStatusPill?: string;
  collectionStatusPillDot?: string;
  collectionStatusPillText?: string;
  collectionStatusPillSuccess?: string;
  collectionStatusPillWarning?: string;
  collectionStatusPillError?: string;
  collectionStatusPillEmpty?: string;
  collectionStatusAvailability?: string;
  collectionStatusAvailabilityVal?: string;
  collectionStatusAvailabilityLabel?: string;
  collectionStatusSubMeta?: string;
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
  collectionStatusTimelineFooter?: string;
  collectionStatusTimelineScaleRow?: string;
  collectionStatusTimelineScale?: string;
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

const resolveToneSuffix = (tone: CollectionStatusTone): string => {
  if (tone === 'success') return 'Success';
  if (tone === 'warning') return 'Warning';
  if (tone === 'error') return 'Error';
  return 'Empty';
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
  const suffix = resolveToneSuffix(tone);
  return `${styles.collectionStatusSegment || ''} ${styles[`collectionStatusSegment${suffix}` as keyof CollectionStatusCardStyles] || ''}`.trim();
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
  emptyTimelineText = '暂无状态时间线数据',
  className,
  styles,
}: CollectionStatusCardProps) => {
  const resolvedStatusTone = getStatusTone(status, statusTone);
  const toneSuffix = resolveToneSuffix(resolvedStatusTone);

  const scaleRange = React.useMemo(() => {
    if (timeline.length < 2) return null;
    const first = timeline[0];
    const last = timeline[timeline.length - 1];
    if (!Number.isFinite(first?.startMs) || !Number.isFinite(last?.endMs)) return null;

    const startText = dayjs(first.startMs).format('HH:mm');
    const now = Date.now();
    const isNearNow = Math.abs(now - last.endMs) < 120_000;
    const endText = isNearNow ? '刚刚' : dayjs(last.endMs).format('HH:mm');

    return { startText, endText };
  }, [timeline]);

  const headerClass = styles.collectionStatusHeader || styles.statHeader;

  return (
    <div
      className={[styles.statCard, styles.collectionStatusCard, className]
        .filter(Boolean)
        .join(' ')}
    >
      <div className={headerClass}>
        <div className={styles.statLabel}>
          <TitleWithGuide
            title={title}
            items={guideItems}
            className={styles.statTitleWithGuide}
            styles={styles}
          />
        </div>
        <div
          className={[
            styles.statIcon,
            styles.collectionStatusHeaderIcon,
            styles[`collectionStatusHeaderIcon${toneSuffix}` as keyof CollectionStatusCardStyles],
            'relative flex items-center justify-center shrink-0 w-[30px] h-[30px] rounded-[8px]'
          ].filter(Boolean).join(' ')}
          aria-hidden="true"
        >
          <span
            className={[
              styles.collectionStatusPulseDot,
              'absolute top-1 right-1 w-1.5 h-1.5 rounded-full'
            ].filter(Boolean).join(' ')}
          />
          <ApiOutlined className="text-[14px]" />
        </div>
      </div>

      <div className={[styles.collectionStatusBody, 'flex flex-col flex-1 min-h-0'].filter(Boolean).join(' ')}>
        <div className={[styles.collectionStatusHeadlineRow, 'flex items-center gap-2 flex-wrap min-h-[28px]'].filter(Boolean).join(' ')}>
          <div
            className={[
              styles.collectionStatusPill,
              styles[`collectionStatusPill${toneSuffix}` as keyof CollectionStatusCardStyles],
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[13px] font-semibold border transition-all'
            ].filter(Boolean).join(' ')}
          >
            <span
              className={[
                styles.collectionStatusPillDot,
                'w-[7px] h-[7px] rounded-full shrink-0'
              ].filter(Boolean).join(' ')}
            />
            <span className={styles.collectionStatusPillText}>{status.label}</span>
          </div>
        </div>

        <div className={[styles.collectionStatusTimelineBlock, 'mt-auto flex flex-col gap-1.5 pt-1.5'].filter(Boolean).join(' ')}>
          <div className={[styles.collectionStatusTimelineTitle, 'flex items-center justify-between gap-2 text-[11px] font-medium text-[var(--color-text-3)]'].filter(Boolean).join(' ')}>
            <span>{timelineTitle}</span>
            {timelineHint ? (
              <span className={[styles.collectionStatusTimelineHint, 'shrink-0 text-[11px] text-[var(--color-text-4)]'].filter(Boolean).join(' ')}>
                {timelineHint}
              </span>
            ) : null}
          </div>

          {timeline.length > 0 ? (
            <>
              <div className={[styles.collectionStatusTimeline, 'grid grid-cols-[repeat(18,minmax(0,1fr))] gap-[3px] items-center py-0.5'].filter(Boolean).join(' ')}>
                {timeline.map((segment, index) => (
                  <Tooltip
                    key={`${segment.tone}-${segment.startMs ?? index}-${index}`}
                    title={
                      <span style={{ whiteSpace: 'pre-line' }}>
                        {formatSegmentTooltip(segment)}
                      </span>
                    }
                  >
                    <span
                      className={[
                        resolveSegmentClass(segment.tone, styles),
                        'block w-full h-2 rounded-[4px] cursor-pointer transition-transform hover:scale-y-125'
                      ].filter(Boolean).join(' ')}
                    />
                  </Tooltip>
                ))}
              </div>

              <div className={[styles.collectionStatusTimelineFooter, 'flex flex-col gap-1.5 pt-0.5 text-[11px] text-[var(--color-text-4)] leading-none'].filter(Boolean).join(' ')}>
                <div className={[styles.collectionStatusTimelineScaleRow, 'flex items-center justify-between gap-2 min-w-0'].filter(Boolean).join(' ')}>
                  <span className={[styles.collectionStatusTimelineScale, 'tabular-nums whitespace-nowrap text-[11px] text-[var(--color-text-4)]'].filter(Boolean).join(' ')}>
                    {scaleRange?.startText || ''}
                  </span>
                  <span className={[styles.collectionStatusTimelineScale, 'tabular-nums whitespace-nowrap text-[11px] text-[var(--color-text-4)]'].filter(Boolean).join(' ')}>
                    {scaleRange?.endText || ''}
                  </span>
                </div>
                <div className={[styles.collectionStatusLegend, 'flex items-center gap-2 whitespace-nowrap text-[11px] text-[var(--color-text-3)]'].filter(Boolean).join(' ')}>
                  {legendItems.map((item) => (
                    <span key={item.key} className={[styles.collectionStatusLegendItem, 'inline-flex items-center gap-1 text-[11px]'].filter(Boolean).join(' ')}>
                      <span
                        className={[styles.collectionStatusLegendDot, 'w-1.5 h-1.5 rounded-full shrink-0'].filter(Boolean).join(' ')}
                        style={{ background: item.color }}
                      />
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
            </>
          ) : emptyTimelineText ? (
            <div className={[styles.collectionStatusTimelineEmpty, 'py-2 text-center text-[12px] text-[var(--color-text-3)]'].filter(Boolean).join(' ')}>
              {emptyTimelineText}
            </div>
          ) : (
            <div className={styles.collectionStatusTimeline} />
          )}
        </div>
      </div>
    </div>
  );
};
