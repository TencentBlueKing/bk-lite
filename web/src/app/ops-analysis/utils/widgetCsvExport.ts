import type { DatasourceItem, ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { TableColumnConfigItem, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import {
  formatVisibleChartValue,
  getLineBarYAxisName,
  hasValueFormatConfigured,
  resolveMultiValueRowDisplay,
} from '@/app/ops-analysis/utils/chartValueFormat';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { buildCsvDocument, buildCsvFilename } from '@/app/ops-analysis/utils/csvDocument';
import { validateMultiValueData } from '@/app/ops-analysis/utils/multiValueData';
import { resolveRadarSeriesData } from '@/app/ops-analysis/utils/radarData';
import { resolveTableCellPresentation } from '@/app/ops-analysis/utils/tableCellStyle';
import { parseTableLikeData, resolveTableLikeColumns } from '@/app/ops-analysis/utils/tableLikeData';
import {
  applyTableQueryList,
  type TableQueryCondition,
} from '@/app/ops-analysis/utils/tableQueryList';
import { resolveTopNHeaderLabel } from '@/app/ops-analysis/components/widgets/comTopN';
import { supportsServerPagination } from '@/app/ops-analysis/utils/tablePagination';
import { buildTopNItems, unwrapTopNData } from '@/app/ops-analysis/utils/topNData';

/**
 * 非 NATS 取数把 page_size 钳到 1000（`_normalize_preview_limit`）。
 * 一次请求再大也会被静默截断，无法判断是否已经拿全，所以导出上限取 1000。
 */
export const CSV_EXPORT_ROW_LIMIT = 1000;

const CSV_EXPORT_CHART_TYPES = new Set([
  'table',
  'eventTable',
  'line',
  'bar',
  'pie',
  'topN',
  'radar',
  'multiValue',
]);

export const supportsWidgetCsvExport = (chartType?: string): boolean =>
  Boolean(chartType && CSV_EXPORT_CHART_TYPES.has(chartType));

export const isRadarMultiSeriesUnsupported = (rawData: unknown): boolean =>
  resolveRadarSeriesData(rawData).unsupported === 'multi_series';

export const isWidgetCsvExportDataBlocked = (
  chartType: string | undefined,
  rawData: unknown,
): boolean => chartType === 'radar' && isRadarMultiSeriesUnsupported(rawData);

export interface WidgetCsvLabels {
  time: string;
  dimension: string;
  value: string;
  indicator: string;
  name: string;
  seriesValue: string;
}

type Translate = (id: string) => string;

export const buildWidgetCsvLabels = (t: Translate): WidgetCsvLabels => ({
  time: t('dashboard.csvTime'),
  dimension: t('dashboard.dimensionField'),
  value: t('dashboard.valueField'),
  indicator: t('dashboard.csvIndicator'),
  name: t('dashboard.csvName'),
  seriesValue: t('topology.treeValueTitle'),
});

export interface CsvTable {
  headers: string[];
  rows: string[][];
}

export interface WidgetCsvExportRuntime {
  chartType?: string;
  rawData: unknown;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  tableQueryParams?: Record<string, unknown>;
  requestParams?: Record<string, unknown> | null;
  loading?: boolean;
  dataSourceId?: number;
  fetchSourceData?: (params: Record<string, unknown>) => Promise<unknown>;
  /** 拓扑非翻页取数代号。翻页不加这个数，筛选和搜索才会加。 */
  requestGeneration?: number;
}

export type WidgetCsvExportOutcome =
  | {
    kind: 'downloaded' | 'truncated';
    csv: string;
    filename: string;
    exportedCount: number;
    limit: number;
  }
  | { kind: 'pending' | 'failed' | 'unconfigured' | 'unsupported' | 'stale' };

class WidgetCsvExportStaleError extends Error {
  constructor() {
    super('widget csv export stale');
    this.name = 'WidgetCsvExportStaleError';
  }
}

const withoutTablePage = (
  params: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null => {
  if (!params) return null;
  const rest: Record<string, unknown> = {};
  Object.keys(params).sort().forEach((key) => {
    if (key === 'page' || key === 'page_size') return;
    rest[key] = params[key];
  });
  return rest;
};

export const isTablePageOnlyChange = (
  previous: Record<string, unknown> | null | undefined,
  next: Record<string, unknown> | null | undefined,
): boolean => {
  if (!previous || !next) return false;
  return JSON.stringify(withoutTablePage(previous)) === JSON.stringify(withoutTablePage(next));
};

const exportQueryFingerprint = (runtime: WidgetCsvExportRuntime): string => JSON.stringify({
  tableQueryParams: withoutTablePage(runtime.tableQueryParams),
  filters: withoutTablePage(runtime.requestParams),
  ...(runtime.requestGeneration === undefined ? {} : {
    requestGeneration: runtime.requestGeneration,
  }),
});

const fieldDisplayName = (
  schema: ResponseFieldDefinition[] | undefined,
  key?: string,
): string => {
  const trimmed = key?.trim() || '';
  if (!trimmed) return '';
  const title = schema?.find((field) => field.key === trimmed)?.title?.trim();
  return title || trimmed;
};

const appendUnit = (label: string, config?: ValueConfig): string => {
  const suffix = getLineBarYAxisName(config);
  if (!suffix || !label || label.includes(suffix)) return label;
  return `${label} (${suffix})`;
};

const formatChartCell = (value: unknown, config?: ValueConfig): string => {
  if (value == null || value === '') return '';
  if (typeof value === 'number' || typeof value === 'string') {
    return formatVisibleChartValue(value, config);
  }
  return String(value);
};

const collectRawDimensionValues = (rawData: unknown, config?: ValueConfig): unknown[] => {
  const dimensionField = config?.dimensionField?.trim() || '';
  const valueField = config?.valueField?.trim() || '';
  if (dimensionField || valueField) {
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
};

const lineDimensionHeader = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
  schema?: ResponseFieldDefinition[],
): string => {
  const titled = fieldDisplayName(schema, config?.dimensionField);
  if (titled) return titled;
  const timeAxis = ChartDataTransformer.shouldFormatAsTimeDimension(
    collectRawDimensionValues(rawData, config),
  );
  return timeAxis ? labels.time : labels.dimension;
};

export const buildLineBarCsvTable = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
  schema?: ResponseFieldDefinition[],
): CsvTable => {
  const chart = ChartDataTransformer.transformToLineBarData(rawData, {
    dimensionField: config?.dimensionField,
    valueField: config?.valueField,
  });
  const dimensionLabel = lineDimensionHeader(rawData, config, labels, schema);
  if (chart.series?.length) {
    return {
      headers: [
        dimensionLabel,
        ...chart.series.map((series) => appendUnit(series.name || labels.seriesValue, config)),
      ],
      rows: chart.categories.map((category, index) => [
        category,
        ...chart.series!.map((series) => formatChartCell(series.data[index], config)),
      ]),
    };
  }

  const valueLabel = appendUnit(
    fieldDisplayName(schema, config?.valueField) || labels.seriesValue,
    config,
  );
  return {
    headers: [dimensionLabel, valueLabel],
    rows: chart.categories.map((category, index) => [
      category,
      formatChartCell(chart.values?.[index], config),
    ]),
  };
};

export const buildPieCsvTable = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
  schema?: ResponseFieldDefinition[],
): CsvTable => {
  const slices = ChartDataTransformer.transformToPieData(rawData, {
    dimensionField: config?.dimensionField,
    valueField: config?.valueField,
    pieScalarFields: config?.pieScalarFields,
  });
  return {
    headers: [
      fieldDisplayName(schema, config?.dimensionField) || labels.dimension,
      appendUnit(fieldDisplayName(schema, config?.valueField) || labels.value, config),
    ],
    rows: slices.map((slice) => [slice.name, formatChartCell(slice.value, config)]),
  };
};

export const buildTopNCsvTable = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
  schema?: ResponseFieldDefinition[],
): CsvTable => {
  const preferTitleOnly = isScreenChartThemeMode(config?.chartThemeMode);
  const labelHeader = resolveTopNHeaderLabel(config?.topNLabelField, schema, { preferTitleOnly })
    || labels.name;
  const valueHeader = appendUnit(
    resolveTopNHeaderLabel(config?.topNValueField, schema, { preferTitleOnly }) || labels.value,
    config,
  );
  const items = buildTopNItems(rawData, config?.topNLabelField, config?.topNValueField, {
    scalarFields: config?.topNScalarFields,
  });
  return {
    headers: [labelHeader, valueHeader],
    rows: items.map((item) => [item.name, formatChartCell(item.value, config)]),
  };
};

