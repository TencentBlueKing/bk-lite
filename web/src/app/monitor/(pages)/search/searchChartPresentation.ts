import type { ChartData } from '@/app/monitor/types';
import { calculateMetrics } from '@/app/monitor/utils/common';

export const SEARCH_CHART_VIEWS = ['line', 'combo'] as const;
export const SEARCH_TABLE_KINDS = ['compare', 'samples'] as const;
export const SEARCH_COLUMN_MIN_WIDTH = 80;

export type SearchValueTone = 'high' | 'low' | null;

export type SearchChartView = (typeof SEARCH_CHART_VIEWS)[number];
export type SearchTableKind = (typeof SEARCH_TABLE_KINDS)[number];

export interface SearchChartPresentation {
  view: SearchChartView;
  /** null 表示用户还没手动选过，按序列条数决定。 */
  tableKind: SearchTableKind | null;
  /** null 表示全部激活，空数组表示全部取消，有值时只亮这些序列。 */
  emphasizedKeys: string[] | null;
}

export interface SearchSeriesDetail {
  name?: string;
  label?: string;
  value?: string;
}

export interface SearchSeriesRow {
  key: string;
  identifier: string;
  values: Array<number | null>;
  min: number | null;
  max: number | null;
  avg: number | null;
  latest: number | null;
  /** 最大值减最小值，按表格展示精度。 */
  range: number | null;
}

export interface SearchChartTableModel {
  times: number[];
  series: SearchSeriesRow[];
}

const VALUE_KEY = /^value\d+$/;

const escapeCsvCell = (value: string) =>
  /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;

/** UTF-8 BOM，方便 Excel 直接打开中文表头。 */
export const toCsv = (headers: string[], rows: string[][]): string => {
  const lines = [headers, ...rows].map((row) => row.map(escapeCsvCell).join(','));
  return `\uFEFF${lines.join('\n')}`;
};

export const emptySearchChartPresentation = (): SearchChartPresentation => ({
  view: 'combo',
  tableKind: null,
  emphasizedKeys: null
});

export const parseSearchChartView = (value: unknown): SearchChartView =>
  value === 'line' ? 'line' : 'combo';

export const parseSearchTableKind = (value: unknown): SearchTableKind | null =>
  SEARCH_TABLE_KINDS.includes(value as SearchTableKind)
    ? (value as SearchTableKind)
    : null;

export const defaultSearchTableKind = (seriesCount: number): SearchTableKind =>
  seriesCount >= 2 ? 'compare' : 'samples';

export const resolveSearchTableKind = (
  presentation: SearchChartPresentation,
  seriesCount: number
): SearchTableKind =>
  presentation.tableKind ?? defaultSearchTableKind(seriesCount);

export const readSavedChartPresentation = (raw: {
  view_mode?: unknown;
  table_kind?: unknown;
}): Pick<SearchChartPresentation, 'view' | 'tableKind'> => ({
  view: parseSearchChartView(raw.view_mode),
  tableKind: parseSearchTableKind(raw.table_kind)
});

export const writeSavedChartPresentation = (
  view: SearchChartView | undefined,
  tableKind: SearchTableKind | null | undefined
): { view_mode?: SearchChartView; table_kind?: SearchTableKind } => {
  const fields: { view_mode?: SearchChartView; table_kind?: SearchTableKind } =
    {};
  if (view === 'line' || view === 'combo') fields.view_mode = view;
  if (tableKind) fields.table_kind = tableKind;
  return fields;
};

export const seedSearchChartPresentation = (
  prev: Record<string, SearchChartPresentation>,
  groups: Array<{
    id: string;
    viewMode?: unknown;
    tableKind?: unknown;
  }>
): Record<string, SearchChartPresentation> => {
  const next: Record<string, SearchChartPresentation> = {};
  groups.forEach((group) => {
    next[group.id] =
      prev[group.id] ??
      {
        view: parseSearchChartView(group.viewMode),
        tableKind: parseSearchTableKind(group.tableKind),
        emphasizedKeys: null
      };
  });
  return next;
};

