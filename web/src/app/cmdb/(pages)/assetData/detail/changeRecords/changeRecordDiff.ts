interface TableColumn {
  column_id: string;
  column_name?: string;
  order?: number;
}

export interface ChangeRecordAttribute {
  attr_name?: string;
  attr_type?: string;
  option?: unknown;
}

export interface ChangeRecordDiffSource {
  label: string;
  before_data?: Record<string, unknown>;
  after_data?: Record<string, unknown>;
}

export interface ChangeRecordDiffRow {
  attr: string;
  before: string;
  after: string;
  current: string;
  changed: boolean;
  currentDiff: boolean;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const stableSerialize = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(',')}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value) ?? String(value);
};

const parseTableRows = (value: unknown): unknown[] | null => {
  let parsed = value;
  if (typeof value === 'string') {
    try {
      parsed = JSON.parse(value);
    } catch {
      return null;
    }
  }

  if (Array.isArray(parsed)) return parsed;
  return isRecord(parsed) ? [parsed] : null;
};

const getTableColumns = (attribute?: ChangeRecordAttribute): TableColumn[] => {
  if (!Array.isArray(attribute?.option)) return [];

  return attribute.option
    .filter(
      (column): column is TableColumn =>
        isRecord(column) && typeof column.column_id === 'string'
    )
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
};

const formatNestedValue = (value: unknown): string => {
  if (value === undefined || value === null || value === '') return '--';
  if (typeof value === 'object') return stableSerialize(value);
  return String(value);
};

export const formatChangeRecordValue = (
  value: unknown,
  attribute?: ChangeRecordAttribute
): string => {
  if (value === undefined || value === null || value === '') return '--';

  if (attribute?.attr_type === 'table') {
    const rows = parseTableRows(value);
    if (rows) {
      if (rows.length === 0) return '--';

      const columns = getTableColumns(attribute);
      return rows
        .map((row) => {
          if (!isRecord(row)) return formatNestedValue(row);
          if (!columns.length) return stableSerialize(row);

          return columns
            .map((column) => {
              const label = column.column_name || column.column_id;
              return `${label}：${formatNestedValue(row[column.column_id])}`;
            })
            .join('；');
        })
        .join('\n');
    }
  }

  if (typeof value === 'object') return stableSerialize(value);
  return String(value);
};

const normalizeForComparison = (
  value: unknown,
  attribute?: ChangeRecordAttribute
): unknown => {
  if (value === undefined || value === null || value === '') return null;
  if (attribute?.attr_type !== 'table') return value;

  const rows = parseTableRows(value);
  return rows?.length ? rows : null;
};

const valuesEqual = (
  left: unknown,
  right: unknown,
  attribute?: ChangeRecordAttribute
): boolean =>
  stableSerialize(normalizeForComparison(left, attribute)) ===
  stableSerialize(normalizeForComparison(right, attribute));

export const buildChangeRecordDiffRows = (
  selectedRecord: ChangeRecordDiffSource | null,
  currentInstance: Record<string, unknown>,
  attrFieldMap: Record<string, ChangeRecordAttribute>
): ChangeRecordDiffRow[] => {
  if (!selectedRecord || selectedRecord.label !== 'instance') return [];

  const beforeData = selectedRecord.before_data || {};
  const afterData = selectedRecord.after_data || {};
  const keys = Array.from(
    new Set([...Object.keys(afterData), ...Object.keys(beforeData)])
  ).filter((key) => !key.startsWith('_'));

  return keys.map((key) => {
    const attribute = attrFieldMap[key];
    const before = formatChangeRecordValue(beforeData[key], attribute);
    const after = formatChangeRecordValue(afterData[key], attribute);
    const current = formatChangeRecordValue(currentInstance[key], attribute);

    return {
      attr: attribute?.attr_name || key,
      before,
      after,
      current,
      changed: !valuesEqual(beforeData[key], afterData[key], attribute),
      currentDiff: !valuesEqual(afterData[key], currentInstance[key], attribute),
    };
  });
};
