export interface ViewColumnLike {
  key: string;
  fixed?: boolean | 'left' | 'right';
}

export interface ResolvedViewColumns<T extends ViewColumnLike> {
  columns: T[];
  fieldKeys: string[];
}

export const DEFAULT_VIEW_FIXED_FIELD_KEYS = ['instance_name'];

/** 固定列靠左且保持各自相对顺序，满足 Ant Design fixed 连续性要求。 */
export const orderFieldKeysWithFixedFirst = (
  fieldKeys: string[],
  fixedFieldKeys: string[]
): { fieldKeys: string[]; fixedFieldKeys: string[] } => {
  const fixedSet = new Set(
    fixedFieldKeys.filter((key) => fieldKeys.includes(key))
  );
  const nextFixed = fieldKeys.filter((key) => fixedSet.has(key));
  const rest = fieldKeys.filter((key) => !fixedSet.has(key));
  return {
    fieldKeys: [...nextFixed, ...rest],
    fixedFieldKeys: nextFixed
  };
};

export const resolveFixedFieldKeys = (
  fieldKeys: string[],
  savedFixedFieldKeys: string[] | null | undefined,
  defaultFixedFieldKeys: string[] = DEFAULT_VIEW_FIXED_FIELD_KEYS
): string[] => {
  const source =
    savedFixedFieldKeys == null ? defaultFixedFieldKeys : savedFixedFieldKeys;
  return fieldKeys.filter((key) => source.includes(key));
};

export const resolveViewColumns = <T extends ViewColumnLike>(
  availableColumns: T[],
  savedFieldKeys: string[] | null | undefined,
  fixedFieldKeys: string[] = ['action'],
  savedFixedFieldKeys: string[] | null | undefined = null,
  defaultFixedFieldKeys: string[] = DEFAULT_VIEW_FIXED_FIELD_KEYS
): ResolvedViewColumns<T> => {
  const fixedKeys = new Set(fixedFieldKeys);
  const choosableColumns = availableColumns.filter(
    (column) => !fixedKeys.has(column.key)
  );
  const availableByKey = new Map(
    choosableColumns.map((column) => [column.key, column])
  );
  const validSavedKeys = (savedFieldKeys || []).filter((key) =>
    availableByKey.has(key)
  );
  const rawFieldKeys = validSavedKeys.length
    ? validSavedKeys
    : choosableColumns.map((column) => column.key);
  const ordered = orderFieldKeysWithFixedFirst(
    rawFieldKeys,
    resolveFixedFieldKeys(
      rawFieldKeys,
      savedFixedFieldKeys,
      defaultFixedFieldKeys
    )
  );
  const selectedColumns = ordered.fieldKeys
    .map((key) => {
      const column = availableByKey.get(key);
      if (!column) return undefined;
      if (ordered.fixedFieldKeys.includes(key)) {
        return { ...column, fixed: 'left' as const };
      }
      if (column.fixed === 'left') {
        const nextColumn = { ...column };
        delete nextColumn.fixed;
        return nextColumn;
      }
      return column;
    })
    .filter((column): column is T => Boolean(column));
  const trailingFixedColumns = availableColumns.filter((column) =>
    fixedKeys.has(column.key)
  );

  return {
    columns: [...selectedColumns, ...trailingFixedColumns],
    fieldKeys: ordered.fieldKeys
  };
};