export const buildRadarCsvTable = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
): CsvTable => {
  const series = resolveRadarSeriesData(
    rawData,
    config?.radar,
    config?.selectedFields || [],
  );
  return {
    headers: [labels.indicator, appendUnit(labels.value, config)],
    rows: series.indicatorLabels.map((label, index) => [
      label,
      formatChartCell(series.indicatorValues[index], config),
    ]),
  };
};

export const buildMultiValueCsvTable = (
  rawData: unknown,
  config: ValueConfig | undefined,
  labels: WidgetCsvLabels,
  schema?: ResponseFieldDefinition[],
): CsvTable => {
  const parsed = validateMultiValueData(rawData, '', {
    labelField: config?.multiValueLabelField,
    valueField: config?.multiValueValueField,
  });
  return {
    headers: [
      fieldDisplayName(schema, config?.multiValueLabelField) || labels.name,
      appendUnit(fieldDisplayName(schema, config?.multiValueValueField) || labels.value, config),
    ],
    rows: parsed.items.map((item) => [
      item.label,
      resolveMultiValueRowDisplay(item.value, config).text,
    ]),
  };
};

const exportColumns = (
  chartType: string,
  config: ValueConfig | undefined,
  dataSource: DatasourceItem | undefined,
  rows: Record<string, unknown>[],
): TableColumnConfigItem[] => {
  if (chartType === 'eventTable') {
    return (config?.tableConfig?.columns || [])
      .filter((column) => column.visible && column.columnType !== 'actions')
      .sort((left, right) => left.order - right.order);
  }

  return resolveTableLikeColumns({
    configuredColumns: config?.tableConfig?.columns,
    schemaFields: dataSource?.field_schema,
    rows,
  }).filter((column) => column.visible && column.columnType !== 'actions');
};

