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

const isPresentChartValue = (value: unknown): boolean => {
  return typeof value === 'number' && Number.isFinite(value);
};

const getMetricKey = (metric: Record<string, string> = {}): string => {
  return JSON.stringify(
    Object.entries(metric).sort(([left], [right]) => left.localeCompare(right))
  );
};

const getGapValueKeys = (data: ChartData[], gap: GapInterval): Set<string> => {
  const gapMetricKeys = new Set(
    (gap.series || [])
      .map((item) => item.metric)
      .filter((metric): metric is Record<string, string> => !!metric)
      .map((metric) => getMetricKey(metric))
  );
  const valueKeys = new Set<string>();

  if (!gapMetricKeys.size) {
    return valueKeys;
  }

  data.forEach((item) => {
    Object.entries(item.seriesMetrics || {}).forEach(([valueKey, metric]) => {
      if (gapMetricKeys.has(getMetricKey(metric))) {
        valueKeys.add(valueKey);
      }
    });
  });

  return valueKeys;
};

const getFinitePointTimes = (data: ChartData[], valueKeys?: Set<string>): number[] => {
  const times = new Set<number>();

  data.forEach((item) => {
    const time = Number(item.time);
    if (!Number.isFinite(time)) {
      return;
    }

    const keys = valueKeys?.size
      ? Array.from(valueKeys)
      : Object.keys(item).filter((key) => /^value\d+$/.test(key));

    if (keys.some((key) => isPresentChartValue(item[key]))) {
      times.add(time);
    }
  });

  return Array.from(times).sort((left, right) => left - right);
};

const getChartValueKeys = (data: ChartData[]): string[] => {
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

const getMedianInterval = (times: number[]): number => {
  const intervals = times
    .slice(1)
    .map((time, index) => time - times[index])
    .filter((interval) => Number.isFinite(interval) && interval > 0)
    .sort((left, right) => left - right);

  if (!intervals.length) {
    return 0;
  }

  return intervals[Math.floor(intervals.length / 2)];
};

export const deriveFinitePointGapIntervals = (data: ChartData[]): GapInterval[] => {
  const gaps: GapInterval[] = [];

  getChartValueKeys(data).forEach((key) => {
    const times = getFinitePointTimes(data, new Set([key]));
    const medianInterval = getMedianInterval(times);
    if (!medianInterval) {
      return;
    }

    times.slice(1).forEach((time, index) => {
      const previousTime = times[index];
      const interval = time - previousTime;
      if (interval > medianInterval * 2) {
        gaps.push({
          start: previousTime,
          end: time,
          duration: interval,
        });
      }
    });
  });

  return mergeGapIntervalsForDisplay(gaps);
};

export const getChartDataWithGapBreaks = (
  data: ChartData[],
  gaps: GapInterval[] = []
): ChartData[] => {
  const breakPoints = new Map<number, Set<string>>();

  getChartValueKeys(data).forEach((key) => {
    const times = getFinitePointTimes(data, new Set([key]));
    const medianInterval = getMedianInterval(times);
    if (!medianInterval) {
      return;
    }

    times.slice(1).forEach((time, index) => {
      const previousTime = times[index];
      if (time - previousTime > medianInterval * 2) {
        const breakTime = (previousTime + time) / 2;
        const keys = breakPoints.get(breakTime) || new Set<string>();
        keys.add(key);
        breakPoints.set(breakTime, keys);
      }
    });
  });

  normalizeGapIntervals(gaps).forEach((gap) => {
    const valueKeys = getGapValueKeys(data, gap);
    if (!valueKeys.size) {
      return;
    }
    const breakTime = (gap.start + gap.end) / 2;
    const keys = breakPoints.get(breakTime) || new Set<string>();
    valueKeys.forEach((key) => keys.add(key));
    breakPoints.set(breakTime, keys);
  });

  if (!breakPoints.size) {
    return data;
  }

  const breakRows = Array.from(breakPoints.entries()).map(([time, keys]) => {
    const row: ChartData = { time };
    keys.forEach((key) => {
      row[key] = null;
    });
    return row;
  });

  return [...data, ...breakRows].sort((left, right) => left.time - right.time);
};

export const expandGapIntervalsToChartPoints = (
  data: ChartData[],
  gaps: GapInterval[] = []
): GapInterval[] => {
  const gapIntervals = normalizeGapIntervals(gaps);
  const fallbackTimes = getFinitePointTimes(data);

  if (!gapIntervals.length || fallbackTimes.length < 2) {
    return gapIntervals;
  }

  return gapIntervals.map((gap) => {
    const gapValueKeys = getGapValueKeys(data, gap);
    const times = gapValueKeys.size
      ? getFinitePointTimes(data, gapValueKeys)
      : fallbackTimes;
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

export const getRenderedGapIntervals = (
  data: ChartData[],
  gaps: GapInterval[] = []
): GapInterval[] => {
  return mergeGapIntervalsForDisplay(
    [
      ...expandGapIntervalsToChartPoints(data, gaps),
      ...deriveFinitePointGapIntervals(data),
    ]
  );
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