export const applySearchPresentationToAll = (
  prev: Record<string, SearchChartPresentation>,
  groupIds: string[],
  source: SearchChartPresentation
): Record<string, SearchChartPresentation> => {
  const next = { ...prev };
  groupIds.forEach((id) => {
    next[id] = {
      view: source.view,
      tableKind: source.tableKind,
      emphasizedKeys: next[id]?.emphasizedKeys ?? null
    };
  });
  return next;
};

/** 一组里的最高用暖色，最低用冷色。全体相等或不足两个数时不染色。 */
export const toneForExtreme = (
  value: number | null,
  peers: Array<number | null>
): SearchValueTone => {
  if (value === null || !Number.isFinite(value)) return null;
  const finite = peers.filter(
    (item): item is number => item !== null && Number.isFinite(item)
  );
  if (finite.length < 2) return null;
  const low = Math.min(...finite);
  const high = Math.max(...finite);
  if (low === high) return null;
  if (value === high) return 'high';
  if (value === low) return 'low';
  return null;
};

/** 采样明细里，被冻结的序列挪到时间列右侧，同时只保留这一列冻结。 */
export const placeFrozenSampleSeries = <T extends { key: string }>(
  series: T[],
  frozenKey: string | null
): T[] => {
  if (!frozenKey) return series;
  const pinned = series.find((item) => item.key === frozenKey);
  if (!pinned) return series;
  return [pinned, ...series.filter((item) => item.key !== frozenKey)];
};

/** null 全部激活，空数组全部取消。点掉最后一条时回到全部激活。 */
export const isSearchSeriesActive = (emphasizedKeys: string[] | null, key: string) =>
  emphasizedKeys === null || emphasizedKeys.includes(key);

export const toggleEmphasizedSeries = (
  current: string[] | null,
  key: string
): string[] | null => {
  if (current === null) return [key];
  if (!current.includes(key)) return [...current, key];
  const next = current.filter((item) => item !== key);
  return next.length === 0 ? null : next;
};

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

/** 与表格展示同一精度。6.104 和 2.466 在表上是 6.10 和 2.47，极差是 3.63。 */
export const roundSearchDisplayValue = (value: number, digits = 2) =>
  Number(value.toFixed(digits));

export const resolveSearchRange = (
  max: number | null,
  min: number | null,
  digits = 2
): number | null => {
  if (max === null || min === null) return null;
  return roundSearchDisplayValue(
    roundSearchDisplayValue(max, digits) - roundSearchDisplayValue(min, digits),
    digits
  );
};

export const listSearchSeriesKeys = (data: ChartData[]): string[] => {
  const keys = new Set<string>();
  data.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (VALUE_KEY.test(key)) keys.add(key);
    });
  });
  return Array.from(keys).sort(
    (left, right) => Number(left.slice(5)) - Number(right.slice(5))
  );
};

export const formatSearchSeriesIdentifier = (
  details: SearchSeriesDetail[] | undefined
): string => {
  if (!details?.length) return '--';
  const parts = details
    .map((detail) => {
      const value = detail.value ?? '';
      if (!value && !detail.label) return '';
      return detail.label ? `${detail.label}: ${value}` : String(value);
    })
    .filter(Boolean);
  return parts.join('-') || '--';
};

export const buildSearchChartTable = (data: ChartData[]): SearchChartTableModel => {
  const ordered = [...data].sort((left, right) => left.time - right.time);
  const times = ordered.map((row) => row.time);
  const byTime = new Map(ordered.map((row) => [row.time, row]));
  const series = listSearchSeriesKeys(ordered).map((key) => {
    const values = times.map((time) => {
      const raw = byTime.get(time)?.[key];
      return isFiniteNumber(raw) ? raw : null;
    });
    const summary = calculateMetrics(
      ordered as Record<string, number | null | undefined>[],
      key
    );
    const latest = isFiniteNumber(summary.latestValue)
      ? summary.latestValue
      : null;
    const min = isFiniteNumber(summary.minValue) ? summary.minValue : null;
    const max = isFiniteNumber(summary.maxValue) ? summary.maxValue : null;
    const detailRow = ordered.find((row) => row.details?.[key]);
    return {
      key,
      identifier: formatSearchSeriesIdentifier(detailRow?.details?.[key]),
      values,
      min,
      max,
      avg: isFiniteNumber(summary.avgValue) ? summary.avgValue : null,
      latest,
      range: resolveSearchRange(max, min)
    };
  });
  return { times, series };
};

