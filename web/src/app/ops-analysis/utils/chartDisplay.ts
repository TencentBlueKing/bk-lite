import {
  ChartDataTransformer,
  type ChartFieldMapping,
  type LineBarChartData,
  type PieChartData,
  type SeriesDataItem,
} from '@/app/ops-analysis/utils/chartDataTransform';
import { hasExplicitLineBarMapping } from '@/app/ops-analysis/utils/lineBarFieldMapping';
import type { ChartLinkPoint } from '@/app/ops-analysis/utils/interactionLink';
import type { TopNItem } from '@/app/ops-analysis/utils/topNData';
import { unwrapTopNData } from '@/app/ops-analysis/utils/topNData';

declare const brand: unique symbol;

export type DisplayLimit = number & { readonly [brand]: true };

export interface ChartDisplay {
  readonly displayLimit?: DisplayLimit;
  readonly sortByValue?: true;
}

export interface ChartDisplayPatch {
  readonly displayLimit: DisplayLimit | undefined;
  readonly sortByValue: true | undefined;
}

export const CHART_DISPLAY_KEYS = ['displayLimit', 'sortByValue'] as const;

export const CHART_DISPLAY_I18N = {
  count: 'dashboard.displayCount',
  countPlaceholder: 'dashboard.displayCountPlaceholder',
  sort: 'dashboard.sortByValue',
  other: 'dashboard.chartOther',
  timeIgnored: 'dashboard.chartDisplayTimeIgnored',
} as const;

const mintDisplayLimit = (value: number): DisplayLimit => value as DisplayLimit;

const parseDisplayLimit = (value: unknown): DisplayLimit | undefined => {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
    return undefined;
  }
  return mintDisplayLimit(value);
};

export function readChartDisplay(
  source: { displayLimit?: unknown; sortByValue?: unknown } | undefined,
): ChartDisplay {
  const displayLimit = parseDisplayLimit(source?.displayLimit);
  const sortByValue = source?.sortByValue === true ? true : undefined;
  return {
    ...(displayLimit !== undefined ? { displayLimit } : {}),
    ...(sortByValue ? { sortByValue } : {}),
  };
}

export function chartDisplayControls(
  chartType: string | undefined,
): { limit: boolean; sort: boolean } {
  if (chartType === 'topN') return { limit: true, sort: false };
  if (chartType === 'pie' || chartType === 'bar') return { limit: true, sort: true };
  return { limit: false, sort: false };
}

export function chartDisplayPatch(
  source: { chartType?: string; displayLimit?: unknown; sortByValue?: unknown } | undefined,
): ChartDisplayPatch {
  const controls = chartDisplayControls(source?.chartType);
  const display = readChartDisplay(source);
  return {
    displayLimit: controls.limit ? display.displayLimit : undefined,
    sortByValue: controls.sort ? display.sortByValue : undefined,
  };
}

export function presentRanking(
  items: readonly TopNItem[],
  display: ChartDisplay,
): TopNItem[] {
  const limit = display.displayLimit;
  if (limit === undefined || limit >= items.length) return items as TopNItem[];
  return items.slice(0, limit);
}

const sortPieSlices = (slices: PieChartData): PieChartData => slices
  .map((slice, index) => ({ slice, index }))
  .sort((left, right) => {
    if (left.slice.value !== right.slice.value) {
      return right.slice.value - left.slice.value;
    }
    return left.index - right.index;
  })
  .map((item) => item.slice);

export function presentPie(
  slices: PieChartData,
  display: ChartDisplay,
  otherName: string,
): PieChartData {
  const sorting = display.sortByValue === true;
  const limit = display.displayLimit;
  if (!sorting && limit === undefined) return slices;

  const ordered = sorting ? sortPieSlices(slices) : slices;
  if (limit === undefined || limit >= ordered.length) {
    return sorting ? ordered : slices;
  }

  const kept = ordered.slice(0, limit);
  const tail = ordered.slice(limit);
  const value = tail.reduce((sum, slice) => sum + slice.value, 0);
  return [...kept, { name: otherName, value }];
}

