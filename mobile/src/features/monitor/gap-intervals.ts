/**
 * 与 web/src/app/monitor/components/monitor-chart-runtime/gap-intervals.ts 对齐。
 * 时间统一为秒级 Unix 时间戳；ECharts 展示前再转毫秒。
 */

export interface GapInterval {
  start: number;
  end: number;
  duration?: number;
  series?: Array<{
    metric?: Record<string, string>;
    missing_points?: number;
  }>;
}

export interface ChartData {
  time: number;
  gapIntervals?: GapInterval[];
  seriesMetrics?: Record<string, Record<string, string>>;
  [key: string]: unknown;
}

export const GAP_FILL_COLOR = 'rgba(244, 59, 44, 0.07)';
export const GAP_BOUNDARY_COLOR = 'rgba(244, 59, 44, 0.3)';

export const normalizeGapIntervals = (gaps: GapInterval[] = []): GapInterval[] =>
  gaps
    .map((gap) => ({
      ...gap,
      start: Number(gap.start),
      end: Number(gap.end),
    }))
    .filter(
      (gap) =>
        Number.isFinite(gap.start)
        && Number.isFinite(gap.end)
        && gap.end >= gap.start,
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

export const getRenderedGapIntervals = (
  data: ChartData[],
  gaps: GapInterval[] = [],
  xAxisDomain?: [number, number],
): GapInterval[] => {
  const visibleXAxisDomain = resolveVisibleXAxisDomain(data, xAxisDomain);
  const reportedGaps = mergeGapIntervalsForDisplay(
    normalizeGapIntervals(gaps).map((gap) =>
      alignReportedGapToSampleBoundaries(data, gap, visibleXAxisDomain)),
  );
  // 后端区间是缺失采样点；视觉边界取有效点与缺失点的中点，避免背景压住折线。
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
