import { ChartData, TimeValuesProps } from '@/app/monitor/types';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { CollectionStatusResult } from '../types';
import { COLLECTION_STATUS_SEGMENT_COUNT } from './constants';

export const getCollectionStatusTones = (
  viewData: ChartData[] | undefined,
  segmentCount = COLLECTION_STATUS_SEGMENT_COUNT
): Array<'success' | 'empty'> => {
  if (!Array.isArray(viewData)) return [];
  return [...viewData]
    .sort((a, b) => Number(a.time) - Number(b.time))
    .slice(-segmentCount)
    .map((point) => (Number(point.value1 ?? 0) > 0 ? 'success' as const : 'empty' as const));
};

export const buildCollectionStatusTimeline = (
  loadState: string | undefined,
  viewData: ChartData[] | undefined,
  segmentCount = COLLECTION_STATUS_SEGMENT_COUNT
): Array<'success' | 'empty' | 'error'> => {
  if (loadState === 'error') {
    return Array.from({ length: segmentCount }, () => 'error' as const);
  }
  const tones = getCollectionStatusTones(viewData, segmentCount);
  if (tones.length >= segmentCount) return tones;
  return [
    ...Array.from({ length: segmentCount - tones.length }, () => 'empty' as const),
    ...tones
  ];
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

  const tones = getCollectionStatusTones(metric?.viewData);
  const latestTone = tones.at(-1);

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

export const formatCollectionStatusWindow = (timeValues: TimeValuesProps) => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);
  if (!startTime || !endTime) return '最近 15 分钟';
  const totalMinutes = Math.max(Math.round((endTime - startTime) / 60000), 1);
  if (totalMinutes < 60) return `最近 ${totalMinutes} 分钟`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `最近 ${hours} 小时 ${minutes} 分钟` : `最近 ${hours} 小时`;
};
