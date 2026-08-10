import type { ChartData, GapInterval } from './types';

export const GAP_INTERVAL_AREA_STYLE = {
  fill: 'var(--color-chart-gap-fill)',
  fillOpacity: 1,
  strokeOpacity: 0,
} as const;

export const GAP_INTERVAL_BOUNDARY_STYLE = {
  stroke: 'var(--color-chart-gap-boundary)',
  strokeDasharray: '3 3',
  strokeWidth: 1,
} as const;

const normalizeCollectionIntervalSeconds = (value: unknown): number => {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return 0;
  }
  return Math.ceil(numericValue);
};

export const buildGapDetectionParams = <T extends object>(
  params: T,
  collectionIntervalSeconds: unknown,
): T & { detect_gaps?: boolean; collection_interval?: number } => {
  const collectionInterval = normalizeCollectionIntervalSeconds(
    collectionIntervalSeconds,
  );
  if (!collectionInterval) {
    return params;
  }
  return {
    ...params,
    detect_gaps: true,
    collection_interval: collectionInterval,
  };
};

export const normalizeGapIntervals = (gaps: GapInterval[] = []): GapInterval[] =>
  gaps
    .map((gap) => ({
      ...gap,
      start: Number(gap.start),
      end: Number(gap.end),
    }))
    .filter(
      (gap) =>
        Number.isFinite(gap.start) &&
        Number.isFinite(gap.end) &&
        gap.end >= gap.start,
    );

export const mergeGapIntervalsForDisplay = (
  gaps: GapInterval[] = [],
): GapInterval[] => {
  const sortedGaps = normalizeGapIntervals(gaps).sort(
    (left, right) => left.start - right.start || left.end - right.end,
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

const isPresentChartValue = (value: unknown): boolean =>
  typeof value === 'number' && Number.isFinite(value);

const getMetricKey = (metric: Record<string, string> = {}): string =>
  JSON.stringify(
    Object.entries(metric).sort(([left], [right]) => left.localeCompare(right)),
  );

const getGapValueKeys = (data: ChartData[], gap: GapInterval): Set<string> => {
  const gapMetricKeys = new Set(
    (gap.series || [])
      .map((item) => item.metric)
      .filter((metric): metric is Record<string, string> => !!metric)
      .map((metric) => getMetricKey(metric)),
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

const resolveVisibleXAxisDomain = (
  data: ChartData[],
  xAxisDomain?: [number, number],
): [number, number] | undefined => {
  if (xAxisDomain) {
    return xAxisDomain;
  }
  const times = data
    .map((item) => Number(item.time))
    .filter((time) => Number.isFinite(time));
  return times.length ? [Math.min(...times), Math.max(...times)] : undefined;
};

const alignReportedGapToSampleBoundaries = (
  data: ChartData[],
  gap: GapInterval,
  xAxisDomain?: [number, number],
): GapInterval => {
  const gapValueKeys = getGapValueKeys(data, gap);
  const times = gapValueKeys.size
    ? getFinitePointTimes(data, gapValueKeys)
    : getFinitePointTimes(data);
  const previousPoint = [...times].reverse().find((time) => time < gap.start);
  const nextPoint = times.find((time) => time > gap.end);
  const start = previousPoint === undefined ? gap.start : (previousPoint + gap.start) / 2;
  const end = nextPoint === undefined ? gap.end : (gap.end + nextPoint) / 2;
  const clampedStart = xAxisDomain ? Math.max(xAxisDomain[0], start) : start;
  const clampedEnd = xAxisDomain ? Math.min(xAxisDomain[1], end) : end;

  return {
    ...gap,
    start: clampedStart,
    end: clampedEnd,
    duration: clampedEnd - clampedStart,
  };
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

export const deriveVisibleGapIntervalsFromChartData = (
  data: ChartData[],
  valueKeys?: string[],
): GapInterval[] => {
  const sortedData = data
    .map((item) => ({
      item,
      time: Number(item.time),
    }))
    .filter(({ time }) => Number.isFinite(time))
    .sort((left, right) => left.time - right.time);
  const keys = valueKeys?.length ? valueKeys : getChartValueKeys(data);
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

export const getChartDataWithGapBreaks = (
  data: ChartData[],
  gaps: GapInterval[] = [],
  xAxisDomain?: [number, number],
): ChartData[] => {
  const visibleXAxisDomain = resolveVisibleXAxisDomain(data, xAxisDomain);
  const syntheticPoints = new Map<number, ChartData>();
  const setSyntheticValue = (time: number, key: string, value: number | null) => {
    if (visibleXAxisDomain && (time < visibleXAxisDomain[0] || time > visibleXAxisDomain[1])) {
      return;
    }
    const row = syntheticPoints.get(time) || { time };
    row[key] = value;
    syntheticPoints.set(time, row);
  };

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
        setSyntheticValue(breakTime, key, null);
      }
    });
  });

  normalizeGapIntervals(gaps).forEach((gap) => {
    const valueKeys = getGapValueKeys(data, gap);
    if (!valueKeys.size) {
      return;
    }
    const alignedGap = alignReportedGapToSampleBoundaries(data, gap, visibleXAxisDomain);
    if (alignedGap.end < alignedGap.start) {
      return;
    }
    valueKeys.forEach((key) => {
      const points = data
        .filter((item) => isPresentChartValue(item[key]))
        .sort((left, right) => Number(left.time) - Number(right.time));
      const previousPoint = [...points].reverse().find((item) => Number(item.time) < gap.start);
      const nextPoint = points.find((item) => Number(item.time) > gap.end);

      if (previousPoint) {
        setSyntheticValue(alignedGap.start, key, previousPoint[key] as number);
      }
      setSyntheticValue((alignedGap.start + alignedGap.end) / 2, key, null);
      if (nextPoint) {
        setSyntheticValue(alignedGap.end, key, nextPoint[key] as number);
      }
    });
  });

  if (!syntheticPoints.size) {
    return data;
  }

  const breakRows = Array.from(syntheticPoints.values());

  return [...data, ...breakRows].sort((left, right) => left.time - right.time);
};

export const expandGapIntervalsToChartPoints = (
  data: ChartData[],
  gaps: GapInterval[] = [],
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
  gaps: GapInterval[] = [],
  xAxisDomain?: [number, number],
): GapInterval[] => {
  const visibleXAxisDomain = resolveVisibleXAxisDomain(data, xAxisDomain);
  const reportedGaps = mergeGapIntervalsForDisplay(
    normalizeGapIntervals(gaps).map((gap) =>
      alignReportedGapToSampleBoundaries(data, gap, visibleXAxisDomain)
    ),
  );
  // 后端区间是缺失采样点；视觉边界取有效点与缺失点的中点，避免背景压住折线或留下生硬白缝。
  return reportedGaps.length
    ? reportedGaps
    : deriveFinitePointGapIntervals(data);
};

export const attachGapIntervals = (
  data: ChartData[],
  gaps: GapInterval[] = [],
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
