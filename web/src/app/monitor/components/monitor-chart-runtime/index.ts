import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { APPOINT_METRIC_IDS } from './constants';
import type { ListItem, MetricItem } from './types';

export const generateUniqueRandomColor = (() => {
  const generatedColors = new Set<string>();
  return (): string => {
    const letters = '0123456789ABCDEF';
    let color;
    do {
      color = '#';
      for (let index = 0; index < 6; index += 1) {
        color += letters[Math.floor(Math.random() * 16)];
      }
    } while (generatedColors.has(color));
    generatedColors.add(color);
    return color;
  };
})();

export const useMonitorChartTimeFormatter = () => {
  const { convertToLocalizedTime } = useLocalizedTime();

  const formatTime = (timestamp: number, minTime: number, maxTime: number) => {
    const totalTimeSpan = maxTime - minTime;
    const time = new Date(timestamp * 1000) + '';
    if (totalTimeSpan === 0) {
      return convertToLocalizedTime(time, 'YYYY-MM-DD HH:mm:ss');
    }
    if (totalTimeSpan <= 24 * 60 * 60) {
      return convertToLocalizedTime(time, 'HH:mm:ss');
    }
    if (totalTimeSpan <= 30 * 24 * 60 * 60) {
      return convertToLocalizedTime(time, 'MM-DD HH:mm');
    }
    if (totalTimeSpan <= 365 * 24 * 60 * 60) {
      return convertToLocalizedTime(time, 'YYYY-MM-DD');
    }
    return convertToLocalizedTime(time, 'YYYY-MM');
  };

  return { formatTime };
};

export const calculateMetrics = (
  data: Record<string, number | null | undefined>[],
  key = 'value1',
) => {
  if (!data || data.length === 0) return {};
  const values = data
    .map((item) => item[key])
    .filter(
      (value): value is number =>
        typeof value === 'number' && !Number.isNaN(value) && value !== null,
    );
  if (values.length === 0) return {};

  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const sumValue = values.reduce((sum, value) => sum + value, 0);
  const avgValue = sumValue / values.length;
  const latestValue = values[values.length - 1];

  return {
    maxValue,
    minValue,
    avgValue,
    sumValue,
    latestValue,
  };
};

export const isStringArray = (input: string): boolean => {
  try {
    if (typeof input !== 'string') {
      return false;
    }
    const parsed = JSON.parse(input);
    return Array.isArray(parsed);
  } catch {
    return false;
  }
};

export const getEnumValue = (metric: MetricItem, id: number | string) => {
  const { unit: input = '', name } = metric || {};
  if (!id && id !== 0) return '--';
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === id)?.name || id
    );
  }
  return Number.isNaN(+id) || APPOINT_METRIC_IDS.includes(name)
    ? id
    : (+id).toFixed(2);
};

export const getEnumColor = (metric: MetricItem, id: number | string) => {
  const { unit: input = '' } = metric || {};
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === +id)?.color || ''
    );
  }
  return '';
};

export type {
  ChartData,
  Dimension,
  GapInterval,
  ListItem,
  MetricItem,
  TableDataItem,
  ThresholdField,
} from './types';

export {
  GAP_INTERVAL_AREA_STYLE,
  buildGapDetectionParams,
  normalizeGapIntervals,
  mergeGapIntervalsForDisplay,
  deriveFinitePointGapIntervals,
  deriveVisibleGapIntervalsFromChartData,
  getChartDataWithGapBreaks,
  expandGapIntervalsToChartPoints,
  getRenderedGapIntervals,
  attachGapIntervals,
} from './gap-intervals';

export { APPOINT_METRIC_IDS } from './constants';
