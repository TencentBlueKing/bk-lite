import type { Key } from 'react';

export const ALARM_SETTINGS_STORAGE_KEY = 'alarmSettings';
export const ALARM_DISPLAY_FIELD_KEYS = 'displayFieldKeys';
export const ALARM_TABLE_ACTION_COLUMN_KEY = 'action';

interface ColumnLike {
  key?: Key;
}

type AlarmSettings = Record<string, unknown>;

const isPlainObject = (value: unknown): value is AlarmSettings =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

const readStorage = (storage?: Pick<Storage, 'getItem'> | null): string | null => {
  try {
    return storage?.getItem(ALARM_SETTINGS_STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
};

export const parseAlarmSettings = (raw: string | null): AlarmSettings => {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return isPlainObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
};

export const readAlarmDisplayFieldKeys = (
  storage?: Pick<Storage, 'getItem'> | null
): string[] | null => {
  const settings = parseAlarmSettings(readStorage(storage));
  const keys = settings[ALARM_DISPLAY_FIELD_KEYS];
  return isStringArray(keys) ? keys : null;
};

export const saveAlarmDisplayFieldKeys = (
  fields: string[],
  storage?: Pick<Storage, 'getItem' | 'setItem'> | null
): void => {
  if (!storage?.setItem) return;
  const settings = parseAlarmSettings(readStorage(storage));
  storage.setItem(
    ALARM_SETTINGS_STORAGE_KEY,
    JSON.stringify({
      ...settings,
      [ALARM_DISPLAY_FIELD_KEYS]: fields,
    })
  );
};

export const getAlarmTableChoosableColumns = <T extends ColumnLike>(
  columns: T[]
): T[] => columns.filter((column) => column.key !== ALARM_TABLE_ACTION_COLUMN_KEY);

export const resolveAlarmTableColumns = <T extends ColumnLike>(
  columns: T[],
  displayFieldKeys?: string[] | null
): T[] => {
  const actionColumn = columns.find(
    (column) => column.key === ALARM_TABLE_ACTION_COLUMN_KEY
  );
  const choosable = getAlarmTableChoosableColumns(columns);
  const selectedKeys =
    displayFieldKeys == null
      ? choosable.map((column) => String(column.key ?? ''))
      : displayFieldKeys;
  const byKey = new Map(
    choosable
      .filter((column) => column.key != null && column.key !== '')
      .map((column) => [String(column.key), column])
  );
  const ordered: T[] = [];
  for (const key of selectedKeys) {
    if (key === ALARM_TABLE_ACTION_COLUMN_KEY) continue;
    const column = byKey.get(key);
    if (column) ordered.push(column);
  }
  if (actionColumn) ordered.push(actionColumn);
  return ordered;
};
