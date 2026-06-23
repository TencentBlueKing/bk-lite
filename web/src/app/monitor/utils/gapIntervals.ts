import { ChartData, GapInterval } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';

export const GAP_INTERVAL_AREA_STYLE = {
  fill: 'rgba(245, 63, 63, 0.18)',
  fillOpacity: 1,
  strokeOpacity: 0,
} as const;

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

export const mergeGapIntervalsForDisplay = (gaps: GapInterval[] = []): GapInterval[] => {
  const sortedGaps = normalizeGapIntervals(gaps).sort(
    (left, right) => left.start - right.start || left.end - right.end
  );

  return sortedGaps.reduce<GapInterval[]>((merged, gap) => {
    const lastGap = merged[merged.length - 1];

    if (!lastGap || gap.start > lastGap.end) {
      merged.push({
        ...gap,
        duration: gap.end - gap.start,
      });
      return merged;
    }

    lastGap.end = Math.max(lastGap.end, gap.end);
    lastGap.duration = lastGap.end - lastGap.start;
    return merged;
  }, []);
};

const getVisibleValueKeys = (data: ChartData[], valueKeys?: string[]): string[] => {
  if (valueKeys?.length) {
    return valueKeys;
  }

  const keys = new Set<string>();
  data.forEach((item) => {
    Object.keys(item).forEach((key) => {
      if (/^value\d+$/.test(key)) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const isPresentChartValue = (value: unknown): boolean => {
  return typeof value === 'number' && Number.isFinite(value);
};

export const deriveVisibleGapIntervalsFromChartData = (
  data: ChartData[],
  valueKeys?: string[]
): GapInterval[] => {
  const sortedData = data
    .map((item) => ({
      item,
      time: Number(item.time),
    }))
    .filter(({ time }) => Number.isFinite(time))
    .sort((left, right) => left.time - right.time);
  const keys = getVisibleValueKeys(data, valueKeys);
  const gaps: GapInterval[] = [];

  keys.forEach((key) => {
    let previousPresentTime: number | null = null;
    let hasMissingRun = false;

    sortedData.forEach(({ item, time }) => {
      if (isPresentChartValue(item[key])) {
        if (previousPresentTime !== null && hasMissingRun && time > previousPresentTime) {
          gaps.push({
            start: previousPresentTime,
            end: time,
            duration: time - previousPresentTime,
          });
        }
        previousPresentTime = time;
        hasMissingRun = false;
        return;
      }

      if (previousPresentTime !== null) {
        hasMissingRun = true;
      }
    });
  });

  return mergeGapIntervalsForDisplay(gaps);
};

export const expandGapIntervalsToChartPoints = (
  data: ChartData[],
  gaps: GapInterval[] = []
): GapInterval[] => {
  const gapIntervals = normalizeGapIntervals(gaps);
  const times = Array.from(
    new Set(
      data
        .map((item) => Number(item.time))
        .filter((time) => Number.isFinite(time))
    )
  ).sort((left, right) => left - right);

  if (!gapIntervals.length || times.length < 2) {
    return gapIntervals;
  }

  return gapIntervals.map((gap) => {
    const previousPoint = [...times].reverse().find((time) => time <= gap.start);
    const nextPoint = times.find((time) => time >= gap.end);
    const start = previousPoint ?? gap.start;
    const end = nextPoint ?? gap.end;

    return {
      ...gap,
      start,
      end,
      duration: end - start,
    };
  });
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
