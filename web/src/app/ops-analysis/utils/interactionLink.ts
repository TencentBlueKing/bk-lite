import dayjs from 'dayjs';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';

import { resolveSameOriginNavigation } from '@/console-layout/screenMode';
import type {
  DashboardActionConfig,
  DashboardActionParamMapping,
  FilterValue,
  UnifiedFilterDefinition,
  WidgetInteractionKind,
  WidgetInteractionLink,
  WidgetInteractionOpenMode,
} from '@/app/ops-analysis/types/dashBoard';
import {
  getDateRangeTimezone,
  resolveDateRange,
} from '@/app/ops-analysis/utils/dateRange';
import { normalizeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';
import { filterDropdownType, listFilterTemplateVariables } from '@/app/ops-analysis/utils/filterTemplate';
import {
  nearestRadarIndicatorIndex,
  type RadarClickGeometry,
} from '@/app/ops-analysis/utils/interactionBehavior';

dayjs.extend(utc);
dayjs.extend(timezone);

export type InteractionSurface = 'edit' | 'view' | 'share';

export type InteractionDataCapability = false | 'click' | 'table' | 'contextMenu' | 'timeline';

export interface ChartLinkPoint {
  seriesName?: string;
  /** 点击瞬间可还原的原始时间，ISO-8601。没有时间维度时不出现。 */
  time?: string;
  /** 折线或柱状的类目轴字段。有时间轴时不设置。 */
  axisField?: string;
  numeric?: number | null;
  text?: string;
  raw?: unknown;
  /** 原始行上真实存在的字段。 */
  fields?: Record<string, unknown>;
}

export interface InteractionVariable {
  token: string;
  label: string;
  group: string;
  /** 样本里第一个非空值。没有样本时不出现。下拉不展示它，只用来判断字段类型。 */
  example?: string;
  /** 筛选参数自己的英文类型。数据点留空，由 token 和样本判断。 */
  valueType?: string;
}

const DATA_VALUE_TOKENS = new Set([
  '__series.name',
  '__value.time',
  '__value.numeric',
  '__value.text',
  '__value.raw',
]);

const DATA_FIELD_PREFIX = '__data.fields.';

const CLICK_CHARTS = new Set([
  'line',
  'bar',
  'pie',
  'gauge',
  'single',
  'topN',
  'radar',
  'cardList',
  'multiValue',
  'nodeGraph',
]);

const TITLE_ONLY = new Set([
  'networkStatusTopology',
  'relatedTopology',
  'topologyMap',
]);

const RESERVED_FIELD_TOKENS = {
  cabinetId: '__data.fields.cabinet.id',
  cabinetName: '__data.fields.cabinet.name',
  deviceId: '__data.fields.device.id',
  deviceName: '__data.fields.device.name',
  systemId: '__data.fields.system.id',
  systemName: '__data.fields.system.name',
  hostId: '__data.fields.host.id',
  hostName: '__data.fields.host.name',
} as const;

export const interactionCapability = (
  chartType?: string,
): { title: boolean; data: InteractionDataCapability } => {
  const type = chartType || '';
  if (TITLE_ONLY.has(type)) return { title: true, data: false };
  if (type === 'table' || type === 'eventTable') return { title: true, data: 'table' };
  if (type === 'eventTimeline') return { title: true, data: 'timeline' };
  if (type === 'room3D' || type === 'application3D') {
    return { title: true, data: 'contextMenu' };
  }
  if (CLICK_CHARTS.has(type)) return { title: true, data: 'click' };
  return { title: true, data: false };
};

export const shouldShowInteractionEntry = (
  surface: InteractionSurface,
  configured: boolean,
) => configured && surface !== 'share';

export const shouldNavigateInteraction = (surface: InteractionSurface) =>
  surface === 'view';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const chartLinkFields = (
  row: unknown,
): Record<string, unknown> | undefined => {
  if (!isRecord(row)) return undefined;
  const fields: Record<string, unknown> = {};
  Object.entries(row).forEach(([key, value]) => {
    if (!key || value === undefined) return;
    fields[key] = value;
  });
  return Object.keys(fields).length ? fields : undefined;
};

export const readChartLinkPoint = (data: unknown): ChartLinkPoint | undefined => {
  if (!isRecord(data)) return undefined;
  const link = data.__link;
  if (!isRecord(link)) return undefined;
  return link as ChartLinkPoint;
};

export interface ChartClickParams {
  data?: unknown;
  event?: {
    offsetX?: number;
    offsetY?: number;
    event?: { offsetX?: number; offsetY?: number };
    target?: { __dimIdx?: number };
    topTarget?: { __dimIdx?: number };
  };
  radar?: RadarClickGeometry;
}

const readClickOffset = (event: ChartClickParams['event']) => {
  const x = typeof event?.offsetX === 'number' ? event.offsetX : event?.event?.offsetX;
  const y = typeof event?.offsetY === 'number' ? event.offsetY : event?.event?.offsetY;
  return { x, y };
};

export const readChartClickPoint = (
  params: ChartClickParams | undefined,
): ChartLinkPoint | undefined => {
  if (!params) return undefined;
  const data = params.data;
  if (isRecord(data) && Array.isArray(data.__links)) {
    const dimension = params.event?.target?.__dimIdx
      ?? params.event?.topTarget?.__dimIdx;
    const links = data.__links as ChartLinkPoint[];
    if (typeof dimension === 'number' && links[dimension]) {
      return links[dimension];
    }
    const offset = readClickOffset(params.event);
    if (
      params.radar
      && typeof offset.x === 'number'
      && typeof offset.y === 'number'
    ) {
      const index = nearestRadarIndicatorIndex(
        { x: offset.x, y: offset.y },
        { x: params.radar.centerX, y: params.radar.centerY },
        params.radar.indicatorCount || links.length,
        params.radar,
      );
      if (typeof index === 'number' && links[index]) return links[index];
    }
  }
  return readChartLinkPoint(data);
};

export const interactionActionColumnTitle = (
  t: (key: string, fallback?: string) => string,
) => t('dashboard.interactionActionColumn', '操作');

export const interactionActionLinkText = (
  name: string | undefined,
  t: (key: string, fallback?: string) => string,
) => name?.trim() || t('dashboard.interactionOpen', '打开链接');

export const withInteractionActionColumn = <T extends { columnType?: string }>(
  columns: T[],
  link: WidgetInteractionLink | undefined,
  surface: InteractionSurface,
  synthesized: T,
): T[] => {
  const dataColumns = columns.filter((column) => column.columnType !== 'actions');
  if (link?.kind !== 'data' || !shouldShowInteractionEntry(surface, true)) {
    return dataColumns;
  }
  return [...dataColumns, synthesized];
};

export const isFirstActionColumn = <T extends { columnType?: string }>(
  columns: T[],
  index: number,
) => columns.findIndex((column) => column.columnType === 'actions') === index;

/** 分享页不显示操作按钮；编辑态显示，是否跳转由打开函数决定。 */
export const shouldRenderInteractionActionButton = (
  link: WidgetInteractionLink | undefined,
  surface: InteractionSurface,
  isFirst: boolean,
) => link?.kind === 'data' && isFirst && shouldShowInteractionEntry(surface, true);

export const withChartLinkPoints = <T>(
  data: T[] | undefined,
  points: ChartLinkPoint[] | undefined,
): T[] | Array<{ value: T; __link: ChartLinkPoint }> => {
  if (!data) return [];
  if (!points || points.length === 0) return data;
  return data.map((value, index) => ({
    value,
    __link: points[index] ?? {},
  }));
};

const toIsoInstant = (value: unknown): string | undefined => {
  if (value == null || value === '') return undefined;
  if (typeof value === 'number' && Number.isFinite(value)) {
    const millis = value > 9999999999 ? value : value * 1000;
    const parsed = dayjs(millis);
    return parsed.isValid() ? parsed.toISOString() : undefined;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    if (/^\d+(\.\d+)?$/.test(trimmed)) {
      return toIsoInstant(Number(trimmed));
    }
    const parsed = dayjs(trimmed);
    return parsed.isValid() ? parsed.toISOString() : undefined;
  }
  return undefined;
};

export const chartLinkTime = (value: unknown, isTime: boolean): string | undefined => {
  if (!isTime) return undefined;
  return toIsoInstant(value);
};

const scalarText = (value: unknown): string => {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
};

const pointTokenValue = (point: ChartLinkPoint | undefined, body: string): string => {
  if (!point) return '';
  if (body === '__series.name') return point.seriesName ?? '';
  if (body === '__value.time') return point.time ?? '';
  if (body === '__value.numeric') {
    return typeof point.numeric === 'number' && Number.isFinite(point.numeric)
      ? String(point.numeric)
      : '';
  }
  if (body === '__value.text') return point.text ?? '';
  if (body === '__value.raw') return scalarText(point.raw);
  if (body.startsWith(DATA_FIELD_PREFIX)) {
    const field = body.slice(DATA_FIELD_PREFIX.length);
    if (!field || !point.fields || !Object.prototype.hasOwnProperty.call(point.fields, field)) {
      return '';
    }
    return scalarText(point.fields[field]);
  }
  return '';
};

export interface InteractionResolveInput {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
  point?: ChartLinkPoint;
  now?: Date | number | string;
}

const absoluteTimeBounds = (
  definition: UnifiedFilterDefinition,
  value: FilterValue | undefined,
  now: Date | number | string,
): { start: string; end: string } | null => {
  if (definition.type === 'timeRange') {
    const normalized = normalizeTimeRangeFilterValue(value, now);
    if (!normalized?.start || !normalized.end) return null;
    const start = toIsoInstant(normalized.start);
    const end = toIsoInstant(normalized.end);
    if (!start || !end) return null;
    return { start, end };
  }
  if (definition.type === 'dateRange') {
    const timezoneName = getDateRangeTimezone();
    const resolved = resolveDateRange(value, {
      referenceNow: now,
      timezone: timezoneName,
    });
    if (!resolved) return null;
    const [startDate, endDate] = resolved;
    const start = dayjs.tz(startDate, timezoneName).startOf('day');
    const end = dayjs.tz(endDate, timezoneName).endOf('day');
    if (!start.isValid() || !end.isValid()) return null;
    return { start: start.toISOString(), end: end.toISOString() };
  }
  return null;
};

const rawFilterText = (value: FilterValue | undefined): string => {
  if (value == null || value === '') return '';
  if (Array.isArray(value)) {
    return value
      .map((item) => (item == null || item === '' ? '' : String(item)))
      .join(',');
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return '';
};

const filterTokenValue = (
  definition: UnifiedFilterDefinition,
  value: FilterValue | undefined,
  part: 'all' | 'start' | 'end',
  now: Date | number | string,
): string => {
  if (definition.type === 'timeRange' || definition.type === 'dateRange') {
    const bounds = absoluteTimeBounds(definition, value, now);
    if (!bounds) return '';
    if (part === 'start') return bounds.start;
    if (part === 'end') return bounds.end;
    return `${bounds.start},${bounds.end}`;
  }
  return rawFilterText(value);
};

interface ParsedInteractionToken {
  body: string;
  end: number;
}

const readInteractionToken = (
  text: string,
  start: number,
): ParsedInteractionToken | null => {
  if (text[start] !== '$') return null;
  let body = '';
  for (let index = start + 1; index < text.length; index += 1) {
    const current = text[index];
    if (current === '\\' && text[index + 1] === '$') {
      body += '$';
      index += 1;
      continue;
    }
    if (current === '$') {
      if (!body || /\s/.test(body)) return null;
      return { body, end: index + 1 };
    }
    body += current;
  }
  return null;
};

const matchFilterVariable = (
  body: string,
  definitions: UnifiedFilterDefinition[],
): { definition: UnifiedFilterDefinition; part: 'all' | 'start' | 'end' } | null => {
  const variables = listFilterTemplateVariables(definitions);
  const exact = variables.find((item) => item.token === `$${body}$`);
  if (exact) return { definition: exact.definition, part: 'all' };
  const part = body.endsWith('.start')
    ? 'start'
    : body.endsWith('.end')
      ? 'end'
      : null;
  if (!part) return null;
  const base = body.slice(0, -(part.length + 1));
  const found = variables.find((item) => item.token === `$${base}$`);
  if (!found) return null;
  if (found.definition.type !== 'timeRange' && found.definition.type !== 'dateRange') {
    return null;
  }
  return { definition: found.definition, part };
};

const isDataToken = (body: string) =>
  DATA_VALUE_TOKENS.has(body) || body.startsWith(DATA_FIELD_PREFIX);

/**
 * 点击时解析链接。筛选写入原始 id；时间范围在此刻换成绝对 ISO。
 * 每个 token 单独 encodeURIComponent，静态 URL 片段保持原样。`\$` 输出字面量 `$`。
 *
 * 时间筛选：
 * - `$key$` / `$key:type$` → `startISO,endISO`
 * - `$key.start$` / `$key.end$`（有类型后缀时是 `$key:type.start$`）→ 单个端点
 * 相对时间用点击时刻换算；日期范围按日期时区取当天起止。
 */
export const resolveInteractionUrl = (
  template: string,
  input: InteractionResolveInput,
): string => {
  if (!template) return '';
  const now = input.now ?? new Date();
  let resolved = '';
  for (let cursor = 0; cursor < template.length; cursor += 1) {
    const current = template[cursor];
    if (current === '\\' && template[cursor + 1] === '$') {
      resolved += '$';
      cursor += 1;
      continue;
    }
    if (current !== '$') {
      resolved += current;
      continue;
    }
    const token = readInteractionToken(template, cursor);
    if (!token) {
      resolved += current;
      continue;
    }
    if (isDataToken(token.body)) {
      resolved += encodeURIComponent(pointTokenValue(input.point, token.body));
      cursor = token.end - 1;
      continue;
    }
    const filter = matchFilterVariable(token.body, input.definitions);
    if (!filter) {
      resolved += template.slice(cursor, token.end);
      cursor = token.end - 1;
      continue;
    }
    resolved += encodeURIComponent(
      filterTokenValue(
        filter.definition,
        input.values[filter.definition.id],
        filter.part,
        now,
      ),
    );
    cursor = token.end - 1;
  }
  return resolved;
};

const HAS_CONTROL_CHAR = /[\u0000-\u001F\u007F]/;

/** 只允许 http(s) 和单个 `/` 开头的站内路径。 */
export const isAllowedInteractionUrl = (url: string): boolean => {
  const trimmed = url.trim();
  if (!trimmed || HAS_CONTROL_CHAR.test(trimmed)) return false;
  if (trimmed.startsWith('/') && !trimmed.startsWith('//') && !trimmed.startsWith('/\\')) {
    return !trimmed.includes('\\');
  }
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

export const prepareInteractionNavigation = (
  url: string,
  openMode: WidgetInteractionOpenMode,
  currentSearch?: string,
) => {
  const trimmed = url.trim();
  if (!trimmed) return { ok: false as const, reason: 'empty' as const };
  if (!isAllowedInteractionUrl(trimmed)) {
    return { ok: false as const, reason: 'blocked' as const };
  }
  return {
    ok: true as const,
    ...resolveSameOriginNavigation(trimmed, {
      currentSearch,
      explicitNewWindow: openMode === 'newTab',
    }),
  };
};

const appendQuery = (url: string, query: string) => {
  if (!query) return url;
  const [withoutHash, hash = ''] = url.split('#');
  const separator = withoutHash.includes('?') ? '&' : '?';
  return `${withoutHash}${separator}${query}${hash ? `#${hash}` : ''}`;
};

const legacyParamQuery = (params: DashboardActionParamMapping[] | undefined) => {
  const parts: string[] = [];
  (params || []).forEach((mapping) => {
    const key = mapping.key?.trim();
    if (!key) return;
    if (mapping.source === 'rowField') {
      const field = mapping.sourceKey?.trim();
      if (!field) return;
      parts.push(
        `${encodeURIComponent(key)}=$${DATA_FIELD_PREFIX}${field}$`,
      );
      return;
    }
    if (mapping.source === 'fixed') {
      const literal = mapping.value == null ? '' : String(mapping.value);
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(literal)}`);
    }
  });
  return parts.join('&');
};

export const migrateActionsToInteraction = (
  actions: DashboardActionConfig[] | undefined,
): WidgetInteractionLink | undefined => {
  const first = actions?.[0];
  if (!first) return undefined;
  const base = first.url?.trim() || '';
  if (!base || !isAllowedInteractionUrl(base)) return undefined;
  const url = appendQuery(base, legacyParamQuery(first.params)).trim();
  if (!isAllowedInteractionUrl(url)) return undefined;
  return {
    kind: 'data',
    name: first.text?.trim() || '',
    url,
    openMode: first.openMode === 'newTab' ? 'newTab' : 'sameTab',
  };
};

export const normalizeInteractionLink = (
  link: (Omit<Partial<WidgetInteractionLink>, 'kind'> & {
    kind?: WidgetInteractionKind | 'none';
  }) | null | undefined,
  chartType?: string,
): WidgetInteractionLink | undefined => {
  if (!link || link.kind === 'none') return undefined;
  const url = link.url?.trim() || '';
  if (!url) return undefined;
  let kind: WidgetInteractionKind = link.kind === 'data' ? 'data' : 'title';
  const capability = interactionCapability(chartType);
  if (kind === 'data' && !capability.data) kind = 'title';
  return {
    kind,
    name: link.name?.trim() || '',
    url,
    openMode: link.openMode === 'newTab' ? 'newTab' : 'sameTab',
  };
};

export const readWidgetInteraction = (
  valueConfig?: {
    interaction?: Partial<WidgetInteractionLink> | null;
    actions?: DashboardActionConfig[];
    chartType?: string;
    sceneWidgetType?: string;
  } | null,
): WidgetInteractionLink | undefined => {
  const chartType = valueConfig?.sceneWidgetType || valueConfig?.chartType;
  const stored = normalizeInteractionLink(valueConfig?.interaction, chartType);
  if (stored) return stored;
  const migrated = migrateActionsToInteraction(valueConfig?.actions);
  return normalizeInteractionLink(migrated, chartType);
};

export const interactionKindForChartType = (
  chartType: string | undefined,
  currentKind: unknown,
): 'none' | WidgetInteractionKind => {
  if (currentKind === 'none') return 'none';
  return currentKind === 'data' && interactionCapability(chartType).data ? 'data' : 'title';
};

const hasOwn = (row: Record<string, unknown>, key: string) =>
  Object.prototype.hasOwnProperty.call(row, key);

const pushFieldVariable = (
  variables: InteractionVariable[],
  tokenBody: string,
  label: string,
  group: string,
  seen: Set<string>,
) => {
  const token = `$${tokenBody}$`;
  if (seen.has(token)) return;
  seen.add(token);
  variables.push({ token, label, group });
};

type PointSeriesKind = 'category' | 'series' | 'name' | 'indicator';

interface PointProfile {
  series?: PointSeriesKind;
  time?: boolean;
  /** 没有时间轴时，把类目字段放进数据点，不再在数据字段里重复。 */
  categoryAxis?: boolean;
  numeric?: boolean;
  fields?: boolean;
  fallback?: Array<'series' | 'numeric'>;
}

const POINT_PROFILES: Record<string, PointProfile> = {
  pie: { series: 'category', numeric: true, fields: true, fallback: ['series', 'numeric'] },
  line: { series: 'series', time: true, categoryAxis: true, numeric: true, fields: true, fallback: ['series', 'numeric'] },
  bar: { series: 'series', time: true, categoryAxis: true, numeric: true, fields: true, fallback: ['series', 'numeric'] },
  gauge: { numeric: true, fields: true, fallback: ['numeric'] },
  single: { numeric: true, fields: true, fallback: ['numeric'] },
  topN: { series: 'name', numeric: true, fields: true },
  cardList: { series: 'name', numeric: true, fields: true },
  multiValue: { series: 'name', numeric: true, fields: true },
  radar: { series: 'indicator', numeric: true, fields: false },
  eventTimeline: { time: true, fields: true },
  nodeGraph: { series: 'name', numeric: true, fields: true },
  table: { fields: true },
  eventTable: { fields: true },
};

interface DataVariableLabels {
  valueGroup: string;
  fieldGroup: string;
  fieldLabel: (field: string) => string;
  category?: string;
  series?: string;
  seriesName?: string;
  name?: string;
  indicator?: string;
  time?: string;
  numeric?: string;
}

const seriesSlotLabel = (kind: PointSeriesKind, labels: DataVariableLabels) => {
  if (kind === 'category') return labels.category || labels.seriesName || '$__series.name$';
  if (kind === 'name') return labels.name || labels.seriesName || '$__series.name$';
  if (kind === 'indicator') return labels.indicator || labels.seriesName || '$__series.name$';
  return labels.series || labels.seriesName || '$__series.name$';
};

const hasNumericPoint = (points: ChartLinkPoint[]) => points.some(
  (point) => typeof point.numeric === 'number' && Number.isFinite(point.numeric),
);

const exampleForToken = (points: ChartLinkPoint[], token: string) => {
  const body = token.slice(1, -1);
  return points.map((point) => pointTokenValue(point, body)).find((value) => value);
};

const addVariable = (
  variables: InteractionVariable[],
  seen: Set<string>,
  body: string,
  label: string,
  group: string,
  points: ChartLinkPoint[],
) => {
  const before = variables.length;
  pushFieldVariable(variables, body, label, group, seen);
  if (variables.length === before) return;
  const example = exampleForToken(points, variables[variables.length - 1].token);
  if (example) variables[variables.length - 1].example = example;
};

const collectFieldVariables = (
  points: ChartLinkPoint[],
  labels: { fieldGroup: string; fieldLabel: (field: string) => string },
  skip: Set<string> = new Set(),
): InteractionVariable[] => {
  const variables: InteractionVariable[] = [];
  const seen = new Set<string>();
  const fields = new Set<string>();
  points.forEach((point) => {
    Object.keys(point.fields || {}).forEach((key) => {
      if (!skip.has(key)) fields.add(key);
    });
  });
  [...fields].sort().forEach((field) => {
    addVariable(
      variables,
      seen,
      `${DATA_FIELD_PREFIX}${field}`,
      labels.fieldLabel(field),
      labels.fieldGroup,
      points,
    );
  });
  return variables;
};

const rowsOf = (data: unknown): Record<string, unknown>[] => {
  const list = Array.isArray(data)
    ? data
    : isRecord(data) && Array.isArray(data.items)
      ? data.items
      : isRecord(data) && Array.isArray(data.data)
        ? data.data
        : [];
  return list.filter(isRecord);
};

export const listPresentDataVariables = (
  chartType: string | undefined,
  rawData: unknown,
  labels: DataVariableLabels & {
    cabinetId?: string;
    cabinetName?: string;
    deviceId?: string;
    deviceName?: string;
    systemId?: string;
    systemName?: string;
    hostId?: string;
    hostName?: string;
  },
  points: ChartLinkPoint[] = [],
): InteractionVariable[] => {
  const capability = interactionCapability(chartType);
  if (!capability.data) return [];
  if (chartType === 'room3D' || chartType === 'application3D') {
    return listSceneVariables(chartType, rawData, labels);
  }
  const profile = POINT_PROFILES[chartType || ''];
  if (!profile) return [];
  if (points.length === 0) {
    if (rawData != null || !profile.fallback) return [];
    const group = labels.valueGroup;
    return profile.fallback.map((slot) => (
      slot === 'numeric'
        ? {
          token: '$__value.numeric$',
          label: labels.numeric || '$__value.numeric$',
          group,
        }
        : {
          token: '$__series.name$',
          label: profile.series
            ? seriesSlotLabel(profile.series, labels)
            : (labels.series || labels.seriesName || '$__series.name$'),
          group,
        }
    ));
  }

  const variables: InteractionVariable[] = [];
  const seen = new Set<string>();
  const hasTime = points.some((point) => point.time);
  if (profile.series && points.some((point) => point.seriesName)) {
    addVariable(
      variables,
      seen,
      '__series.name',
      seriesSlotLabel(profile.series, labels),
      labels.valueGroup,
      points,
    );
  }
  if (profile.time && hasTime) {
    addVariable(
      variables,
      seen,
      '__value.time',
      labels.time || '$__value.time$',
      labels.valueGroup,
      points,
    );
  }
  const axisField = profile.categoryAxis && !hasTime
    ? points.find((point) => point.axisField)?.axisField
    : undefined;
  if (axisField) {
    addVariable(
      variables,
      seen,
      `${DATA_FIELD_PREFIX}${axisField}`,
      labels.category || axisField,
      labels.valueGroup,
      points,
    );
  }
  if (profile.numeric && hasNumericPoint(points)) {
    addVariable(
      variables,
      seen,
      '__value.numeric',
      labels.numeric || '$__value.numeric$',
      labels.valueGroup,
      points,
    );
  }
  if (profile.fields) {
    collectFieldVariables(points, labels, new Set(axisField ? [axisField] : [])).forEach((item) => {
      if (seen.has(item.token)) return;
      seen.add(item.token);
      variables.push(item);
    });
  }
  return variables;
};

const listSceneVariables = (
  chartType: string,
  rawData: unknown,
  labels: {
    fieldGroup: string;
    cabinetId?: string;
    cabinetName?: string;
    deviceId?: string;
    deviceName?: string;
    systemId?: string;
    systemName?: string;
    hostId?: string;
    hostName?: string;
  },
): InteractionVariable[] => {
  const variables: InteractionVariable[] = [];
  const seen = new Set<string>();
  const add = (body: string, label: string, example?: unknown) => {
    const before = variables.length;
    pushFieldVariable(variables, body, label, labels.fieldGroup, seen);
    if (variables.length === before || example == null || example === '') return;
    variables[variables.length - 1].example = scalarText(example);
  };
  if (chartType === 'room3D' && isRecord(rawData)) {
    const racks = Array.isArray(rawData.racks) ? rawData.racks.filter(isRecord) : [];
    const rackWithId = racks.find((rack) => hasOwn(rack, 'rack_id') || hasOwn(rack, 'id'));
    const rackWithName = racks.find((rack) => hasOwn(rack, 'rack_name') || hasOwn(rack, 'name'));
    if (rackWithId) {
      add(RESERVED_FIELD_TOKENS.cabinetId, labels.cabinetId || 'cabinet.id', rackWithId.rack_id ?? rackWithId.id);
    }
    if (rackWithName) {
      add(RESERVED_FIELD_TOKENS.cabinetName, labels.cabinetName || 'cabinet.name', rackWithName.rack_name ?? rackWithName.name);
    }
    const devices = racks.flatMap((rack) =>
      Array.isArray(rack.devices) ? rack.devices.filter(isRecord) : [],
    );
    const deviceWithId = devices.find((device) => hasOwn(device, 'device_id') || hasOwn(device, 'id'));
    const deviceWithName = devices.find((device) => hasOwn(device, 'device_name') || hasOwn(device, 'name'));
    if (deviceWithId) {
      add(RESERVED_FIELD_TOKENS.deviceId, labels.deviceId || 'device.id', deviceWithId.device_id ?? deviceWithId.id);
    }
    if (deviceWithName) {
      add(RESERVED_FIELD_TOKENS.deviceName, labels.deviceName || 'device.name', deviceWithName.device_name ?? deviceWithName.name);
    }
  }
  if (chartType === 'application3D') {
    const systems = [
      ...sceneNodes(rawData, 'system'),
      ...unlabeledWallItems(rawData),
    ];
    const hosts = sceneNodes(rawData, 'host');
    const systemWithId = systems.find((node) => hasOwn(node, 'id'));
    const systemWithName = systems.find((node) => hasOwn(node, 'name'));
    const hostWithId = hosts.find((node) => hasOwn(node, 'id'));
    const hostWithName = hosts.find((node) => hasOwn(node, 'name'));
    if (systemWithId) {
      add(RESERVED_FIELD_TOKENS.systemId, labels.systemId || 'system.id', systemWithId.id);
    }
    if (systemWithName) {
      add(RESERVED_FIELD_TOKENS.systemName, labels.systemName || 'system.name', systemWithName.name);
    }
    if (hostWithId) {
      add(RESERVED_FIELD_TOKENS.hostId, labels.hostId || 'host.id', hostWithId.id);
    }
    if (hostWithName) {
      add(RESERVED_FIELD_TOKENS.hostName, labels.hostName || 'host.name', hostWithName.name);
    }
  }
  return variables;
};

const unlabeledWallItems = (rawData: unknown) => {
  if (!isRecord(rawData) || !Array.isArray(rawData.items)) return [];
  return rawData.items.filter(
    (item) => isRecord(item)
      && item.kind == null
      && (hasOwn(item, 'id') || hasOwn(item, 'name')),
  );
};

const sceneNodes = (rawData: unknown, kind: 'system' | 'host') => {
  if (!isRecord(rawData)) return [];
  const buckets = [
    rawData.items,
    rawData.nodes,
    rawData.applications,
    isRecord(rawData.architecture) ? rawData.architecture.nodes : undefined,
  ];
  return buckets.flatMap((bucket) =>
    Array.isArray(bucket)
      ? bucket.filter((item) => isRecord(item) && item.kind === kind)
      : [],
  );
};

export const sceneLinkPoint = (hit: {
  cabinet?: { id?: string; name?: string };
  device?: { id?: string; name?: string };
  system?: { id?: string; name?: string };
  host?: { id?: string; name?: string };
}): ChartLinkPoint => {
  const fields: Record<string, unknown> = {};
  if (hit.cabinet?.id) fields['cabinet.id'] = hit.cabinet.id;
  if (hit.cabinet?.name) fields['cabinet.name'] = hit.cabinet.name;
  if (hit.device?.id) fields['device.id'] = hit.device.id;
  if (hit.device?.name) fields['device.name'] = hit.device.name;
  if (hit.system?.id) fields['system.id'] = hit.system.id;
  if (hit.system?.name) fields['system.name'] = hit.system.name;
  if (hit.host?.id) fields['host.id'] = hit.host.id;
  if (hit.host?.name) fields['host.name'] = hit.host.name;
  return { fields };
};

export const tableRowLinkPoint = (record: Record<string, unknown>): ChartLinkPoint => ({
  fields: chartLinkFields(record),
  raw: record,
});

/** 事件时间线数据链接：时间、标题，以及原始行上真实存在的字段。 */
export const eventTimelineLinkPoint = (item: {
  time?: string;
  title?: string;
  source?: Record<string, unknown>;
}): ChartLinkPoint => {
  const iso = item.time ? chartLinkTime(item.time, true) : undefined;
  const time = iso || item.time || undefined;
  const fields = chartLinkFields(item.source);
  return {
    ...(time ? { time } : {}),
    ...(item.title ? { text: item.title } : {}),
    ...(item.source ? { raw: item.source } : {}),
    ...(fields ? { fields } : {}),
  };
};

/** 配了数据链接时，标题不再使用 linkField 的地址。 */
export const shouldRenderEventTimelineFieldLink = (
  link: WidgetInteractionLink | undefined,
  fieldLink?: string,
) => Boolean(fieldLink) && link?.kind !== 'data';

export const listTableFieldVariables = (
  rows: Array<Record<string, unknown>>,
  labels: { fieldGroup: string; fieldLabel: (field: string) => string },
): InteractionVariable[] =>
  collectFieldVariables(
    rows.map((row) => ({ fields: chartLinkFields(row) })),
    labels,
  );

export const listInteractionVariables = ({
  definitions,
  dataVariables,
  filterGroup,
  timeStartLabel,
  timeEndLabel,
}: {
  definitions: UnifiedFilterDefinition[];
  dataVariables: InteractionVariable[];
  filterGroup: string;
  timeStartLabel: (name: string) => string;
  timeEndLabel: (name: string) => string;
}): InteractionVariable[] => {
  const filters: InteractionVariable[] = [];
  listFilterTemplateVariables(definitions).forEach((item) => {
    const name = item.definition.name?.trim() || item.definition.key;
    const valueType = filterDropdownType(item.definition.type);
    filters.push({ token: item.token, label: name, group: filterGroup, valueType });
    if (item.definition.type !== 'timeRange' && item.definition.type !== 'dateRange') return;
    const inner = item.token.slice(1, -1);
    filters.push({
      token: `$${inner}.start$`,
      label: timeStartLabel(name),
      group: filterGroup,
      valueType,
    });
    filters.push({
      token: `$${inner}.end$`,
      label: timeEndLabel(name),
      group: filterGroup,
      valueType,
    });
  });
  return [...filters, ...dataVariables];
};

export const listUnmatchedInteractionTokens = (
  text: string,
  variables: InteractionVariable[],
): string[] => {
  if (!text) return [];
  const known = new Set(variables.map((item) => item.token));
  const unmatched: string[] = [];
  const seen = new Set<string>();
  for (let cursor = 0; cursor < text.length; cursor += 1) {
    if (text[cursor] === '\\' && text[cursor + 1] === '$') {
      cursor += 1;
      continue;
    }
    if (text[cursor] !== '$') continue;
    const token = readInteractionToken(text, cursor);
    if (!token) continue;
    const raw = text.slice(cursor, token.end);
    cursor = token.end - 1;
    if (known.has(raw) || DATA_VALUE_TOKENS.has(token.body) || seen.has(raw)) continue;
    seen.add(raw);
    unmatched.push(raw);
  }
  return unmatched;
};

export const rowsFromUnknown = rowsOf;
