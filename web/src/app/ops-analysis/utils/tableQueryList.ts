import dayjs from 'dayjs';

import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';

export type TableQueryCondition =
  | { field: string; type: 'str*'; value: string }
  | { field: string; type: 'time'; start: string; end: string };

export const buildTableQueryList = (
  filters: Record<string, unknown> = {},
): TableQueryCondition[] => {
  const queryList: TableQueryCondition[] = [];

  Object.entries(filters).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }

    if (
      Array.isArray(value)
      && value.length === 2
      && dayjs.isDayjs(value[0])
      && dayjs.isDayjs(value[1])
    ) {
      queryList.push({
        field: key,
        type: 'time',
        start: formatOpsRequestTime(value[0]),
        end: formatOpsRequestTime(value[1]),
      });
      return;
    }

    if (typeof value === 'string') {
      const text = value.trim();
      if (!text) {
        return;
      }
      queryList.push({
        field: key,
        type: 'str*',
        value: text,
      });
    }
  });

  return queryList;
};

export const applyTableQueryList = <RecordType extends Record<string, any>>(
  rows: RecordType[],
  queryList: TableQueryCondition[],
): RecordType[] => {
  if (!queryList.length) {
    return rows;
  }

  return rows.filter((row) => queryList.every((condition) => rowMatches(row, condition)));
};

export const applyTableRowFilters = <RecordType extends Record<string, any>>(
  rows: RecordType[],
  filters: Record<string, unknown> = {},
): RecordType[] => applyTableQueryList(rows, buildTableQueryList(filters));

const rowMatches = (
  row: Record<string, unknown>,
  condition: TableQueryCondition,
): boolean => {
  const rawValue = row?.[condition.field];
  if (condition.type === 'time') {
    const current = dayjs(rawValue as dayjs.ConfigType);
    const start = dayjs(condition.start);
    const end = dayjs(condition.end);
    if (!current.isValid() || !start.isValid() || !end.isValid()) {
      return false;
    }
    return (
      (current.isAfter(start) || current.isSame(start))
      && (current.isBefore(end) || current.isSame(end))
    );
  }

  const needle = condition.value.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystack = rawValue == null ? '' : String(rawValue).toLowerCase();
  return haystack.includes(needle);
};