const formatTableExportCell = (
  chartType: string,
  raw: unknown,
  column: TableColumnConfigItem,
  config?: ValueConfig,
): string => {
  if (chartType === 'eventTable') {
    if (raw == null) return '-';
    return String(raw);
  }

  const presentation = resolveTableCellPresentation(raw, column);
  if (
    presentation.mode === 'text'
    && column.key === 'value'
    && hasValueFormatConfigured(config)
  ) {
    return formatVisibleChartValue(
      typeof raw === 'number' || typeof raw === 'string' ? raw : String(raw ?? ''),
      config,
    );
  }
  return presentation.mode === 'colorBackground'
    ? presentation.tooltipText
    : presentation.displayText;
};

export const buildTableCsvTable = (
  chartType: 'table' | 'eventTable',
  rows: Record<string, unknown>[],
  config: ValueConfig | undefined,
  dataSource: DatasourceItem | undefined,
): CsvTable & { unconfigured: boolean } => {
  const columns = exportColumns(chartType, config, dataSource, rows);
  return {
    unconfigured: chartType === 'eventTable' && columns.length === 0,
    headers: columns.map((column) => column.title || column.key),
    rows: rows.map((row) => columns.map((column) => (
      formatTableExportCell(chartType, row[column.key], column, config)
    ))),
  };
};

const isQueryCondition = (value: unknown): value is TableQueryCondition => {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  if (typeof record.field !== 'string') return false;
  if (record.type === 'str*' && typeof record.value === 'string') return true;
  return record.type === 'time'
    && typeof record.start === 'string'
    && typeof record.end === 'string';
};

export const readTableQueryList = (
  params: Record<string, unknown> | undefined,
): TableQueryCondition[] => {
  const value = params?.query_list;
  if (!Array.isArray(value)) return [];
  return value.filter(isQueryCondition);
};

const positivePageSize = (value: unknown): number | undefined => {
  const size = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(size) || size <= 0) return undefined;
  return Math.floor(size);
};

/**
 * 告警列表会把 page_size 钳到 100 并回显。云账单接受 1000。
 * 非 NATS 预览钳到 1000。LLM 实例列表钳到 100 但不回显 page_size。
 */
const readEchoedPageSize = (payload: unknown, requested: number): number | undefined => {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return undefined;
  const echoed = positivePageSize((payload as Record<string, unknown>).page_size);
  if (echoed === undefined) return undefined;
  return Math.min(echoed, requested);
};

