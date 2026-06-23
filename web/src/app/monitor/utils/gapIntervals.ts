import { ChartData, GapInterval } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';

const normalizeCollectionIntervalSeconds = (value: unknown): number => {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return 0;
  }
  return Math.ceil(numericValue);
};

export const buildGapDetectionParams = <T extends SearchParams>(
  params: T,
  collectionIntervalSeconds: unknown
): T & { detect_gaps?: boolean; collection_interval?: number } => {
  const collectionInterval = normalizeCollectionIntervalSeconds(collectionIntervalSeconds);
  if (!collectionInterval) {
    return params;
  }
  return {
    ...params,
    detect_gaps: true,
    collection_interval: collectionInterval,
  };
};

export const normalizeGapIntervals = (gaps: GapInterval[] = []): GapInterval[] => {
  return gaps
    .map((gap) => ({
      ...gap,
      start: Number(gap.start),
      end: Number(gap.end),
    }))
    .filter((gap) => Number.isFinite(gap.start) && Number.isFinite(gap.end) && gap.end >= gap.start);
};

export const attachGapIntervals = (
  data: ChartData[],
  gaps: GapInterval[] = []
): ChartData[] => {
  const gapIntervals = normalizeGapIntervals(gaps);
  if (!gapIntervals.length) {
    return data;
  }
  return data.map((item) => ({
    ...item,
    gapIntervals,
  }));
};
