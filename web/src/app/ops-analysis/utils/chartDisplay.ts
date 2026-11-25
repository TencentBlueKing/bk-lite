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
import { defaultLightTokens } from '@/theme/defaults';

declare const displayLimitBrand: unique symbol;
declare const finiteValueBrand: unique symbol;

export type DisplayLimit = number & { readonly [displayLimitBrand]: true };

/** A finite number, including 0 and negatives. NaN and Infinity are not members. */
export type FiniteValue = number & { readonly [finiteValueBrand]: true };

const STATUS_ERROR_VAR = '--theme-color-status-error';

/**
 * Painted when a line has no color of its own.
 * Reads the theme status-error token. Without a document, the token default is used.
 */
export function referenceLineColor(): string {
  if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') {
    return defaultLightTokens.statusError;
  }
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(STATUS_ERROR_VAR)
      .trim();
    return value || defaultLightTokens.statusError;
  } catch {
    return defaultLightTokens.statusError;
  }
}

/**
 * One horizontal guide. `name` is the label drawn on the line.
 * `color` is optional. A missing or illegal color paints the status-error token.
 */
export interface ReferenceLine {
  readonly name: string;
  readonly value: FiniteValue;
  readonly color?: string;
}

/**
 * Parsed domain. Missing field means today's picture.
 * True-only switches are `true | undefined`, never `false`.
 * `referenceLines` is omitted when no entry survives parsing.
 */
export interface ChartDisplay {
  readonly displayLimit?: DisplayLimit;
  readonly sortByValue?: true;
  readonly stackBars?: true;
  readonly referenceLines?: readonly ReferenceLine[];
  readonly autoScroll?: true;
  /** Seconds for one rendered row. Absent means DEFAULT_SCROLL_SECONDS. */
  readonly scrollSeconds?: number;
}

/** One rendered row takes this many seconds when scrollSeconds is absent. */
export const DEFAULT_SCROLL_SECONDS = 2;

/** What the authoring form is allowed to show. Derived from DISPLAY_SLOTS. */
export interface ChartDisplayControls {
  readonly limit: boolean;
  readonly sort: boolean;
  readonly stackBars: boolean;
  readonly referenceLines: boolean;
  readonly autoScroll: boolean;
}

/**
 * Raw config or form values at the boundary.
 * `stack` is intentionally absent: storybook `config.stack` is not a slot.
 */
export interface ChartDisplaySource {
  readonly chartType?: string;
  readonly displayLimit?: unknown;
  readonly sortByValue?: unknown;
  readonly stackBars?: unknown;
  readonly referenceLines?: unknown;
  readonly autoScroll?: unknown;
  readonly scrollSeconds?: unknown;
}

export const CHART_DISPLAY_I18N = {
  count: 'dashboard.displayCount',
  countPlaceholder: 'dashboard.displayCountPlaceholder',
  sort: 'dashboard.sortByValue',
  other: 'dashboard.chartOther',
  timeIgnored: 'dashboard.chartDisplayTimeIgnored',
  stackBars: 'dashboard.stackBars',
  referenceLines: 'dashboard.referenceLines',
  referenceName: 'dashboard.referenceLineName',
  referenceNamePlaceholder: 'dashboard.referenceLineNamePlaceholder',
  referenceValue: 'dashboard.referenceLineValue',
  referenceValuePlaceholder: 'dashboard.referenceLineValuePlaceholder',
  referenceColor: 'dashboard.referenceLineColor',
  referenceEmpty: 'dashboard.referenceLinesEmpty',
  referenceAdd: 'dashboard.referenceLinesAdd',
  autoScroll: 'dashboard.autoScrollRows',
  autoScrollTip: 'dashboard.autoScrollRowsTip',
  scrollSeconds: 'dashboard.scrollSeconds',
} as const;

type DisplaySlotKind = 'positiveInt' | 'positiveNumber' | 'trueOnly' | 'referenceLines';

interface DisplaySlot {
  readonly key: keyof ChartDisplay;
  readonly kind: DisplaySlotKind;
  readonly charts: readonly string[];
}

/**
 * The only list of display keys and the only chart-ownership map.
 * CHART_DISPLAY_KEYS, chartDisplayControls, read, and apply all derive from this.
 */
const ROW_SCROLL_CHARTS = ['table', 'topN', 'eventTable', 'cardList', 'multiValue'] as const;

const DISPLAY_SLOTS = [
  { key: 'displayLimit', kind: 'positiveInt', charts: ['topN', 'pie', 'bar'] },
  { key: 'sortByValue', kind: 'trueOnly', charts: ['pie', 'bar'] },
  { key: 'stackBars', kind: 'trueOnly', charts: ['bar'] },
  { key: 'referenceLines', kind: 'referenceLines', charts: ['bar', 'line'] },
  { key: 'autoScroll', kind: 'trueOnly', charts: ROW_SCROLL_CHARTS },
  { key: 'scrollSeconds', kind: 'positiveNumber', charts: ROW_SCROLL_CHARTS },
] as const satisfies readonly DisplaySlot[];

type DisplaySlotKey = (typeof DISPLAY_SLOTS)[number]['key'];
type EqualKeys<A, B> = (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2)
  ? true
  : false;
const displaySlotKeysMatchChartDisplay: EqualKeys<DisplaySlotKey, keyof ChartDisplay> = true;
void displaySlotKeysMatchChartDisplay;