const fetchTablePages = async (
  fetchPage: (page: number, pageSize: number) => Promise<unknown>,
  limit: number,
  queryListActive: boolean,
): Promise<{ rows: Record<string, unknown>[]; total: number | null; exhausted: boolean }> => {
  const firstPayload = await fetchPage(1, limit);
  const first = parseTableLikeData<Record<string, unknown>>(
    firstPayload,
    { current: 1, pageSize: limit },
    true,
  );
  if (!first.isPaginated) {
    const rows = first.rows.slice(0, limit);
    return {
      rows,
      total: null,
      exhausted: first.rows.length < limit,
    };
  }

  const total = first.pagination.total;
  const echoed = readEchoedPageSize(firstPayload, limit);
  let pageSize = echoed ?? limit;
  if (
    !echoed
    && !queryListActive
    && first.rows.length > 0
    && first.rows.length < limit
    && total > first.rows.length
  ) {
    pageSize = first.rows.length;
  }

  const rows = [...first.rows];
  let covered = queryListActive ? pageSize : first.rows.length;
  const finish = (exhausted: boolean) => ({
    rows: rows.slice(0, limit),
    total,
    exhausted: exhausted && rows.length <= limit,
  });
  if (first.rows.length === 0 || rows.length >= limit || covered >= total) {
    return finish(covered >= total || first.rows.length === 0);
  }
  if (!queryListActive && first.rows.length < pageSize) {
    return finish(true);
  }

  let page = 2;
  const maxPages = Math.ceil(Math.max(total, 1) / pageSize) + 1;
  while (rows.length < limit && covered < total && page <= maxPages) {
    const nextPayload = await fetchPage(page, pageSize);
    const nextEcho = readEchoedPageSize(nextPayload, pageSize);
    if (nextEcho && nextEcho < pageSize) pageSize = nextEcho;
    const next = parseTableLikeData<Record<string, unknown>>(
      nextPayload,
      { current: page, pageSize },
      true,
    );
    if (next.rows.length === 0) return finish(true);
    rows.push(...next.rows);
    covered += queryListActive ? pageSize : next.rows.length;
    if (!queryListActive && next.rows.length < pageSize) return finish(true);
    page += 1;
  }
  return finish(covered >= total);
};

export const loadTableExportRows = async ({
  rawData,
  supportsPagination,
  queryList,
  limit = CSV_EXPORT_ROW_LIMIT,
  fetchPage,
}: {
  rawData: unknown;
  supportsPagination: boolean;
  queryList: TableQueryCondition[];
  limit?: number;
  fetchPage?: (page: number, pageSize: number) => Promise<unknown>;
}): Promise<{ rows: Record<string, unknown>[]; truncated: boolean; total: number }> => {
  const initial = parseTableLikeData<Record<string, unknown>>(
    rawData,
    { current: 1, pageSize: limit },
    supportsPagination,
  );
  let sourceRows = initial.rows;
  let total = initial.isPaginated ? initial.pagination.total : initial.rows.length;
  let exhausted = initial.isPaginated
    ? initial.pagination.total <= initial.rows.length
    : !supportsPagination;

  if ((!initial.isPaginated || !exhausted) && supportsPagination && fetchPage) {
    const loaded = await fetchTablePages(fetchPage, limit, queryList.length > 0);
    sourceRows = loaded.rows;
    if (loaded.total != null) total = loaded.total;
    else total = sourceRows.length;
    exhausted = loaded.exhausted;
  }

  const filtered = applyTableQueryList(sourceRows, queryList);
  const exported = filtered.slice(0, limit);
  const incomplete = filtered.length > exported.length || !exhausted;
  return {
    rows: exported,
    truncated: incomplete && exported.length > 0,
    total,
  };
};

const buildChartTable = (
  runtime: WidgetCsvExportRuntime,
  labels: WidgetCsvLabels,
): CsvTable => {
  const schema = runtime.dataSource?.field_schema;
  switch (runtime.chartType) {
    case 'line':
    case 'bar':
      return buildLineBarCsvTable(runtime.rawData, runtime.config, labels, schema);
    case 'pie':
      return buildPieCsvTable(runtime.rawData, runtime.config, labels, schema);
    case 'topN':
      return buildTopNCsvTable(runtime.rawData, runtime.config, labels, schema);
    case 'radar':
      return buildRadarCsvTable(runtime.rawData, runtime.config, labels);
    case 'multiValue':
      return buildMultiValueCsvTable(runtime.rawData, runtime.config, labels, schema);
    default:
      return { headers: [], rows: [] };
  }
};

