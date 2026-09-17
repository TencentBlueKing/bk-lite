export interface FrozenQueryClue {
  policy_id?: number | string | null;
  policy_name?: string | null;
  collect_type_id?: number | string | null;
  collect_type_name?: string | null;
  log_groups?: unknown;
  alert_type?: string | null;
  alert_name?: string | null;
  alert_level?: string | null;
  alert_condition?: unknown;
  period?: unknown;
  schedule?: unknown;
  show_fields?: unknown;
  window_start?: number | string | null;
  window_end?: number | string | null;
}

export interface AlertSnapshotItem {
  type?: string;
  event_id?: string;
  event_time?: string;
  snapshot_time?: string;
  raw_data?: unknown;
  query_clue?: FrozenQueryClue | null;
}

export interface AlertInfoEvidence {
  id?: string;
  source_id?: string;
  level?: string;
  content?: string;
  start_event_time?: string;
}

export function hasFrozenQueryClue(clue: unknown): clue is FrozenQueryClue {
  return Boolean(clue) && typeof clue === 'object' && !Array.isArray(clue) && Object.keys(clue as object).length > 0;
}

export function hasSnapshotRawData(rawData: unknown): boolean {
  if (rawData == null) return false;
  if (Array.isArray(rawData)) return rawData.length > 0;
  if (typeof rawData === 'object') return Object.keys(rawData).length > 0;
  return true;
}

export function historicalAlertInfo(alertInfo: AlertInfoEvidence | null | undefined): AlertInfoEvidence {
  if (!alertInfo) return {};
  return {
    id: alertInfo.id,
    source_id: alertInfo.source_id,
    level: alertInfo.level,
    content: alertInfo.content,
    start_event_time: alertInfo.start_event_time,
  };
}

export function formatClueTimestamp(
  time: unknown,
  convertToLocalizedTime?: (iso: string) => string,
): string {
  if (time == null || time === '') return '--';
  if (typeof time === 'number') {
    const ms = time < 10000000000 ? time * 1000 : time;
    const iso = new Date(ms).toISOString();
    return convertToLocalizedTime ? convertToLocalizedTime(iso) || iso : iso;
  }
  if (typeof time === 'string') {
    const trimmed = time.trim();
    if (!trimmed) return '--';
    const num = Number(trimmed);
    if (!isNaN(num) && /^\d+$/.test(trimmed)) {
      const ms = num < 10000000000 ? num * 1000 : num;
      const iso = new Date(ms).toISOString();
      return convertToLocalizedTime ? convertToLocalizedTime(iso) || iso : iso;
    }
    return convertToLocalizedTime ? convertToLocalizedTime(trimmed) || trimmed : trimmed;
  }
  return String(time);
}

export function formatPeriod(
  period: unknown,
  t?: (key: string, defaultVal?: string) => string,
): string {
  if (period == null || period === '') return '--';
  if (typeof period === 'number') {
    return `${period}s`;
  }
  if (typeof period === 'string') {
    return period.trim() || '--';
  }
  if (typeof period === 'object' && period !== null) {
    const p = period as { type?: string; value?: number | string };
    if (p.value != null && p.value !== '') {
      const type = String(p.type || '').toLowerCase();
      const unitMap: Record<string, string> = {
        min: t ? t('common.minute', 'minute') : 'm',
        m: t ? t('common.minute', 'minute') : 'm',
        sec: t ? t('common.second', 'second') : 's',
        s: t ? t('common.second', 'second') : 's',
        hour: t ? t('common.hour', 'hour') : 'h',
        h: t ? t('common.hour', 'hour') : 'h',
        day: t ? t('common.day', 'day') : 'd',
        d: t ? t('common.day', 'day') : 'd',
      };
      const unit = unitMap[type] || type;
      return `${p.value} ${unit}`.trim();
    }
  }
  return '--';
}

export interface FormattedConditionRule {
  field: string;
  op: string;
  value: string;
}

export interface FormattedCondition {
  query?: string;
  ruleMode?: string;
  conditions?: FormattedConditionRule[];
  groupBy?: string[];
  rawText?: string;
}