/** Derived. Proposal overlay is the only caller. Do not re-list these strings. */
export const CHART_DISPLAY_KEYS = DISPLAY_SLOTS.map((slot) => slot.key);

const mintDisplayLimit = (value: number): DisplayLimit => value as DisplayLimit;
const mintFiniteValue = (value: number): FiniteValue => value as FiniteValue;

const LEGACY_KEYS_WITHOUT_CHART_TYPE = new Set<keyof ChartDisplay>(['displayLimit', 'sortByValue']);

const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

function parseReferenceColor(value: unknown): string | undefined {
  if (typeof value !== 'string' || !HEX_COLOR.test(value)) return undefined;
  return value;
}

function parseReferenceLines(value: unknown): readonly ReferenceLine[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const lines: ReferenceLine[] = [];
  value.forEach((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return;
    const record = row as { name?: unknown; value?: unknown; color?: unknown };
    if (typeof record.name !== 'string') return;
    const name = record.name.trim();
    if (!name) return;
    if (typeof record.value !== 'number' || !Number.isFinite(record.value)) return;
    const color = parseReferenceColor(record.color);
    lines.push(color
      ? { name, value: mintFiniteValue(record.value), color }
      : { name, value: mintFiniteValue(record.value) });
  });
  return lines.length > 0 ? lines : undefined;
}

function parseTrueOnly(value: unknown): true | undefined {
  return value === true ? true : undefined;
}

function parseScrollSeconds(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return undefined;
  return value;
}

function parseDisplayLimit(value: unknown): DisplayLimit | undefined {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
    return undefined;
  }
  return mintDisplayLimit(value);
}

function parseSlot(
  slot: DisplaySlot,
  source: ChartDisplaySource | undefined,
): ChartDisplay[keyof ChartDisplay] | undefined {
  const value = source?.[slot.key];
  if (slot.kind === 'positiveInt') return parseDisplayLimit(value);
  if (slot.kind === 'positiveNumber') return parseScrollSeconds(value);
  if (slot.kind === 'trueOnly') return parseTrueOnly(value);
  return parseReferenceLines(value);
}

function slotOwned(slot: DisplaySlot, chartType: string | undefined): boolean {
  return typeof chartType === 'string' && slot.charts.includes(chartType);
}

function includeParsedSlot(
  slot: DisplaySlot,
  source: ChartDisplaySource | undefined,
): boolean {
  if (LEGACY_KEYS_WITHOUT_CHART_TYPE.has(slot.key) && !source?.chartType) return true;
  return slotOwned(slot, source?.chartType);
}

/**
 * Parse once. Legacy limit and sort still parse when chartType is absent, so
 * presentBar / presentRanking / presentPie keep working on a bare display object.
 * stackBars, referenceLines, autoScroll, and scrollSeconds appear only when chartType owns the slot.
 * A line config with a stale stackBars key does not surface stackBars.
 * A pie config with autoScroll does not surface autoScroll.
 */
export function readChartDisplay(source: ChartDisplaySource | undefined): ChartDisplay {
  const display: {
    displayLimit?: DisplayLimit;
    sortByValue?: true;
    stackBars?: true;
    referenceLines?: readonly ReferenceLine[];
    autoScroll?: true;
    scrollSeconds?: number;
  } = {};
  DISPLAY_SLOTS.forEach((slot) => {
    const parsed = parseSlot(slot, source);
    if (parsed === undefined || !includeParsedSlot(slot, source)) return;
    if (slot.key === 'displayLimit') display.displayLimit = parsed as DisplayLimit;
    else if (slot.key === 'sortByValue') display.sortByValue = true;
    else if (slot.key === 'stackBars') display.stackBars = true;
    else if (slot.key === 'autoScroll') display.autoScroll = true;
    else if (slot.key === 'scrollSeconds') display.scrollSeconds = parsed as number;
    else display.referenceLines = parsed as readonly ReferenceLine[];
  });
  return display;
}

/** Form visibility. No chartType and every unlisted chart get all-false. */
export function chartDisplayControls(chartType: string | undefined): ChartDisplayControls {
  const owned = (key: keyof ChartDisplay) => {
    const slot = DISPLAY_SLOTS.find((item) => item.key === key);
    return slot ? slotOwned(slot, chartType) : false;
  };
  return {
    limit: owned('displayLimit'),
    sort: owned('sortByValue'),
    stackBars: owned('stackBars'),
    referenceLines: owned('referenceLines'),
    autoScroll: owned('autoScroll'),
  };
}

/**
 * Rewrite every catalog key on a full form submit.
 * Owned + parsed → target[key] = parsed domain value (plain JSON after brand erasure).
 * Otherwise delete target[key].
 * Idempotent. Does not read or write thresholdColors.
 * Does not use isBlankOptionalValue.
 *
 * Source chartType is required to keep a slot. Callers pass the chart type they are saving.
 * Proposal overlay must not use this: absent proposal keys would wipe stored slots.
 */
export function applyChartDisplay(
  target: Record<string, unknown>,
  source: ChartDisplaySource | undefined,
): void {
  DISPLAY_SLOTS.forEach((slot) => {
    const parsed = parseSlot(slot, source);
    if (slotOwned(slot, source?.chartType) && parsed !== undefined) {
      target[slot.key] = parsed;
    } else {
      delete target[slot.key];
    }
  });
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