export function collectRawDimensionValues(
  rawData: unknown,
  config?: {
    dimensionField?: string;
    valueField?: string;
    valueFields?: string[];
    seriesField?: string;
  },
): unknown[] {
  const dimensionField = config?.dimensionField?.trim() || '';
  if (hasExplicitLineBarMapping(config)) {
    return unwrapTopNData(rawData).map((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return undefined;
      return (row as Record<string, unknown>)[dimensionField];
    });
  }

  if (Array.isArray(rawData)) {
    if (rawData.length === 0) return [];
    const first = rawData[0];
    if (Array.isArray(first)) {
      return rawData.map((item) => (Array.isArray(item) ? item[0] : undefined));
    }
    if (first && typeof first === 'object' && 'name' in (first as Record<string, unknown>)) {
      return rawData.map((item) => (item as { name?: unknown }).name);
    }
    return [];
  }

  if (rawData && typeof rawData === 'object') {
    const values: unknown[] = [];
    Object.values(rawData as Record<string, unknown>).forEach((series) => {
      if (!Array.isArray(series)) return;
      series.forEach((item) => {
        if (Array.isArray(item)) values.push(item[0]);
        else if (item && typeof item === 'object' && 'name' in (item as Record<string, unknown>)) {
          values.push((item as { name?: unknown }).name);
        }
      });
    });
    return values;
  }

  return [];
}

const finiteCategorySum = (chart: LineBarChartData, index: number): number | null => {
  let sum = 0;
  let seen = false;
  const add = (value: number | null | undefined) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    sum += value;
    seen = true;
  };
  add(chart.values?.[index]);
  chart.series?.forEach((series) => add(series.data[index]));
  return seen ? sum : null;
};

const sumFiniteCells = (
  data: Array<number | null> | undefined,
  indexes: readonly number[],
): number | null => {
  let sum = 0;
  let seen = false;
  indexes.forEach((index) => {
    const value = data?.[index];
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    sum += value;
    seen = true;
  });
  return seen ? sum : null;
};

const keptPoints = (
  points: ChartLinkPoint[] | undefined,
  categoryCount: number,
  kept: readonly number[],
): ChartLinkPoint[] | undefined => {
  if (!points || points.length !== categoryCount) return undefined;
  return kept.map((index) => points[index]);
};

const presentSeries = (
  series: SeriesDataItem,
  categoryCount: number,
  kept: readonly number[],
  tail: readonly number[],
): SeriesDataItem => {
  const data = kept.map((index) => series.data[index] ?? null);
  if (tail.length > 0) data.push(sumFiniteCells(series.data, tail));
  const points = keptPoints(series.points, categoryCount, kept);
  return points ? { name: series.name, data, points } : { name: series.name, data };
};

export function presentBar(
  chart: LineBarChartData,
  display: ChartDisplay,
  input: {
    rawData: unknown;
    mapping: ChartFieldMapping | undefined;
    otherName: string;
  },
): LineBarChartData {
  // 时间分类保持转换后的顺序。按数值重排会打乱已经按时间或字典序排好的轴。
  if (ChartDataTransformer.shouldFormatAsTimeDimension(
    collectRawDimensionValues(input.rawData, input.mapping),
  )) {
    return chart;
  }
  if (display.displayLimit === undefined && display.sortByValue !== true) {
    return chart;
  }

  const categoryCount = chart.categories.length;
  const order = chart.categories.map((_, index) => index);
  if (display.sortByValue === true) {
    order.sort((left, right) => {
      const leftSum = finiteCategorySum(chart, left);
      const rightSum = finiteCategorySum(chart, right);
      if (leftSum === null && rightSum === null) return left - right;
      if (leftSum === null) return 1;
      if (rightSum === null) return -1;
      if (leftSum !== rightSum) return rightSum - leftSum;
      return left - right;
    });
  }

  const limit = display.displayLimit;
  const kept = limit === undefined ? order : order.slice(0, limit);
  const tail = limit === undefined ? [] : order.slice(limit);
  const categories = kept.map((index) => chart.categories[index]);
  if (tail.length > 0) categories.push(input.otherName);

  const next: LineBarChartData = { categories };
  if (chart.values) {
    const values = kept.map((index) => chart.values?.[index] ?? null);
    if (tail.length > 0) values.push(sumFiniteCells(chart.values, tail));
    next.values = values;
  }
  if (chart.series) {
    next.series = chart.series.map((series) => presentSeries(series, categoryCount, kept, tail));
  }
  const points = keptPoints(chart.points, categoryCount, kept);
  if (points) next.points = points;
  return next;
}