export function parseAlertCondition(
  rawCondition: unknown,
  fallbackQuery?: unknown,
): FormattedCondition | null {
  if (!rawCondition && !fallbackQuery) return null;

  if (typeof rawCondition === 'string') {
    const trimmed = rawCondition.trim();
    return trimmed ? { query: trimmed } : null;
  }

  if (typeof rawCondition === 'object' && rawCondition !== null) {
    const cond = rawCondition as Record<string, unknown>;
    const query =
      typeof cond.query === 'string' && cond.query.trim()
        ? cond.query.trim()
        : typeof fallbackQuery === 'string' && fallbackQuery.trim()
          ? fallbackQuery.trim()
          : undefined;

    const ruleObj =
      cond.rule && typeof cond.rule === 'object'
        ? (cond.rule as Record<string, unknown>)
        : undefined;
    const ruleMode =
      typeof ruleObj?.mode === 'string' ? ruleObj.mode.toUpperCase() : undefined;
    const rawConditions = Array.isArray(ruleObj?.conditions)
      ? ruleObj.conditions
      : undefined;

    const conditions: FormattedConditionRule[] | undefined = rawConditions
      ?.map((c) => {
        if (typeof c === 'object' && c !== null) {
          const item = c as Record<string, unknown>;
          return {
            field: String(item.field || ''),
            op: String(item.op || '='),
            value: String(item.value ?? ''),
          };
        }
        return { field: '', op: '=', value: String(c) };
      })
      .filter((c) => c.field || c.value);

    let groupBy: string[] | undefined;
    if (Array.isArray(cond.group_by)) {
      groupBy = cond.group_by.map((g) => String(g)).filter(Boolean);
    }

    if (
      query ||
      (conditions && conditions.length > 0) ||
      (groupBy && groupBy.length > 0)
    ) {
      return { query, ruleMode, conditions, groupBy };
    }

    try {
      const json = JSON.stringify(rawCondition);
      if (json !== '{}') return { rawText: json };
    } catch {
      return null;
    }
  }

  if (typeof fallbackQuery === 'string' && fallbackQuery.trim()) {
    return { query: fallbackQuery.trim() };
  }

  return null;
}

export interface RawLogTableRow {
  __id: string | number;
  [key: string]: unknown;
}

export interface ParsedRawDataResult {
  isTabular: boolean;
  isAggregate: boolean;
  rows: RawLogTableRow[];
  columns: Array<{ key: string; title: string; dataIndex: string; width?: number }>;
  timeKey?: string;
  messageKey?: string;
}

export function normalizeRawDataList(rawData: unknown): unknown[] | null {
  if (rawData == null) return null;
  if (Array.isArray(rawData)) return rawData;
  if (typeof rawData === 'object') {
    const obj = rawData as Record<string, unknown>;
    if (Array.isArray(obj.data)) return obj.data;
    if (Array.isArray(obj.logs)) return obj.logs;
    if (Array.isArray(obj.list)) return obj.list;
    return [obj];
  }
  return null;
}

export function parseRawLogData(rawData: unknown): ParsedRawDataResult {
  const list = normalizeRawDataList(rawData);
  if (!list || list.length === 0) {
    return { isTabular: false, isAggregate: false, rows: [], columns: [] };
  }

  const allObjects = list.every(
    (item) => typeof item === 'object' && item !== null && !Array.isArray(item),
  );
  if (!allObjects) {
    return { isTabular: false, isAggregate: false, rows: [], columns: [] };
  }

  const objectList = list as Array<Record<string, unknown>>;
  const timeKeyCandidates = ['_time', 'timestamp', 'time', '@timestamp'];
  const messageKeyCandidates = ['message', '_msg', 'log', 'content'];

  let detectedTimeKey: string | undefined;
  let detectedMessageKey: string | undefined;

  for (const key of timeKeyCandidates) {
    if (objectList.some((row) => key in row && row[key] != null && row[key] !== '')) {
      detectedTimeKey = key;
      break;
    }
  }

  for (const key of messageKeyCandidates) {
    if (objectList.some((row) => key in row && row[key] != null && row[key] !== '')) {
      detectedMessageKey = key;
      break;
    }
  }

  const rows: RawLogTableRow[] = objectList.map((row, index) => ({
    __id: (row.id as string | number) ?? index,
    ...row,
  }));

  if (!detectedTimeKey && !detectedMessageKey) {
    const firstRow = objectList[0] || {};
    const sampleKeys = Object.keys(firstRow).filter((k) => k !== 'id' && k !== '__id');
    const allPrimitives =
      sampleKeys.length > 0 &&
      sampleKeys.every((k) => {
        const val = firstRow[k];
        return val === null || typeof val !== 'object';
      });

    if (allPrimitives) {
      const columns = sampleKeys.map((key) => ({
        key,
        title: key,
        dataIndex: key,
      }));
      return {
        isTabular: true,
        isAggregate: true,
        rows,
        columns,
      };
    }

    return { isTabular: false, isAggregate: false, rows: [], columns: [] };
  }

  const columns: Array<{ key: string; title: string; dataIndex: string; width?: number }> = [];
  if (detectedTimeKey) {
    columns.push({
      key: detectedTimeKey,
      title: 'timestamp',
      dataIndex: detectedTimeKey,
      width: 175,
    });
  }
  if (detectedMessageKey) {
    columns.push({
      key: detectedMessageKey,
      title: 'message',
      dataIndex: detectedMessageKey,
    });
  }

  return {
    isTabular: true,
    isAggregate: false,
    rows,
    columns,
    timeKey: detectedTimeKey,
    messageKey: detectedMessageKey,
  };
}
