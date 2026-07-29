import { useCallback, useEffect, useMemo, useState } from 'react';

type ChartRecord = Record<string, unknown>;

interface UseChartSeriesStateOptions<T extends ChartRecord> {
  data: T[];
  generateColor?: () => string;
  keyMatcher?: (key: string) => boolean;
}

const DEFAULT_KEY_MATCHER = (key: string) => key.includes('value');

export const getChartSeriesKeys = <T extends ChartRecord>(
  data: T[],
  keyMatcher: (key: string) => boolean = DEFAULT_KEY_MATCHER
) => {
  const keys = new Set<string>();

  if (!Array.isArray(data)) {
    return [];
  }

  data.forEach((item) => {
    if (!item || typeof item !== 'object') {
      return;
    }

    Object.keys(item).forEach((key) => {
      if (keyMatcher(key)) {
        keys.add(key);
      }
    });
  });

  return Array.from(keys);
};

export const getChartDetailsMap = <
  T extends ChartRecord,
  D extends Record<string, unknown> = Record<string, unknown>
>(
    data: T[]
  ) => {
  return data.reduce((acc, item) => {
    const details = item?.details;
    if (details && typeof details === 'object') {
      Object.assign(acc, details);
    }
    return acc;
  }, {} as D);
};

export const hasChartDimensionDetails = (details: Record<string, unknown>) => {
  return !Object.values(details || {}).every(
    (item) => !Array.isArray(item) || item.length === 0
  );
};

export const useChartSeriesState = <
  T extends ChartRecord,
  D extends Record<string, unknown> = Record<string, unknown>
>({
    data,
    generateColor,
    keyMatcher = DEFAULT_KEY_MATCHER,
  }: UseChartSeriesStateOptions<T>) => {
  const chartKeys = useMemo(() => getChartSeriesKeys(data, keyMatcher), [data, keyMatcher]);
  const details = useMemo(() => getChartDetailsMap<T, D>(data), [data]);
  const hasDimension = useMemo(
    () => hasChartDimensionDetails(details),
    [details]
  );
  const [colors, setColors] = useState<string[]>([]);
  const [visibleAreas, setVisibleAreas] = useState<string[]>([]);

  useEffect(() => {
    setVisibleAreas(chartKeys);

    if (!generateColor || chartKeys.length <= colors.length) {
      return;
    }

    const nextColors = Array.from(
      { length: chartKeys.length - colors.length },
      () => generateColor()
    );
    setColors((prev) => [...prev, ...nextColors]);
  }, [chartKeys, colors.length, generateColor]);

  const toggleVisibleArea = useCallback((key: string) => {
    setVisibleAreas((prevVisibleAreas) =>
      prevVisibleAreas.includes(key)
        ? prevVisibleAreas.filter((area) => area !== key)
        : [...prevVisibleAreas, key]
    );
  }, []);

  return {
    chartKeys,
    colors,
    details,
    hasDimension,
    setColors,
    setVisibleAreas,
    toggleVisibleArea,
    visibleAreas,
  };
};
