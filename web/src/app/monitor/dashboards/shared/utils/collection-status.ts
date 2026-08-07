import { ChartData, TimeValuesProps } from '@/app/monitor/types';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { CollectionStatusResult } from '../types';
import { COLLECTION_STATUS_SEGMENT_COUNT } from './constants';

export type CollectionStatusTone = 'success' | 'empty' | 'error';

export interface CollectionStatusTimelineSegment {
  tone: CollectionStatusTone;
  startMs: number;
  endMs: number;
}

const COLLECTION_STATUS_TONE_LABEL: Record<CollectionStatusTone, string> = {
  success: '正常',
  empty: '无数据',
  error: '异常'
};

/** Prometheus/VM 点时间通常是秒；时间窗用毫秒。 */
const toTimestampMs = (value: number): number => (value < 1e12 ? value * 1000 : value);

export const getCollectionStatusToneLabel = (tone: CollectionStatusTone): string =>
  COLLECTION_STATUS_TONE_LABEL[tone];

export const getLatestCollectionTone = (
  viewData: ChartData[] | undefined
): 'success' | 'empty' | undefined => {
  if (!Array.isArray(viewData) || viewData.length === 0) return undefined;
  const latest = [...viewData]
    .sort((a, b) => Number(a.time) - Number(b.time))
    .at(-1);
  if (!latest) return undefined;
  return Number(latest.value1 ?? 0) > 0 ? 'success' : 'empty';
};

/** @deprecated 仅保留兼容；时间线已改为按时间窗均分桶。 */
export const getCollectionStatusTones = (
  viewData: ChartData[] | undefined,
  segmentCount = COLLECTION_STATUS_SEGMENT_COUNT
): Array<'success' | 'empty'> => {
  if (!Array.isArray(viewData)) return [];
  return [...viewData]
    .sort((a, b) => Number(a.time) - Number(b.time))
    .slice(-segmentCount)
    .map((point) => (Number(point.value1 ?? 0) > 0 ? ('success' as const) : ('empty' as const)));
};

export const buildCollectionStatusTimeline = (
  loadState: string | undefined,
  viewData: ChartData[] | undefined,
  startMs: number,
  endMs: number,
  segmentCount = COLLECTION_STATUS_SEGMENT_COUNT
): CollectionStatusTimelineSegment[] => {
  const safeStart = Number(startMs);
  const safeEnd = Number(endMs);
  const count = Math.max(1, Math.floor(segmentCount));
  const hasValidRange = Number.isFinite(safeStart) && Number.isFinite(safeEnd) && safeEnd > safeStart;
  const resolvedStart = hasValidRange ? safeStart : Date.now() - 15 * 60_000;
  const resolvedEnd = hasValidRange ? safeEnd : Date.now();
  const duration = resolvedEnd - resolvedStart;
  const bucketWidth = duration / count;

  const makeSegment = (index: number, tone: CollectionStatusTone): CollectionStatusTimelineSegment => {
    const bucketStart = resolvedStart + index * bucketWidth;
    const bucketEnd = index === count - 1 ? resolvedEnd : resolvedStart + (index + 1) * bucketWidth;
    return { tone, startMs: bucketStart, endMs: bucketEnd };
  };

  if (loadState === 'error') {
    return Array.from({ length: count }, (_, index) => makeSegment(index, 'error'));
  }

  const hits = Array.from({ length: count }, () => false);
  if (Array.isArray(viewData)) {
    for (const point of viewData) {
      if (Number(point.value1 ?? 0) <= 0) continue;
      const pointMs = toTimestampMs(Number(point.time));
      if (!Number.isFinite(pointMs) || pointMs < resolvedStart || pointMs > resolvedEnd) continue;
      const index = Math.min(count - 1, Math.max(0, Math.floor((pointMs - resolvedStart) / bucketWidth)));
      hits[index] = true;
    }
  }

  return hits.map((hasData, index) => makeSegment(index, hasData ? 'success' : 'empty'));
};

export const getCollectionStatus = (
  metric?: { viewData?: ChartData[]; loadState?: string } | null,
  objectLabel = 'MySQL'
): CollectionStatusResult => {
  if (metric?.loadState === 'error') {
    return {
      label: '异常',
      tagColor: 'error',
      accentColor: '#ff4d4f',
      summary: '查询失败',
      detail: `当前采集状态指标查询失败，请检查探针与${objectLabel}连通性或采集配置。`
    };
  }

  const latestTone = getLatestCollectionTone(metric?.viewData);

  if (latestTone === 'success') {
    return {
      label: '正常',
      tagColor: 'success',
      accentColor: '#27c274',
      summary: '采集中',
      detail: `当前采集状态指标可正常返回，说明 ${objectLabel} 监控探针采集链路正常。`
    };
  }

  return {
    label: '无数据',
    tagColor: 'warning',
    accentColor: '#fa8c16',
    summary: '暂无采集数据',
    detail: `尚未在当前时间范围内看到采集状态数据，请检查时间范围或等待新数据进入。`
  };
};

export const formatDurationApprox = (durationMs: number): string => {
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  return remainMinutes > 0 ? `${hours} 小时 ${remainMinutes} 分钟` : `${hours} 小时`;
};

export const formatCollectionStatusWindowFromMs = (startMs: number, endMs: number): string => {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return '最近 15 分钟';
  }
  const totalMinutes = Math.max(Math.round((endMs - startMs) / 60000), 1);
  if (totalMinutes < 60) return `最近 ${totalMinutes} 分钟`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `最近 ${hours} 小时 ${minutes} 分钟` : `最近 ${hours} 小时`;
};

export const formatCollectionStatusWindow = (timeValues: TimeValuesProps) => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  return formatCollectionStatusWindowFromMs(Number(startTime), Number(endTime));
};

export const formatCollectionStatusTimelineHint = (
  startMs: number,
  endMs: number,
  segmentCount = COLLECTION_STATUS_SEGMENT_COUNT
): string => {
  const count = Math.max(1, Math.floor(segmentCount));
  const segmentMs = Math.max(endMs - startMs, 0) / count;
  return `每格约 ${formatDurationApprox(segmentMs)}`;
};

export const resolveCollectionStatusRange = (
  timeValues: TimeValuesProps
): { startMs: number; endMs: number } | null => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  const startMs = Number(startTime);
  const endMs = Number(endTime);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return null;
  return { startMs, endMs };
};