export const describeWidgetCsvExportNotice = (
  outcome: WidgetCsvExportOutcome,
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string,
): { level: 'info' | 'warning' | 'error'; text: string } | null => {
  if (outcome.kind === 'truncated') {
    return {
      level: 'info',
      text: t('dashboard.csvExportTruncated', undefined, { count: outcome.exportedCount }),
    };
  }
  if (outcome.kind === 'pending') {
    return { level: 'warning', text: t('dashboard.csvExportPending') };
  }
  if (outcome.kind === 'unconfigured') {
    return { level: 'warning', text: t('dashboard.configureDisplayFieldsFirst') };
  }
  if (outcome.kind === 'stale') {
    return { level: 'warning', text: t('dashboard.csvExportStale') };
  }
  if (outcome.kind === 'failed' || outcome.kind === 'unsupported') {
    return { level: 'error', text: t('dashboard.csvExportFailed') };
  }
  return null;
};

export const createWidgetCsvExport = async (
  runtime: WidgetCsvExportRuntime,
  request: { title: string; now?: Date },
  labels: WidgetCsvLabels,
  limit = CSV_EXPORT_ROW_LIMIT,
  options?: { readLatest?: () => WidgetCsvExportRuntime },
): Promise<WidgetCsvExportOutcome> => {
  if (!supportsWidgetCsvExport(runtime.chartType)) {
    return { kind: 'unsupported' };
  }
  if (isWidgetCsvExportDataBlocked(runtime.chartType, runtime.rawData)) {
    return { kind: 'unsupported' };
  }
  if (runtime.loading) {
    return { kind: 'pending' };
  }

  const fingerprint = exportQueryFingerprint(runtime);
  const assertFresh = () => {
    if (!options?.readLatest) return;
    let latest: WidgetCsvExportRuntime;
    try {
      latest = options.readLatest();
    } catch {
      throw new WidgetCsvExportStaleError();
    }
    if (exportQueryFingerprint(latest) !== fingerprint) {
      throw new WidgetCsvExportStaleError();
    }
  };

  try {
    let table: CsvTable;
    let truncated = false;
    if (runtime.chartType === 'table' || runtime.chartType === 'eventTable') {
      const previewColumns = exportColumns(runtime.chartType, runtime.config, runtime.dataSource, []);
      if (runtime.chartType === 'eventTable' && previewColumns.length === 0) {
        return { kind: 'unconfigured' };
      }
      const supportsPagination = supportsServerPagination(runtime.dataSource?.params);
      const loaded = await loadTableExportRows({
        rawData: runtime.rawData,
        supportsPagination,
        queryList: readTableQueryList(runtime.tableQueryParams),
        limit,
        fetchPage: supportsPagination && runtime.fetchSourceData && runtime.requestParams && runtime.dataSourceId
          ? async (page, pageSize) => {
            assertFresh();
            const fetchSourceData = runtime.fetchSourceData;
            const requestParams = runtime.requestParams;
            if (!fetchSourceData || !requestParams) return null;
            return fetchSourceData({
              ...requestParams,
              page,
              page_size: pageSize,
            });
          }
          : undefined,
      });
      assertFresh();
      const built = buildTableCsvTable(
        runtime.chartType,
        loaded.rows,
        runtime.config,
        runtime.dataSource,
      );
      if (built.unconfigured) return { kind: 'unconfigured' };
      table = built;
      truncated = loaded.truncated;
    } else {
      table = buildChartTable(runtime, labels);
      assertFresh();
    }

    const filename = buildCsvFilename(request.title, request.now);
    const csv = buildCsvDocument(table.headers, table.rows);
    return {
      kind: truncated ? 'truncated' : 'downloaded',
      csv,
      filename,
      exportedCount: table.rows.length,
      limit,
    };
  } catch (error) {
    if (error instanceof WidgetCsvExportStaleError) return { kind: 'stale' };
    return { kind: 'failed' };
  }
};
